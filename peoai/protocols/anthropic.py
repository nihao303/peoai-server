"""Anthropic Messages 协议：/v1/messages 及其流式事件。"""
from __future__ import annotations

import json
import queue as queue_module
from typing import Any, Dict, Iterator, List, Optional

from ..errors import bad_request, unsupported
from ..images import collect, media_from_base64, media_from_url
from ..store import TERMINAL, Job
from ..tokens import estimate_messages, estimate_tokens, usage_for
from .common import (
    Normalized,
    collect_params,
    enforce_limits,
    flatten_parts,
    make_message,
    normalize_arguments,
    normalize_tool_choice,
    normalize_tools,
    sse_keepalive,
    sse_named,
)

PROTOCOL = "anthropic.messages"
LABEL = "Anthropic Messages"


def parse_messages(body: Dict[str, Any], limits: Dict[str, int]) -> Normalized:
    """解析 Anthropic /v1/messages 请求体。"""
    raw_messages = body.get("messages")
    if not isinstance(raw_messages, list) or not raw_messages:
        raise bad_request("messages 必须是非空数组")
    if len(raw_messages) > limits["max_messages"]:
        raise bad_request("消息条数超过上限（%d）" % limits["max_messages"])

    messages: List[Dict[str, Any]] = []
    system = body.get("system")
    if system:
        system_images: List[Dict[str, Any]] = []
        system_text = flatten_parts(system, limits, system_images, "system")
        messages.append(make_message("system", system_text, system_images))

    for index, raw in enumerate(raw_messages):
        if not isinstance(raw, dict):
            raise bad_request("messages[%d] 必须是对象" % index)
        role = str(raw.get("role") or "user").lower()
        if role not in ("user", "assistant"):
            raise bad_request("messages[%d].role 只能是 user 或 assistant" % index)
        content = raw.get("content")
        images: List[Dict[str, Any]] = []
        tool_calls: List[Dict[str, Any]] = []
        text_chunks: List[str] = []
        pending_tool_results: List[Dict[str, Any]] = []

        if isinstance(content, str):
            text_chunks.append(content)
        elif isinstance(content, list):
            for block_index, block in enumerate(content):
                if isinstance(block, str):
                    text_chunks.append(block)
                    continue
                if not isinstance(block, dict):
                    continue
                kind = str(block.get("type") or "").lower()
                if kind == "text":
                    text_chunks.append(str(block.get("text") or ""))
                elif kind == "image":
                    source = block.get("source") or {}
                    media_type = source.get("media_type") or "image/png"
                    if source.get("type") == "base64" and source.get("data"):
                        collect(media_from_base64(source["data"], media_type, limits), images, limits)
                    elif source.get("type") == "url" and source.get("url"):
                        collect(media_from_url(source["url"], limits), images, limits)
                    else:
                        raise bad_request("messages[%d].content[%d] 图片缺少数据" % (index, block_index))
                    text_chunks.append("[图片]")
                elif kind == "tool_use":
                    arguments_text, arguments_json = normalize_arguments(block.get("input"))
                    tool_calls.append(
                        {
                            "id": str(block.get("id") or ""),
                            "name": str(block.get("name") or ""),
                            "arguments": arguments_text,
                            "arguments_json": arguments_json,
                        }
                    )
                elif kind == "tool_result":
                    result_images: List[Dict[str, Any]] = []
                    result_text = flatten_parts(
                        block.get("content"), limits, result_images, "tool_result"
                    )
                    pending_tool_results.append(
                        {
                            "role": "tool",
                            "text": result_text,
                            "images": result_images,
                            "tool_call_id": str(block.get("tool_use_id") or ""),
                        }
                    )
                elif kind in ("thinking", "redacted_thinking"):
                    # 思考内容不展示为对话正文，仅留痕
                    continue
                elif kind == "document":
                    raise unsupported("Anthropic document 块暂不支持，请改为文本")
                else:
                    text_chunks.append(str(block.get("text") or ""))
        elif content is None:
            content = ""
        else:
            raise bad_request("messages[%d].content 格式不正确" % index)

        if text_chunks or images or tool_calls:
            messages.append(
                make_message(role, "".join(text_chunks), images, tool_calls=tool_calls)
            )
        messages.extend(
            make_message(
                item["role"], item["text"], item["images"], tool_call_id=item["tool_call_id"]
            )
            for item in pending_tool_results
        )

    enforce_limits(messages, limits)
    if "max_tokens" not in body:
        raise bad_request("max_tokens 为必填参数")
    tools = normalize_tools(body.get("tools"), "anthropic")
    params = collect_params(
        body,
        ("temperature", "top_p", "top_k", "max_tokens", "stop_sequences", "metadata"),
    )
    return Normalized(
        model=str(body.get("model") or "").strip(),
        messages=messages,
        tools=tools,
        tool_choice=normalize_tool_choice(body.get("tool_choice"), "anthropic"),
        params=params,
        stream=bool(body.get("stream")),
        meta={
            "anthropic_version": body.get("anthropic_version"),
            "user": (body.get("metadata") or {}).get("user_id")
            if isinstance(body.get("metadata"), dict)
            else None,
        },
    )


