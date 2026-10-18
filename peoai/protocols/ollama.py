"""Ollama 兼容协议：/api/chat、/api/tags、/api/version、/api/show。"""
from __future__ import annotations

import json
import queue as queue_module
from typing import Any, Dict, Iterator, List

from ..errors import bad_request
from ..images import collect, media_from_base64
from ..store import TERMINAL, Job
from ..tokens import usage_for
from ..util import iso_time, now
from .common import (
    Normalized,
    collect_params,
    enforce_limits,
    make_message,
    normalize_arguments,
    normalize_tools,
)

PROTOCOL = "ollama.chat"
LABEL = "Ollama Chat"


def parse_chat(body: Dict[str, Any], limits: Dict[str, int]) -> Normalized:
    """解析 Ollama /api/chat 请求体。"""
    raw_messages = body.get("messages")
    if not isinstance(raw_messages, list) or not raw_messages:
        raise bad_request("messages 必须是非空数组")
    messages: List[Dict[str, Any]] = []
    for index, raw in enumerate(raw_messages):
        if not isinstance(raw, dict):
            raise bad_request("messages[%d] 必须是对象" % index)
        role = str(raw.get("role") or "user").lower()
        if role not in ("system", "user", "assistant", "tool"):
            role = "user"
        images: List[Dict[str, Any]] = []
        for image_index, item in enumerate(raw.get("images") or []):
            if isinstance(item, str):
                collect(media_from_base64(item, "image/png", limits), images, limits)
            else:
                raise bad_request("messages[%d].images[%d] 必须是 base64 字符串" % (index, image_index))
        tool_calls: List[Dict[str, Any]] = []
        for call_index, call in enumerate(raw.get("tool_calls") or []):
            if not isinstance(call, dict):
                raise bad_request("messages[%d].tool_calls[%d] 必须是对象" % (index, call_index))
            function = call.get("function") if isinstance(call.get("function"), dict) else {}
            name = str(function.get("name") or call.get("name") or "").strip()
            if not name:
                raise bad_request("messages[%d].tool_calls[%d] 缺少函数名" % (index, call_index))
            arguments_text, arguments_json = normalize_arguments(function.get("arguments", call.get("arguments")))
            tool_calls.append(
                {
                    "id": str(call.get("id") or ""),
                    "name": name,
                    "arguments": arguments_text,
                    "arguments_json": arguments_json,
                }
            )
        messages.append(
            make_message(
                role,
                str(raw.get("content") or ""),
                images,
                tool_calls=tool_calls,
                tool_call_id=str(raw.get("tool_call_id") or ""),
                name=str(raw.get("tool_name") or ""),
            )
        )
    enforce_limits(messages, limits)
    options = body.get("options") if isinstance(body.get("options"), dict) else {}
    params = collect_params(options, ("temperature", "top_p", "top_k", "num_predict", "stop", "seed"))
    if "num_predict" in params and "max_tokens" not in params:
        params["max_tokens"] = params["num_predict"]
    return Normalized(
        model=str(body.get("model") or "").strip(),
        messages=messages,
        tools=normalize_tools(body.get("tools"), "openai"),
        tool_choice=None,
        params=params,
        # Ollama 默认 stream=true
        stream=bool(body.get("stream", True)),
        meta={"api": "ollama.chat"},
    )


def message_payload(job: Job) -> Dict[str, Any]:
    message: Dict[str, Any] = {"role": "assistant", "content": job.reply_text}
    if job.reply_reasoning:
        message["thinking"] = job.reply_reasoning
    if job.reply_tools:
        message["tool_calls"] = [
            {
                "function": {
                    "name": call.get("name", ""),
                    "arguments": call.get("arguments_json")
                    if isinstance(call.get("arguments_json"), dict)
                    else {},
                }
            }
            for call in job.reply_tools
        ]
    return message


def response_payload(job: Job, usage: Dict[str, int]) -> Dict[str, Any]:
    """非流式 /api/chat 响应。"""
    duration = int(((job.completed_at or now()) - job.created_at) * 1e9)
    return {
        "model": job.model,
        "created_at": iso_time(job.created_at),
        "message": message_payload(job),
        "done": True,
        "done_reason": "stop",
        "total_duration": duration,
        "load_duration": 0,
        "prompt_eval_count": usage["prompt_tokens"],
        "prompt_eval_duration": 0,
        "eval_count": usage["completion_tokens"],
        "eval_duration": 0,
    }


