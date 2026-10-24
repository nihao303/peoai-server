"""OpenAI 兼容协议：/v1/chat/completions、/v1/completions、/v1/responses、/v1/models。"""
from __future__ import annotations

import json
import queue as queue_module
import time
from typing import Any, Dict, Iterable, Iterator, List, Optional

from ..errors import bad_request, unsupported
from ..images import collect, media_from_url
from ..store import TERMINAL, Job
from ..tokens import usage_for
from .common import (
    Normalized,
    collect_params,
    enforce_limits,
    flatten_parts,
    make_message,
    normalize_arguments,
    normalize_tool_choice,
    normalize_tools,
    now_created,
    should_include_usage,
    sse,
    sse_done,
    sse_keepalive,
)

PROTOCOL = "openai.chat"
LABEL = "OpenAI Chat Completions"

FINISH_MAP = {
    "stop": "stop",
    "length": "length",
    "tool_calls": "tool_calls",
    "content_filter": "content_filter",
}


def _parse_chat_messages(raw_messages: Any, limits: Dict[str, int]) -> List[Dict[str, Any]]:
    if not isinstance(raw_messages, list) or not raw_messages:
        raise bad_request("messages 必须是非空数组")
    if len(raw_messages) > limits["max_messages"]:
        raise bad_request("消息条数超过上限（%d）" % limits["max_messages"])
    messages: List[Dict[str, Any]] = []
    for index, raw in enumerate(raw_messages):
        if not isinstance(raw, dict):
            raise bad_request("messages[%d] 必须是对象" % index)
        role = str(raw.get("role") or "user").lower()
        if role == "developer":
            role = "system"
        if role == "function":
            role = "tool"
        if role not in ("system", "user", "assistant", "tool"):
            role = "user"
        images: List[Dict[str, Any]] = []
        text = flatten_parts(raw.get("content"), limits, images, "messages[%d].content" % index)
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
                role=role,
                text=text,
                images=images,
                tool_calls=tool_calls,
                tool_call_id=str(raw.get("tool_call_id") or ""),
                name=str(raw.get("name") or ""),
            )
        )
    return messages


def parse_chat(body: Dict[str, Any], limits: Dict[str, int]) -> Normalized:
    """解析 /v1/chat/completions 请求体。"""
    messages = _parse_chat_messages(body.get("messages"), limits)
    enforce_limits(messages, limits)
    tools = normalize_tools(body.get("tools"), "openai")
    params = collect_params(
        body,
        (
            "temperature",
            "top_p",
            "max_tokens",
            "max_completion_tokens",
            "stop",
            "presence_penalty",
            "frequency_penalty",
            "seed",
            "response_format",
            "reasoning_effort",
            "n",
            "stream_options",
            "user",
            "logit_bias",
            "parallel_tool_calls",
            "service_tier",
        ),
    )
    if "max_completion_tokens" in params and "max_tokens" not in params:
        params["max_tokens"] = params["max_completion_tokens"]
    choices = params.get("n", 1)
    try:
        choices = int(choices)
    except (TypeError, ValueError):
        raise bad_request("n 必须是整数")
    if choices != 1:
        raise unsupported("真人操作员一次只能生成一个候选，n 仅支持 1")
    if "temperature" in params:
        try:
            value = float(params["temperature"])
        except (TypeError, ValueError):
            raise bad_request("temperature 必须是数字")
        if value != value or value < 0 or value > 2:
            raise bad_request("temperature 必须在 0 到 2 之间")
    return Normalized(
        model=str(body.get("model") or "").strip(),
        messages=messages,
        tools=tools,
        tool_choice=normalize_tool_choice(body.get("tool_choice"), "openai"),
        params=params,
        stream=bool(body.get("stream")),
        meta={"dimensions": body.get("dimensions"), "user": body.get("user")},
    )


def parse_completions(body: Dict[str, Any], limits: Dict[str, int]) -> Normalized:
    """解析旧版 /v1/completions（prompt 补全）。"""
    prompt = body.get("prompt")
    if isinstance(prompt, list):
        prompt = "\n".join(str(item) for item in prompt)
    if not isinstance(prompt, str) or not prompt.strip():
        raise bad_request("prompt 必须是非空字符串")
    messages = [make_message("user", prompt)]
    enforce_limits(messages, limits)
    return Normalized(
        model=str(body.get("model") or "").strip(),
        messages=messages,
        tools=[],
        tool_choice=None,
        params=collect_params(
            body,
            ("temperature", "top_p", "max_tokens", "stop", "presence_penalty", "frequency_penalty", "n"),
        ),
        stream=bool(body.get("stream")),
        meta={"legacy": True},
    )