def message_object(job: Job, usage: Dict[str, int]) -> Dict[str, Any]:
    """非流式 /v1/messages 响应。"""
    content: List[Dict[str, Any]] = []
    if job.reply_reasoning:
        content.append(
            {"type": "thinking", "thinking": job.reply_reasoning, "signature": ""}
        )
    if job.reply_text:
        content.append({"type": "text", "text": job.reply_text})
    for call in job.reply_tools:
        content.append(
            {
                "type": "tool_use",
                "id": call.get("id") or "",
                "name": call.get("name", ""),
                "input": call.get("arguments_json") if isinstance(call.get("arguments_json"), dict) else {},
            }
        )
    return {
        "id": "msg_" + job.id[4:],
        "type": "message",
        "role": "assistant",
        "model": job.model,
        "content": content,
        "stop_reason": "tool_use" if job.reply_tools else "end_turn",
        "stop_sequence": None,
        "usage": {"input_tokens": usage["prompt_tokens"], "output_tokens": usage["completion_tokens"]},
    }


def sse_stream(job: Job) -> Iterator[str]:
    """Anthropic 事件流：message_start / content_block_* / message_delta / message_stop。"""
    bucket = job.subscribe()
    sent = 0
    emitted_text = ""
    emitted_reasoning = ""
    block_index = 0
    thinking_open = False
    text_open = False
    prompt_usage = usage_for(job.messages, "", job.tools, [])
    try:
        yield sse_named(
            "message_start",
            {
                "type": "message_start",
                "message": {
                    "id": "msg_" + job.id[4:],
                    "type": "message",
                    "role": "assistant",
                    "model": job.model,
                    "content": [],
                    "stop_reason": None,
                    "stop_sequence": None,
                    "usage": {"input_tokens": prompt_usage["prompt_tokens"], "output_tokens": 0},
                },
            },
        )
        while True:
            while sent < len(job.deltas):
                item = job.deltas[sent]
                sent += 1
                text = item.get("text", "")
                kind = item.get("kind", "text")
                if not text:
                    continue
                if kind == "reasoning":
                    if text_open:
                        continue
                    if not thinking_open:
                        yield sse_named(
                            "content_block_start",
                            {
                                "type": "content_block_start",
                                "index": block_index,
                                "content_block": {"type": "thinking", "thinking": "", "signature": ""},
                            },
                        )
                        thinking_open = True
                    emitted_reasoning += text
                    yield sse_named(
                        "content_block_delta",
                        {
                            "type": "content_block_delta",
                            "index": block_index,
                            "delta": {"type": "thinking_delta", "thinking": text},
                        },
                    )
                else:
                    if not text_open:
                        if thinking_open:
                            yield sse_named(
                                "content_block_stop",
                                {"type": "content_block_stop", "index": block_index},
                            )
                            thinking_open = False
                            block_index += 1
                        yield sse_named(
                            "content_block_start",
                            {
                                "type": "content_block_start",
                                "index": block_index,
                                "content_block": {"type": "text", "text": ""},
                            },
                        )
                        text_open = True
                    emitted_text += text
                    yield sse_named(
                        "content_block_delta",
                        {
                            "type": "content_block_delta",
                            "index": block_index,
                            "delta": {"type": "text_delta", "text": text},
                        },
                    )
            if job.status in TERMINAL:
                break
            try:
                bucket.get(timeout=15.0)
            except queue_module.Empty:
                yield sse_keepalive()
        if job.status != "answered":
            yield sse_named(
                "error",
                {
                    "type": "error",
                    "error": {
                        "type": "timeout_error" if job.status == "expired" else "api_error",
                        "message": job.rejected_reason or "操作员未能按时作答",
                    },
                },
            )
            return
        remaining_reasoning = job.reply_reasoning
        if emitted_reasoning and remaining_reasoning.startswith(emitted_reasoning):
            remaining_reasoning = remaining_reasoning[len(emitted_reasoning):]
        if remaining_reasoning and not text_open:
            if not thinking_open:
                yield sse_named(
                    "content_block_start",
                    {
                        "type": "content_block_start",
                        "index": block_index,
                        "content_block": {"type": "thinking", "thinking": "", "signature": ""},
                    },
                )
                thinking_open = True
            yield sse_named(
                "content_block_delta",
                {
                    "type": "content_block_delta",
                    "index": block_index,
                    "delta": {"type": "thinking_delta", "thinking": remaining_reasoning},
                },
            )
        if thinking_open:
            yield sse_named(
                "content_block_stop", {"type": "content_block_stop", "index": block_index}
            )
            thinking_open = False
            block_index += 1
        if not text_open:
            yield sse_named(
                "content_block_start",
                {
                    "type": "content_block_start",
                    "index": block_index,
                    "content_block": {"type": "text", "text": ""},
                },
            )
            text_open = True
        remainder = job.reply_text
        if emitted_text and remainder.startswith(emitted_text):
            remainder = remainder[len(emitted_text):]
        if remainder:
            yield sse_named(
                "content_block_delta",
                {
                    "type": "content_block_delta",
                    "index": block_index,
                    "delta": {"type": "text_delta", "text": remainder},
                },
            )
        yield sse_named("content_block_stop", {"type": "content_block_stop", "index": block_index})
        block_index += 1
        for call in job.reply_tools:
            yield sse_named(
                "content_block_start",
                {
                    "type": "content_block_start",
                    "index": block_index,
                    "content_block": {
                        "type": "tool_use",
                        "id": call.get("id") or "",
                        "name": call.get("name", ""),
                        "input": {},
                    },
                },
            )
            yield sse_named(
                "content_block_delta",
                {
                    "type": "content_block_delta",
                    "index": block_index,
                    "delta": {"type": "input_json_delta", "partial_json": call.get("arguments", "{}")},
                },
            )
            yield sse_named("content_block_stop", {"type": "content_block_stop", "index": block_index})
            block_index += 1
        final_usage = usage_for(job.messages, job.reply_text, job.tools, job.reply_tools)
        yield sse_named(
            "message_delta",
            {
                "type": "message_delta",
                "delta": {
                    "stop_reason": "tool_use" if job.reply_tools else "end_turn",
                    "stop_sequence": None,
                },
                "usage": {"output_tokens": final_usage["completion_tokens"]},
            },
        )
        yield sse_named("message_stop", {"type": "message_stop"})
    finally:
        job.unsubscribe(bucket)


def count_tokens(body: Dict[str, Any]) -> Dict[str, Any]:
    """粗略的 token 计数（Anthropic count_tokens 兼容）。"""
    messages = body.get("messages") or []
    text = json.dumps(messages, ensure_ascii=False)
    total = estimate_tokens(text)
    return {"input_tokens": max(1, total)}