def ndjson_stream(job: Job) -> Iterator[str]:
    """Ollama NDJSON 流式响应（每行一个 JSON）。"""
    bucket = job.subscribe()
    sent = 0
    emitted_text = ""
    emitted_reasoning = ""
    try:
        while True:
            while sent < len(job.deltas):
                item = job.deltas[sent]
                sent += 1
                text = item.get("text", "")
                kind = item.get("kind", "text")
                if not text:
                    continue
                message = {"role": "assistant", "content": ""}
                if kind == "reasoning":
                    emitted_reasoning += text
                    message["thinking"] = text
                else:
                    emitted_text += text
                    message["content"] = text
                yield json.dumps(
                    {
                        "model": job.model,
                        "created_at": iso_time(now()),
                        "message": message,
                        "done": False,
                    },
                    ensure_ascii=False,
                ) + "\n"
            if job.status in TERMINAL:
                break
            try:
                bucket.get(timeout=15.0)
            except queue_module.Empty:
                yield "\n"
        if job.status == "answered":
            remaining_reasoning = job.reply_reasoning
            if emitted_reasoning and remaining_reasoning.startswith(emitted_reasoning):
                remaining_reasoning = remaining_reasoning[len(emitted_reasoning):]
            if remaining_reasoning:
                yield json.dumps(
                    {
                        "model": job.model,
                        "created_at": iso_time(now()),
                        "message": {
                            "role": "assistant",
                            "content": "",
                            "thinking": remaining_reasoning,
                        },
                        "done": False,
                    },
                    ensure_ascii=False,
                ) + "\n"
            remainder = job.reply_text
            if emitted_text and remainder.startswith(emitted_text):
                remainder = remainder[len(emitted_text):]
            if remainder:
                yield json.dumps(
                    {
                        "model": job.model,
                        "created_at": iso_time(now()),
                        "message": {"role": "assistant", "content": remainder},
                        "done": False,
                    },
                    ensure_ascii=False,
                ) + "\n"
            usage = usage_for(job.messages, job.reply_text, job.tools, job.reply_tools)
            final = {
                "model": job.model,
                "created_at": iso_time(now()),
                "message": message_payload(job),
                "done": True,
                "done_reason": "stop",
                "prompt_eval_count": usage["prompt_tokens"],
                "eval_count": usage["completion_tokens"],
            }
            yield json.dumps(final, ensure_ascii=False) + "\n"
        else:
            yield json.dumps(
                {
                    "model": job.model,
                    "created_at": iso_time(now()),
                    "message": {"role": "assistant", "content": ""},
                    "done": True,
                    "error": job.rejected_reason or "操作员未能按时作答",
                },
                ensure_ascii=False,
            ) + "\n"
    finally:
        job.unsubscribe(bucket)


def tags_payload(models: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Ollama /api/tags 模型列表。"""
    result = []
    for model in models:
        result.append(
            {
                "name": model["id"] + ":latest",
                "model": model["id"] + ":latest",
                "modified_at": iso_time(1700000000),
                "size": 0,
                "digest": "peoai-human-" + model["id"],
                "details": {
                    "parent_model": "",
                    "format": "peoai",
                    "family": "human",
                    "families": ["human"],
                    "parameter_size": "1h",
                    "quantization_level": "human-in-the-loop",
                },
            }
        )
    return {"models": result}


def show_payload(model: Dict[str, Any]) -> Dict[str, Any]:
    """Ollama /api/show 模型详情。"""
    return {
        "modelfile": "# PeoAI human-backed model\n",
        "parameters": "temperature 0.7",
        "template": "{{ .Prompt }}",
        "details": {
            "parent_model": "",
            "format": "peoai",
            "family": "human",
            "families": ["human"],
            "parameter_size": "1h",
            "quantization_level": "human-in-the-loop",
        },
        "model_info": {
            "general.architecture": "human",
            "peoai.capabilities": model.get("capabilities"),
            "peoai.context_window": model.get("context_window"),
        },
    }
