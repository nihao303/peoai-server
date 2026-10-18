"""请求队列与状态机。

一个 Job 的生命周期：

    pending --claim--> claimed --reply--> answered
       |                  |
       +----reject-------> rejected       +----> cancelled（客户端断开）
       +----ttl 超时-----> expired

并发模型：
    * Flask 多线程处理 HTTP；Job 内部用 Condition 等待终态；
    * 流式客户端通过订阅队列接收增量，窗口外自动补发历史增量；
    * 状态变化同时广播给所有操作台 SSE 连接，多开控制台不会丢事件。
"""
from __future__ import annotations

import base64
import copy
import hashlib
import json
import os
import queue
import re
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from .errors import bad_request, not_found, rate_limited, timeout_error, unavailable
from .images import public_media, strip_inline
from .util import iso_time, new_id, now, truncate

TERMINAL = ("answered", "rejected", "cancelled", "expired")
ACTIVE = ("pending", "claimed")

PROTOCOL_LABELS = {
    "openai.chat": "OpenAI Chat Completions",
    "openai.completions": "OpenAI Completions",
    "openai.responses": "OpenAI Responses",
    "anthropic.messages": "Anthropic Messages",
    "gemini.generate": "Gemini generateContent",
    "ollama.chat": "Ollama Chat",
}

_MAX_EVENT_QUEUE = 256
_BASE64ISH = re.compile(r"^[A-Za-z0-9+/=\s]{600,}$")


def _notify(job: "Job") -> None:
    """安全唤醒等待中的客户端（Condition 必须持锁 notify）。"""
    with job._cv:
        job._cv.notify_all()