def parse_responses(body: Dict[str, Any], limits: Dict[str, int]) -> Normalized:
    """解析 /v1/responses（OpenAI Responses API 的核心子集）。"""
    raw_input = body.get("input")
    messages: List[Dict[str, Any]] = []
    if isinstance(raw_input, str):
        messages.append(make_message("user", raw_input))
    elif isinstance(raw_input, list):
        for index, item in enumerate(raw_input):
            if isinstance(item, str):
                messages.append(make_message("user", item))
                continue
            if not isinstance(item, dict):
                raise bad_request("input[%d] 必须是对象" % index)
            role = str(item.get("role") or "user").lower()
            if role == "developer":
                role = "system"
            images: List[Dict[str, Any]] = []
            if "content" in item:
                text = flatten_parts(item.get("content"), limits, images, "input[%d].content" % index)
            else:
                text = str(item.get("text") or "")
            if role == "assistant":
                messages.append(make_message("assistant", text))
            elif role in ("system", "user"):
                messages.append(make_message(role, text, images))
    else:
        raise bad_request("input 必须是字符串或数组")
    instructions = body.get("instructions")
    if isinstance(instructions, str) and instructions.strip():
        messages.insert(0, make_message("system", instructions))
    enforce_limits(messages, limits)
    tools = normalize_tools(body.get("tools"), "openai")
    return Normalized(
        model=str(body.get("model") or "").strip(),
        messages=messages,
        tools=tools,
        tool_choice=normalize_tool_choice(body.get("tool_choice"), "openai"),
        params=collect_params(
            body,
            ("temperature", "top_p", "max_output_tokens", "max_tokens", "reasoning", "text", "metadata", "parallel_tool_calls"),
        ),
        stream=bool(body.get("stream")),
        meta={
            "api": "responses",
            "user": (body.get("metadata") or {}).get("user") if isinstance(body.get("metadata"), dict) else body.get("user"),
        },
    )


def uses_vision(messages: Iterable[Dict[str, Any]]) -> bool:
    return any(message.get("images") for message in messages)


# ---------------------------------------------------------------------------
# 渲染
# ---------------------------------------------------------------------------

def _tool_call_payload(calls: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [
        {
            "id": call.get("id") or "",
            "type": "function",
            "function": {"name": call.get("name", ""), "arguments": call.get("arguments", "{}")},
        }
        for call in calls
    ]


def response_payload(job: Job, usage: Dict[str, int]) -> Dict[str, Any]:
    """非流式 chat.completion 响应。"""
    calls = _tool_call_payload(job.reply_tools)
    message: Dict[str, Any] = {"role": "assistant", "content": job.reply_text or (None if calls else "")}
    if job.reply_reasoning:
        message["reasoning_content"] = job.reply_reasoning
    if calls:
        message["tool_calls"] = calls
    return {
        "id": "chatcmpl-" + job.id[4:],
        "object": "chat.completion",
        "created": int(job.created_at),
        "model": job.model,
        "system_fingerprint": "peoai-human",
        "choices": [
            {
                "index": 0,
                "message": message,
                "logprobs": None,
                "finish_reason": FINISH_MAP.get(job.finish_reason or "", "stop"),
            }
        ],
        "usage": usage,
    }


def completions_payload(job: Job, usage: Dict[str, int]) -> Dict[str, Any]:
    """非流式旧版 text_completion 响应。"""
    return {
        "id": "cmpl-" + job.id[4:],
        "object": "text_completion",
        "created": int(job.created_at),
        "model": job.model,
        "choices": [
            {
                "index": 0,
                "text": job.reply_text,
                "logprobs": None,
                "finish_reason": "stop",
            }
        ],
        "usage": usage,
    }


def _chunk(job: Job, model: str, delta: Dict[str, Any], finish: Optional[str] = None) -> Dict[str, Any]:
    return {
        "id": "chatcmpl-" + job.id[4:],
        "object": "chat.completion.chunk",
        "created": int(job.created_at),
        "model": model,
        "system_fingerprint": "peoai-human",
        "choices": [{"index": 0, "delta": delta, "logprobs": None, "finish_reason": finish}],
    }


def chat_stream(job: Job) -> Iterator[str]:
    """流式 chat.completion.chunk（SSE）。

    设计：增量统一从 job.deltas 读取，事件队列只用于唤醒，
    因此中途重连的客户端也能补齐历史文本。
    """
    bucket = job.subscribe()
    sent = 0
    emitted_text = ""
    emitted_reasoning = ""
    keepalive = 15.0
    try:
        yield sse(_chunk(job, job.model, {"role": "assistant", "content": ""}))
        while True:
            while sent < len(job.deltas):
                item = job.deltas[sent]
                sent += 1
                text = item.get("text", "")
                kind = item.get("kind", "text")
                if not text:
                    continue
                if kind == "reasoning":
                    emitted_reasoning += text
                    yield sse(_chunk(job, job.model, {"reasoning_content": text}))
                else:
                    emitted_text += text
                    yield sse(_chunk(job, job.model, {"content": text}))
            if job.status in TERMINAL:
                break
            try:
                bucket.get(timeout=keepalive)
            except queue_module.Empty:
                yield sse_keepalive()
                continue
        if job.status == "answered":
            remaining_reasoning = job.reply_reasoning
            if emitted_reasoning and remaining_reasoning.startswith(emitted_reasoning):
                remaining_reasoning = remaining_reasoning[len(emitted_reasoning):]
            if remaining_reasoning:
                yield sse(_chunk(job, job.model, {"reasoning_content": remaining_reasoning}))
            remainder = job.reply_text
            if emitted_text and remainder.startswith(emitted_text):
                remainder = remainder[len(emitted_text):]
            if remainder:
                yield sse(_chunk(job, job.model, {"content": remainder}))
            calls = _tool_call_payload(job.reply_tools)
            if calls:
                yield sse(
                    _chunk(
                        job,
                        job.model,
                        {
                            "tool_calls": [
                                {"index": index, **call} for index, call in enumerate(calls)
                            ]
                        },
                    )
                )
            finish = FINISH_MAP.get(job.finish_reason or "", "stop")
            yield sse(_chunk(job, job.model, {}, finish))
            usage = usage_for(job.messages, job.reply_text, job.tools, job.reply_tools)
            if should_include_usage(job):
                yield sse(
                    {
                        "id": "chatcmpl-" + job.id[4:],
                        "object": "chat.completion.chunk",
                        "created": int(job.created_at),
                        "model": job.model,
                        "choices": [],
                        "usage": usage,
                    }
                )
        else:
            yield sse(
                {
                    "error": {
                        "message": job.rejected_reason or "操作员未能按时作答",
                        "type": "timeout_error" if job.status == "expired" else "service_unavailable_error",
                        "code": job.status,
                    }
                }
            )
        yield sse_done()
    finally:
        job.unsubscribe(bucket)


def completions_stream(job: Job) -> Iterator[str]:
    """旧版 /v1/completions 的流式响应。"""
    bucket = job.subscribe()
    sent = 0
    emitted = ""
    try:
        while True:
            while sent < len(job.deltas):
                text = job.deltas[sent].get("text", "")
                sent += 1
                emitted += text
                if text:
                    yield sse(
                        {
                            "id": "cmpl-" + job.id[4:],
                            "object": "text_completion",
                            "created": int(job.created_at),
                            "model": job.model,
                            "choices": [{"index": 0, "text": text, "logprobs": None, "finish_reason": None}],
                        }
                    )
            if job.status in TERMINAL:
                break
            try:
                bucket.get(timeout=15.0)
            except queue_module.Empty:
                yield sse_keepalive()
        if job.status == "answered":
            remainder = job.reply_text
            if emitted and remainder.startswith(emitted):
                remainder = remainder[len(emitted):]
            if remainder:
                yield sse(
                    {
                        "id": "cmpl-" + job.id[4:],
                        "object": "text_completion",
                        "created": int(job.created_at),
                        "model": job.model,
                        "choices": [{"index": 0, "text": remainder, "logprobs": None, "finish_reason": None}],
                    }
                )
            yield sse(
                {
                    "id": "cmpl-" + job.id[4:],
                    "object": "text_completion",
                    "created": int(job.created_at),
                    "model": job.model,
                    "choices": [{"index": 0, "text": "", "logprobs": None, "finish_reason": "stop"}],
                }
            )
        else:
            yield sse({"error": {"message": job.rejected_reason or "未作答", "code": job.status}})
        yield sse_done()
    finally:
        job.unsubscribe(bucket)


# ---------------------------------------------------------------------------
# Responses API
# ---------------------------------------------------------------------------

def responses_object(job: Job, usage: Dict[str, int]) -> Dict[str, Any]:
    """非流式 Responses API 响应对象。"""
    content: List[Dict[str, Any]] = []
    if job.reply_text:
        content.append({"type": "output_text", "text": job.reply_text, "annotations": []})
    output: List[Dict[str, Any]] = []
    if content:
        output.append(
            {
                "type": "message",
                "id": "msg_" + job.id[4:],
                "status": "completed",
                "role": "assistant",
                "content": content,
            }
        )
    for call in job.reply_tools:
        output.append(
            {
                "type": "function_call",
                "id": "fc_" + str(call.get("id") or "")[:24],
                "call_id": call.get("id") or "",
                "name": call.get("name", ""),
                "arguments": call.get("arguments", "{}"),
                "status": "completed",
            }
        )
    return {
        "id": "resp_" + job.id[4:],
        "object": "response",
        "created_at": int(job.created_at),
        "status": "completed",
        "model": job.model,
        "output": output,
        "parallel_tool_calls": True,
        "tool_choice": job.tool_choice or "auto",
        "usage": {
            "input_tokens": usage["prompt_tokens"],
            "output_tokens": usage["completion_tokens"],
            "total_tokens": usage["total_tokens"],
        },
        "metadata": {},
    }


def responses_stream(job: Job) -> Iterator[str]:
    """Responses API 的简化事件流。"""
    bucket = job.subscribe()
    sent = 0
    emitted = ""
    response_id = "resp_" + job.id[4:]
    item_id = "msg_" + job.id[4:]
    base = {
        "id": response_id,
        "object": "response",
        "created_at": int(job.created_at),
        "model": job.model,
        "status": "in_progress",
        "output": [],
    }
    try:
        yield sse({"type": "response.created", "response": base})
        yield sse(
            {
                "type": "response.output_item.added",
                "output_index": 0,
                "item": {"type": "message", "id": item_id, "status": "in_progress", "role": "assistant", "content": []},
            }
        )
        yield sse(
            {
                "type": "response.content_part.added",
                "item_id": item_id,
                "output_index": 0,
                "content_index": 0,
                "part": {"type": "output_text", "text": "", "annotations": []},
            }
        )
        while True:
            while sent < len(job.deltas):
                text = job.deltas[sent].get("text", "")
                sent += 1
                emitted += text
                if text:
                    yield sse(
                        {
                            "type": "response.output_text.delta",
                            "item_id": item_id,
                            "output_index": 0,
                            "content_index": 0,
                            "delta": text,
                        }
                    )
            if job.status in TERMINAL:
                break
            try:
                bucket.get(timeout=15.0)
            except queue_module.Empty:
                yield sse_keepalive()
        if job.status == "answered":
            remainder = job.reply_text
            if emitted and remainder.startswith(emitted):
                remainder = remainder[len(emitted):]
            if remainder:
                yield sse(
                    {
                        "type": "response.output_text.delta",
                        "item_id": item_id,
                        "output_index": 0,
                        "content_index": 0,
                        "delta": remainder,
                    }
                )
            final = responses_object(job, usage_for(job.messages, job.reply_text, job.tools, job.reply_tools))
            yield sse(
                {
                    "type": "response.output_text.done",
                    "item_id": item_id,
                    "output_index": 0,
                    "content_index": 0,
                    "text": job.reply_text,
                }
            )
            yield sse(
                {
                    "type": "response.content_part.done",
                    "item_id": item_id,
                    "output_index": 0,
                    "content_index": 0,
                    "part": {"type": "output_text", "text": job.reply_text, "annotations": []},
                }
            )
            for index, item in enumerate(final["output"]):
                yield sse({"type": "response.output_item.done", "output_index": index, "item": item})
            final["status"] = "completed"
            yield sse({"type": "response.completed", "response": final})
        else:
            failed = dict(base)
            failed["status"] = "failed"
            failed["error"] = {"code": job.status, "message": job.rejected_reason or "未作答"}
            yield sse({"type": "response.failed", "response": failed})
    finally:
        job.unsubscribe(bucket)


def models_payload(models: List[Dict[str, Any]]) -> Dict[str, Any]:
    """OpenAI /v1/models 列表，附带标准容量字段与 x_peoai 扩展。

    除了 x_peoai 扩展，顶层也给出 context_window / max_output_tokens /
    capabilities / input_modalities，方便只读取标准字段的 Agent 客户端
    （例如 DSH）直接拿到模型能力，而不是退回默认值。
    """
    created = 1700000000
    data = []
    for model in models:
        caps = model.get("capabilities") or {}
        context_window = model.get("context_window")
        max_output_tokens = model.get("max_output_tokens")
        input_modalities = ["text"]
        if caps.get("vision"):
            input_modalities.append("image")
        item = {
            "id": model["id"],
            "object": "model",
            "created": created,
            "owned_by": "peoai",
            "permission": [],
            "root": model["id"],
            "parent": None,
            "label": model.get("label"),
            "description": model.get("description"),
            "capabilities": caps,
            "context_window": context_window,
            "context_length": context_window,
            "contextWindow": context_window,
            "max_output_tokens": max_output_tokens,
            "max_tokens": max_output_tokens,
            "maxOutputTokens": max_output_tokens,
            "maxTokens": max_output_tokens,
            "input_modalities": input_modalities,
            "inputModalities": input_modalities,
            "x_peoai": {
                "label": model.get("label"),
                "description": model.get("description"),
                "capabilities": caps,
                "context_window": context_window,
                "max_output_tokens": max_output_tokens,
                "input_modalities": input_modalities,
            },
        }
        data.append(item)
    return {"object": "list", "data": data}