def sanitize_raw(value: Any, depth: int = 0) -> Any:
    """把原始请求体压缩成可读预览：超长 base64 与超长文本折叠。"""
    if depth > 12:
        return "<depth-limit>"
    if isinstance(value, dict):
        return {str(key)[:64]: sanitize_raw(item, depth + 1) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [sanitize_raw(item, depth + 1) for item in value[:64]]
    if isinstance(value, str):
        if len(value) > 600 and _BASE64ISH.match(value):
            return "<base64 %d chars omitted>" % len(value)
        if len(value) > 8000:
            return value[:8000] + "... <truncated %d chars>" % (len(value) - 8000)
        return value
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    return truncate(value, 400)


def raw_preview(body: Any) -> Dict[str, Any]:
    """构造落盘用的原始请求预览，整体不超过约 100KB。"""
    try:
        cleaned = sanitize_raw(body)
        text = json.dumps(cleaned, ensure_ascii=False)
        if len(text) > 100000:
            return {"_omitted": True, "reason": "请求体过大，已省略原始内容"}
        return cleaned
    except (TypeError, ValueError):
        return {"_omitted": True, "reason": "无法序列化原始请求"}


@dataclass
class Job:
    """一次待人工作答的请求。"""

    id: str
    protocol: str
    model: str
    stream: bool
    created_at: float
    messages: List[Dict[str, Any]] = field(default_factory=list)
    tools: List[Dict[str, Any]] = field(default_factory=list)
    tool_choice: Any = None
    params: Dict[str, Any] = field(default_factory=dict)
    images: List[Dict[str, Any]] = field(default_factory=list)
    api_key: str = "anonymous"
    client_ip: str = ""
    user_agent: str = ""
    request_model: str = ""
    meta: Dict[str, Any] = field(default_factory=dict)
    raw: Dict[str, Any] = field(default_factory=dict)

    status: str = "pending"
    claimed_at: Optional[float] = None
    claimed_by: Optional[str] = None
    first_delta_at: Optional[float] = None
    typing: bool = False
    deltas: List[Dict[str, Any]] = field(default_factory=list)
    reply_text: str = ""
    reply_reasoning: str = ""
    reply_tools: List[Dict[str, Any]] = field(default_factory=list)
    finish_reason: Optional[str] = None
    rejected_reason: Optional[str] = None
    completed_at: Optional[float] = None
    usage_note: Optional[str] = None
    version: int = 0

    _subs: List[Any] = field(default_factory=list, repr=False, compare=False)
    _cv: Any = field(default_factory=threading.Condition, repr=False, compare=False)
    _lock: Any = field(default_factory=threading.RLock, repr=False, compare=False)

    # -- 派生信息 --------------------------------------------------------
    @property
    def protocol_label(self) -> str:
        return PROTOCOL_LABELS.get(self.protocol, self.protocol)

    def age(self) -> float:
        return max(0.0, now() - self.created_at)

    def preview(self) -> str:
        for message in reversed(self.messages):
            if message.get("role") == "user" and message.get("text"):
                return truncate(message["text"].strip(), 180)
        for message in self.messages:
            if message.get("text"):
                return truncate(message["text"].strip(), 180)
        return "(空请求)"

    def image_count(self) -> int:
        return sum(len(message.get("images") or []) for message in self.messages)

    def conversation_key(self) -> str:
        """把同一对话的多轮请求归到一组。

        优先使用调用方显式传入的 user / X-PeoAI-Conversation；
        否则用「system + 第一条 user 消息」做稳定指纹。
        """
        meta = self.meta or {}
        explicit = str(meta.get("conversation") or meta.get("user") or "").strip()
        if explicit:
            return "conv_" + hashlib.sha1(("tag:" + explicit).encode("utf-8")).hexdigest()[:12]
        system_text = ""
        first_user = ""
        for message in self.messages:
            role = message.get("role")
            if role == "system" and not system_text:
                system_text = message.get("text") or ""
            elif role == "user" and message.get("text") and not first_user:
                first_user = message["text"]
                break
        if not first_user and not system_text:
            return "conv_" + self.id[4:16]
        seed = system_text + "\n---\n" + first_user
        return "conv_" + hashlib.sha1(seed.encode("utf-8")).hexdigest()[:12]

    def conversation_title(self) -> str:
        for message in self.messages:
            if message.get("role") == "user" and message.get("text"):
                return truncate(message["text"].strip(), 60)
        return self.conversation_key()

    # -- 序列化 ----------------------------------------------------------
    def summary(self, show_ip: bool = True) -> Dict[str, Any]:
        data = {
            "id": self.id,
            "status": self.status,
            "protocol": self.protocol,
            "protocol_label": self.protocol_label,
            "model": self.model,
            "request_model": self.request_model,
            "stream": bool(self.stream),
            "created_at": self.created_at,
            "created_iso": iso_time(self.created_at),
            "age_seconds": round(self.age(), 1),
            "preview": self.preview(),
            "conversation_id": self.conversation_key(),
            "conversation_title": self.conversation_title(),
            "message_count": len(self.messages),
            "image_count": self.image_count(),
            "tool_count": len(self.tools),
            "api_key": self.api_key,
            "version": self.version,
            "typing": bool(self.typing),
            "claimed_at": self.claimed_at,
            "completed_at": self.completed_at,
            "finish_reason": self.finish_reason,
        }
        if show_ip:
            data["client_ip"] = self.client_ip
        return data

    def detail(self, include_inline: bool = True, show_ip: bool = True) -> Dict[str, Any]:
        data = self.summary(show_ip=show_ip)
        messages = []
        for message in self.messages:
            item = {
                "role": message.get("role"),
                "text": message.get("text") or "",
                "name": message.get("name") or "",
                "tool_call_id": message.get("tool_call_id") or "",
                "images": [public_media(img, include_inline) for img in message.get("images") or []],
                "tool_calls": [
                    {
                        "id": call.get("id", ""),
                        "name": call.get("name", ""),
                        "arguments": call.get("arguments", ""),
                        "arguments_json": call.get("arguments_json"),
                    }
                    for call in message.get("tool_calls") or []
                ],
            }
            messages.append(item)
        data["messages"] = messages
        data["tools"] = self.tools
        data["tool_choice"] = self.tool_choice
        data["params"] = self.params
        data["images"] = [public_media(img, include_inline) for img in self.images]
        data["reply"] = {
            "text": self.reply_text,
            "reasoning": self.reply_reasoning,
            "tool_calls": self.reply_tools,
            "finish_reason": self.finish_reason,
            "completed_at": self.completed_at,
            "deltas": len(self.deltas),
        }
        data["meta"] = self.meta
        data["raw"] = self.raw
        data["user_agent"] = self.user_agent
        return data

    def to_json(self, persist_media: bool = False) -> Dict[str, Any]:
        messages = []
        for message in self.messages:
            messages.append(
                {
                    "role": message.get("role"),
                    "text": message.get("text") or "",
                    "name": message.get("name") or "",
                    "tool_call_id": message.get("tool_call_id") or "",
                    "images": [
                        (img if persist_media else strip_inline(img))
                        for img in message.get("images") or []
                    ],
                    "tool_calls": message.get("tool_calls") or [],
                }
            )
        return {
            "id": self.id,
            "protocol": self.protocol,
            "model": self.model,
            "request_model": self.request_model,
            "stream": self.stream,
            "created_at": self.created_at,
            "messages": messages,
            "tools": self.tools,
            "tool_choice": self.tool_choice,
            "params": self.params,
            "images": [(img if persist_media else strip_inline(img)) for img in self.images],
            "api_key": self.api_key,
            "client_ip": self.client_ip,
            "user_agent": self.user_agent,
            "meta": self.meta,
            "raw": self.raw,
            "status": self.status,
            "claimed_at": self.claimed_at,
            "claimed_by": self.claimed_by,
            "typing": self.typing,
            "deltas": self.deltas,
            "reply_text": self.reply_text,
            "reply_reasoning": self.reply_reasoning,
            "reply_tools": self.reply_tools,
            "finish_reason": self.finish_reason,
            "rejected_reason": self.rejected_reason,
            "completed_at": self.completed_at,
            "usage_note": self.usage_note,
            "version": self.version,
        }

    @classmethod
    def from_json(cls, payload: Dict[str, Any]) -> "Job":
        job = cls(
            id=payload.get("id") or new_id(),
            protocol=payload.get("protocol") or "openai.chat",
            model=payload.get("model") or "",
            stream=bool(payload.get("stream")),
            created_at=float(payload.get("created_at") or now()),
        )
        job.request_model = payload.get("request_model") or job.model
        job.messages = payload.get("messages") or []
        job.tools = payload.get("tools") or []
        job.tool_choice = payload.get("tool_choice")
        job.params = payload.get("params") or {}
        job.images = payload.get("images") or []
        job.api_key = payload.get("api_key") or "anonymous"
        job.client_ip = payload.get("client_ip") or ""
        job.user_agent = payload.get("user_agent") or ""
        job.meta = payload.get("meta") or {}
        job.raw = payload.get("raw") or {}
        job.status = payload.get("status") or "pending"
        job.claimed_at = payload.get("claimed_at")
        job.claimed_by = payload.get("claimed_by")
        job.typing = bool(payload.get("typing"))
        job.deltas = payload.get("deltas") or []
        job.reply_text = payload.get("reply_text") or ""
        job.reply_reasoning = payload.get("reply_reasoning") or ""
        job.reply_tools = payload.get("reply_tools") or []
        job.finish_reason = payload.get("finish_reason")
        job.rejected_reason = payload.get("rejected_reason")
        job.completed_at = payload.get("completed_at")
        job.usage_note = payload.get("usage_note")
        job.version = int(payload.get("version") or 0)
        return job

    # -- 事件分发（操作台） ----------------------------------------------
    def _broadcast_locked(self, item: Dict[str, Any]) -> None:
        for bucket in list(self._subs):
            try:
                if bucket.full():
                    try:
                        bucket.get_nowait()
                    except queue.Empty:
                        pass
                bucket.put_nowait(item)
            except (queue.Full, ValueError):
                continue

    def subscribe(self) -> Any:
        bucket = queue.Queue(maxsize=_MAX_EVENT_QUEUE)
        with self._lock:
            self._subs.append(bucket)
        return bucket

    def unsubscribe(self, bucket: Any) -> None:
        with self._lock:
            if bucket in self._subs:
                self._subs.remove(bucket)


class JobStore:
    """Job 的内存索引 + 落盘存储 + 事件广播。"""

    def __init__(self, config: Any, data_dir: Path, logger: Any = None) -> None:
        self.config = config
        self.log = logger
        self.root = Path(data_dir)
        self.dir = self.root / "requests"
        self.dir.mkdir(parents=True, exist_ok=True)
        self.started_at = now()
        self._lock = threading.RLock()
        self._jobs: Dict[str, Job] = {}
        self._listeners: List[Any] = []
        self._last_persist: Dict[str, float] = {}
        self._persist_count = 0
        self._last_publish_at = 0.0
        self._stop = threading.Event()
        self._load()

    # -- 基础访问 --------------------------------------------------------
    def get(self, job_id: str) -> Optional[Job]:
        with self._lock:
            return self._jobs.get(job_id)

    def require(self, job_id: str) -> Job:
        job = self.get(job_id)
        if not job:
            raise not_found("请求不存在或已被清理")
        return job

    def pending_count(self) -> int:
        with self._lock:
            return sum(1 for job in self._jobs.values() if job.status == "pending")

    def active_count_for_key(self, key_name: str) -> int:
        with self._lock:
            return sum(
                1
                for job in self._jobs.values()
                if job.status in ACTIVE and job.api_key == key_name
            )

    def list(
        self,
        status: Optional[str] = None,
        limit: int = 60,
        search: str = "",
        show_ip: bool = True,
    ) -> List[Dict[str, Any]]:
        needle = (search or "").strip().lower()
        with self._lock:
            jobs = list(self._jobs.values())
        if status and status not in ("all", "*"):
            wanted = [item.strip() for item in status.split(",") if item.strip()]
            jobs = [job for job in jobs if job.status in wanted]
        if needle:
            jobs = [
                job
                for job in jobs
                if needle in job.id.lower()
                or needle in job.model.lower()
                or needle in (job.preview() or "").lower()
                or needle in job.protocol.lower()
            ]
        jobs.sort(key=lambda item: item.created_at, reverse=True)
        return [job.summary(show_ip=show_ip) for job in jobs[: max(1, min(limit, 200))]]

    # -- 创建 ------------------------------------------------------------
    def create(
        self,
        protocol: str,
        model: str,
        request_model: str,
        stream: bool,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        tool_choice: Any = None,
        params: Optional[Dict[str, Any]] = None,
        api_key: str = "anonymous",
        client_ip: str = "",
        user_agent: str = "",
        meta: Optional[Dict[str, Any]] = None,
        raw: Optional[Dict[str, Any]] = None,
    ) -> Job:
        if not messages:
            raise bad_request("messages 不能为空")
        max_pending = int(self.config.get("queue.max_pending", 100))
        max_per_key = int(self.config.get("queue.max_concurrent_per_key", 3))
        with self._lock:
            pending = sum(1 for job in self._jobs.values() if job.status == "pending")
            if pending >= max_pending:
                raise unavailable("待处理队列已满（%d），请稍后重试" % max_pending)
            if max_per_key > 0:
                active = sum(
                    1
                    for job in self._jobs.values()
                    if job.status in ACTIVE and job.api_key == api_key
                )
                if active >= max_per_key:
                    raise rate_limited(
                        "同一 API Key 并发请求已达上限（%d）" % max_per_key, retry_after=5
                    )
        images: List[Dict[str, Any]] = []
        for message in messages:
            images.extend(message.get("images") or [])
        job = Job(
            id=new_id("req_"),
            protocol=protocol,
            model=model,
            request_model=request_model or model,
            stream=bool(stream),
            created_at=now(),
            messages=messages,
            tools=tools or [],
            tool_choice=tool_choice,
            params=params or {},
            images=images,
            api_key=api_key,
            client_ip=client_ip,
            user_agent=user_agent,
            meta=meta or {},
            raw=raw or {},
        )
        with self._lock:
            self._jobs[job.id] = job
        self._persist(job, force=True)
        self._publish()
        if self.log:
            self.log.info(
                "新请求 %s model=%s protocol=%s key=%s images=%d",
                job.id,
                job.model,
                job.protocol,
                job.api_key,
                len(images),
            )
        return job

    # -- 状态迁移 --------------------------------------------------------
    def claim(self, job_id: str, actor: str) -> Job:
        job = self.require(job_id)
        with job._lock:
            if job.status in TERMINAL:
                raise bad_request("该请求已经结束，无法认领")
            job.status = "claimed"
            job.claimed_at = job.claimed_at or now()
            job.claimed_by = actor or "operator"
            job.version += 1
            _notify(job)
            job._broadcast_locked({"type": "state", "job": job.summary()})
        self._persist(job, force=True)
        self._publish()
        return job

    def release(self, job_id: str, actor: str = "") -> Job:
        job = self.require(job_id)
        with job._lock:
            if job.status in TERMINAL:
                raise bad_request("该请求已经结束，无法退回")
            job.status = "pending"
            job.claimed_at = None
            job.claimed_by = None
            job.typing = False
            job.version += 1
            _notify(job)
            job._broadcast_locked({"type": "state", "job": job.summary()})
        self._persist(job, force=True)
        self._publish()
        return job

    def set_typing(self, job_id: str, typing: bool) -> Job:
        job = self.require(job_id)
        if job.status in TERMINAL:
            raise bad_request("该请求已经结束")
        with job._lock:
            if job.typing == bool(typing):
                return job
            job.typing = bool(typing)
            job.version += 1
            job._broadcast_locked({"type": "typing", "id": job.id, "typing": job.typing})
        self._publish(force=False)
        return job

    def delta(self, job_id: str, text: str, actor: str = "", kind: str = "text") -> Job:
        """追加一段增量（正文或思考）并实时推给流式客户端。"""
        job = self.require(job_id)
        clean = (text or "").replace("\x00", "")
        if not clean:
            raise bad_request("增量内容不能为空")
        if kind not in ("text", "reasoning"):
            raise bad_request("kind 只能是 text 或 reasoning")
        max_chars = int(self.config.limits()["max_reply_chars"])
        with job._lock:
            if job.status in TERMINAL:
                raise bad_request("该请求已经结束，无法继续发送")
            if kind == "reasoning":
                if len(job.reply_reasoning) + len(clean) > max_chars:
                    raise bad_request("思考内容超过长度上限（%d 字符）" % max_chars)
                job.reply_reasoning += clean
            else:
                if len(job.reply_text) + len(clean) > max_chars:
                    raise bad_request("回复内容超过长度上限（%d 字符）" % max_chars)
                job.reply_text += clean
            if job.status == "pending":
                job.status = "claimed"
                job.claimed_at = now()
                job.claimed_by = actor or "operator"
            job.first_delta_at = job.first_delta_at or now()
            job.deltas.append({"kind": kind, "text": clean, "at": now()})
            job.version += 1
            _notify(job)
            job._broadcast_locked(
                {
                    "type": "delta",
                    "id": job.id,
                    "kind": kind,
                    "text": clean,
                    "version": job.version,
                }
            )
        self._persist(job)
        self._publish(force=False)
        return job

    def reply(
        self,
        job_id: str,
        text: Optional[str] = None,
        reasoning: Optional[str] = None,
        tool_calls: Optional[List[Dict[str, Any]]] = None,
        finish_reason: Optional[str] = None,
        usage_note: Optional[str] = None,
        actor: str = "",
    ) -> Job:
        """提交最终答复（可包含工具调用），并唤醒等待中的客户端。"""
        job = self.require(job_id)
        max_chars = int(self.config.limits()["max_reply_chars"])
        final_text = job.reply_text if text is None else (text or "").replace("\x00", "")
        final_reasoning = (
            job.reply_reasoning if reasoning is None else (reasoning or "").replace("\x00", "")
        )
        if len(final_text) > max_chars:
            raise bad_request("回复内容超过长度上限（%d 字符）" % max_chars)
        if len(final_reasoning) > max_chars:
            raise bad_request("思考内容超过长度上限（%d 字符）" % max_chars)
        normalized_calls = []
        for index, call in enumerate(tool_calls or []):
            if not isinstance(call, dict):
                raise bad_request("tool_calls[%d] 必须是对象" % index)
            name = str(call.get("name") or "").strip()
            if not name:
                raise bad_request("tool_calls[%d] 缺少 name" % index)
            arguments = call.get("arguments")
            if arguments is None:
                arguments = call.get("arguments_json")
            if isinstance(arguments, (dict, list)):
                arguments_text = json.dumps(arguments, ensure_ascii=False)
                arguments_json = arguments
            else:
                arguments_text = str(arguments or "{}")
                try:
                    arguments_json = json.loads(arguments_text)
                except (ValueError, TypeError):
                    raise bad_request("tool_calls[%d].arguments 不是合法 JSON" % index)
            normalized_calls.append(
                {
                    "id": str(call.get("id") or new_id("call_")),
                    "name": name[:64],
                    "arguments": arguments_text,
                    "arguments_json": arguments_json,
                }
            )
        if not final_text and not final_reasoning and not normalized_calls:
            raise bad_request("回复内容、思考内容与工具调用不能同时为空")
        with job._lock:
            if job.status in TERMINAL:
                raise bad_request("该请求已经结束")
            if job.status == "pending":
                job.claimed_at = now()
                job.claimed_by = actor or "operator"
            job.reply_text = final_text
            job.reply_reasoning = final_reasoning
            job.reply_tools = normalized_calls
            job.finish_reason = finish_reason or ("tool_calls" if normalized_calls else "stop")
            job.usage_note = usage_note
            job.status = "answered"
            job.completed_at = now()
            job.typing = False
            job.version += 1
            _notify(job)
            job._broadcast_locked({"type": "state", "job": job.summary()})
        self._persist(job, force=True)
        self._publish()
        if self.log:
            latency = (job.completed_at or now()) - job.created_at
            self.log.info("已答复 %s（耗时 %.1fs）", job.id, latency)
        return job

    def reject(self, job_id: str, reason: str = "", actor: str = "") -> Job:
        job = self.require(job_id)
        with job._lock:
            if job.status in TERMINAL:
                raise bad_request("该请求已经结束")
            job.status = "rejected"
            job.rejected_reason = truncate(reason or "操作员拒绝了该请求", 300)
            job.completed_at = now()
            job.typing = False
            job.version += 1
            _notify(job)
            job._broadcast_locked({"type": "state", "job": job.summary()})
        self._persist(job, force=True)
        self._publish()
        return job

    def cancel(self, job_id: str, reason: str = "client_disconnected") -> Job:
        job = self.require(job_id)
        with job._lock:
            if job.status in TERMINAL:
                return job
            job.status = "cancelled"
            job.rejected_reason = reason
            job.completed_at = now()
            job.typing = False
            job.version += 1
            _notify(job)
            job._broadcast_locked({"type": "state", "job": job.summary()})
        self._persist(job, force=True)
        self._publish()
        return job

    def expire(self, job: Job, reason: str = "timeout") -> Job:
        with job._lock:
            if job.status in TERMINAL:
                return job
            job.status = "expired"
            job.rejected_reason = reason
            job.completed_at = now()
            job.typing = False
            job.version += 1
            _notify(job)
            job._broadcast_locked({"type": "state", "job": job.summary()})
        self._persist(job, force=True)
        self._publish()
        return job

    # -- 等待 ------------------------------------------------------------
    def wait(self, job: Job, timeout: Optional[float] = None) -> Job:
        """阻塞等待终态；超时则标记 expired 并抛错。"""
        if timeout is None:
            timeout = float(self.config.get("queue.request_ttl_seconds", 600))
        deadline = now() + max(1.0, timeout)
        with job._cv:
            while job.status not in TERMINAL:
                remaining = deadline - now()
                if remaining <= 0:
                    break
                job._cv.wait(min(remaining, 0.5))
        if job.status == "answered":
            return job
        if job.status in TERMINAL:
            if job.status == "rejected":
                raise unavailable(job.rejected_reason or "操作员拒绝了该请求")
            if job.status == "cancelled":
                raise unavailable("请求已被取消")
            raise timeout_error(job.rejected_reason or "请求已过期")
        self.expire(job, reason="等待超时，操作员未响应")
        raise timeout_error("等待超时：操作员在 %.0f 秒内未响应" % timeout)

    # -- 统计 ------------------------------------------------------------
    def stats(self) -> Dict[str, Any]:
        with self._lock:
            jobs = list(self._jobs.values())
        counts = {name: 0 for name in ("pending", "claimed", "answered", "rejected", "expired", "cancelled")}
        latencies = []
        answered_today = 0
        midnight = time.time() - (time.time() % 86400)
        for job in jobs:
            counts[job.status] = counts.get(job.status, 0) + 1
            if job.status == "answered" and job.completed_at:
                latencies.append(job.completed_at - job.created_at)
                if job.completed_at >= midnight:
                    answered_today += 1
        average = round(sum(latencies) / len(latencies), 1) if latencies else 0.0
        return {
            "pending": counts.get("pending", 0),
            "claimed": counts.get("claimed", 0),
            "answered": counts.get("answered", 0),
            "rejected": counts.get("rejected", 0),
            "expired": counts.get("expired", 0),
            "cancelled": counts.get("cancelled", 0),
            "total": len(jobs),
            "answered_today": answered_today,
            "avg_reply_seconds": average,
            "uptime_seconds": round(now() - self.started_at, 1),
            "capacity": int(self.config.get("queue.max_pending", 100)),
        }

    # -- 操作台事件流 ----------------------------------------------------
    def subscribe_events(self) -> Any:
        bucket = queue.Queue(maxsize=_MAX_EVENT_QUEUE)
        with self._lock:
            self._listeners.append(bucket)
        return bucket

    def unsubscribe_events(self, bucket: Any) -> None:
        with self._lock:
            if bucket in self._listeners:
                self._listeners.remove(bucket)

    def _publish(self, force: bool = True) -> None:
        """广播队列快照；高频事件（增量/输入中）做 0.5 秒节流。"""
        current = now()
        with self._lock:
            if not force and current - self._last_publish_at < 0.5:
                return
            self._last_publish_at = current
        payload = {
            "type": "queue",
            "jobs": self.list(status="all", limit=80, show_ip=False),
            "stats": self.stats(),
        }
        with self._lock:
            listeners = list(self._listeners)
        for bucket in listeners:
            try:
                if bucket.full():
                    try:
                        bucket.get_nowait()
                    except queue.Empty:
                        pass
                bucket.put_nowait(payload)
            except (queue.Full, ValueError):
                continue

    # -- 落盘 ------------------------------------------------------------
    def _persist(self, job: Job, force: bool = False) -> None:
        current = now()
        last = self._last_persist.get(job.id, 0.0)
        if not force and job.status not in TERMINAL and current - last < 2.0:
            return
        self._last_persist[job.id] = current
        persist_media = bool(self.config.get("queue.persist_media", False))
        target = self.dir / (job.id + ".json")
        temp = self.dir / ("%s.%d.%d.tmp" % (job.id, os.getpid(), threading.get_ident()))
        try:
            payload = json.dumps(job.to_json(persist_media=persist_media), ensure_ascii=False)
        except (TypeError, ValueError) as exc:
            if self.log:
                self.log.warning("请求序列化失败 %s: %s", job.id, exc)
            return
        for attempt in range(3):
            try:
                temp.write_text(payload, "utf-8")
                os.replace(str(temp), str(target))
                break
            except OSError as exc:
                if attempt == 2:
                    if self.log:
                        self.log.warning("请求落盘失败 %s: %s", job.id, exc)
                    return
                time.sleep(0.05)
        self._persist_count += 1
        if job.status in TERMINAL and self._persist_count % 10 == 0:
            self._prune_files()

    def _prune_files(self) -> None:
        limit = int(self.config.get("queue.history_limit", 300))
        try:
            files = sorted(self.dir.glob("req_*.json"), key=lambda item: item.stat().st_mtime, reverse=True)
        except OSError:
            return
        for stale in files[limit:]:
            try:
                stale.unlink()
            except OSError:
                continue
        with self._lock:
            if len(self._jobs) > limit * 2:
                ordered = sorted(self._jobs.values(), key=lambda item: item.created_at)
                for job in ordered[: len(self._jobs) - limit]:
                    if job.status in TERMINAL:
                        self._jobs.pop(job.id, None)

    def _load(self) -> None:
        limit = int(self.config.get("queue.history_limit", 300))
        ttl = float(self.config.get("queue.request_ttl_seconds", 600))
        try:
            files = sorted(
                self.dir.glob("req_*.json"),
                key=lambda item: item.stat().st_mtime,
                reverse=True,
            )[:limit]
        except OSError:
            return
        restored = 0
        for path in files:
            try:
                payload = json.loads(path.read_text("utf-8"))
                job = Job.from_json(payload)
            except (OSError, ValueError, TypeError) as exc:
                if self.log:
                    self.log.warning("恢复请求失败 %s: %s", path.name, exc)
                continue
            if job.status in ACTIVE:
                if now() - job.created_at > ttl:
                    job.status = "expired"
                    job.rejected_reason = "服务重启后已过期"
                    job.completed_at = now()
                else:
                    job.status = "pending"
                    job.claimed_at = None
                    job.claimed_by = None
                    job.typing = False
                    job.meta = dict(job.meta or {})
                    job.meta["restored"] = True
            self._jobs[job.id] = job
            restored += 1
        if restored and self.log:
            self.log.info("已恢复 %d 条历史请求", restored)

    def shutdown(self) -> None:
        self._stop.set()
