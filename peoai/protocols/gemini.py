"""Google Gemini 协议：/v1beta/models/{model}:generateContent。"""
from __future__ import annotations

import json
import queue as queue_module
from typing import Any, Dict, Iterator, List

from ..errors import bad_request, unsupported
from ..images import collect, media_from_base64, media_from_url
from ..store import TERMINAL, Job
from ..tokens import usage_for
from .common import (
    Normalized,
    collect_params,
    enforce_limits,
    make_message,
    normalize_arguments,
    normalize_tool_choice,
    normalize_tools,
    sse,
    sse_keepalive,
)

PROTOCOL = "gemini.generate"
LABEL = "Gemini generateContent"


def _parse_parts(parts: Any, limits: Dict[str, int], images: List[Dict[str, Any]], tool_calls: List[Dict[str, Any]], role: str) -> str:
    if not isinstance(parts, list):
        raise bad_request("contents[].parts 必须是数组")
    chunks: List[str] = []
    for index, part in enumerate(parts):
        if not isinstance(part, dict):
            raise bad_request("parts[%d] 必须是对象" % index)
        if "text" in part:
            chunks.append(str(part.get("text") or ""))
        elif "inlineData" in part or "inline_data" in part:
            payload = part.get("inlineData") or part.get("inline_data") or {}
            data = payload.get("data")
            mime = payload.get("mimeType") or payload.get("mime_type") or "image/png"
            if not data:
                raise bad_request("inlineData 缺少 data")
            collect(media_from_base64(str(data), str(mime), limits), images, limits)
            chunks.append("[图片]")
        elif "fileData" in part or "file_data" in part:
            payload = part.get("fileData") or part.get("file_data") or {}
            uri = str(payload.get("fileUri") or payload.get("file_uri") or "")
            if uri.startswith(("http://", "https://")):
                collect(media_from_url(uri, limits), images, limits)
                chunks.append("[图片]")
            else:
                raise unsupported("Gemini fileData 目前只支持 http(s) 图片链接")
        elif "functionCall" in part or "function_call" in part:
            call = part.get("functionCall") or part.get("function_call") or {}
            arguments_text, arguments_json = normalize_arguments(call.get("args"))
            tool_calls.append(
                {
                    "id": str(call.get("id") or ""),
                    "name": str(call.get("name") or ""),
                    "arguments": arguments_text,
                    "arguments_json": arguments_json,
                }
            )
        elif "functionResponse" in part or "function_response" in part:
            response = part.get("functionResponse") or part.get("function_response") or {}
            payload = response.get("response")
            chunks.append(json.dumps(payload, ensure_ascii=False) if isinstance(payload, (dict, list)) else str(payload or ""))
        elif "thought" in part:
            continue
        else:
            raise unsupported("不支持的 Gemini part 类型")
    return "".join(chunks)


def parse_generate(body: Dict[str, Any], limits: Dict[str, int], model_hint: str = "") -> Normalized:
    """解析 generateContent 请求体。"""
    contents = body.get("contents")
    if not isinstance(contents, list) or not contents:
        raise bad_request("contents 必须是非空数组")
    messages: List[Dict[str, Any]] = []
    system_text = ""
    system = body.get("systemInstruction") or body.get("system_instruction")
    if isinstance(system, dict):
        parts = system.get("parts") or []
        system_text = _parse_parts(parts, limits, [], [], "system")
    elif isinstance(system, str):
        system_text = system
    if system_text.strip():
        messages.append(make_message("system", system_text))
    for index, content in enumerate(contents):
        if not isinstance(content, dict):
            raise bad_request("contents[%d] 必须是对象" % index)
        role = str(content.get("role") or "user").lower()
        if role == "model":
            mapped = "assistant"
        elif role == "function":
            mapped = "tool"
        else:
            mapped = "user"
        images: List[Dict[str, Any]] = []
        tool_calls: List[Dict[str, Any]] = []
        text = _parse_parts(content.get("parts") or [], limits, images, tool_calls, mapped)
        tool_call_id = ""
        for part in content.get("parts") or []:
            if isinstance(part, dict) and ("functionResponse" in part or "function_response" in part):
                payload = part.get("functionResponse") or part.get("function_response") or {}
                tool_call_id = str(payload.get("name") or "")
        messages.append(make_message(mapped, text, images, tool_calls=tool_calls, tool_call_id=tool_call_id))
    enforce_limits(messages, limits)

    tools: List[Dict[str, Any]] = []
    raw_tools = body.get("tools") or []
    if isinstance(raw_tools, list):
        for item in raw_tools:
            if not isinstance(item, dict):
                continue
            declarations = item.get("functionDeclarations") or item.get("function_declarations")
            if declarations:
                tools.extend(normalize_tools(declarations, "gemini"))
    tool_config = body.get("toolConfig") or body.get("tool_config") or {}
    tool_choice = normalize_tool_choice(tool_config, "gemini") if tool_config else None

    generation = body.get("generationConfig") or body.get("generation_config") or {}
    if not isinstance(generation, dict):
        generation = {}
    params = collect_params(
        generation,
        ("temperature", "topP", "topK", "maxOutputTokens", "stopSequences", "candidateCount", "responseMimeType", "seed"),
    )
    if "candidateCount" in params:
        try:
            count = int(params["candidateCount"])
        except (TypeError, ValueError):
            raise bad_request("candidateCount 必须是整数")
        if count != 1:
            raise unsupported("真人操作员一次只能生成一个候选，candidateCount 仅支持 1")
    return Normalized(
        model=model_hint or str(body.get("model") or ""),
        messages=messages,
        tools=tools,
        tool_choice=tool_choice,
        params=params,
        stream=bool(body.get("_stream")),
        meta={"api": "generateContent"},
    )


def response_payload(job: Job, usage: Dict[str, int]) -> Dict[str, Any]:
    """非流式 generateContent 响应。"""
    parts: List[Dict[str, Any]] = []
    if job.reply_reasoning:
        parts.append({"text": job.reply_reasoning, "thought": True})
    if job.reply_text:
        parts.append({"text": job.reply_text})
    for call in job.reply_tools:
        arguments = call.get("arguments_json")
        parts.append(
            {
                "functionCall": {
                    "name": call.get("name", ""),
                    "args": arguments if isinstance(arguments, dict) else {},
                }
            }
        )
    if not parts:
        parts.append({"text": ""})
    return {
        "candidates": [
            {
                "content": {"parts": parts, "role": "model"},
                "finishReason": "STOP",
                "index": 0,
                "safetyRatings": [],
            }
        ],
        "usageMetadata": {
            "promptTokenCount": usage["prompt_tokens"],
            "candidatesTokenCount": usage["completion_tokens"],
            "totalTokenCount": usage["total_tokens"],
        },
        "modelVersion": job.model,
    }


def sse_stream(job: Job) -> Iterator[str]:
    """Gemini alt=sse 流式响应。"""
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
                if kind == "reasoning":
                    emitted_reasoning += text
                    part = {"text": text, "thought": True}
                else:
                    emitted_text += text
                    part = {"text": text}
                yield sse(
                    {
                        "candidates": [
                            {
                                "content": {"parts": [part], "role": "model"},
                                "index": 0,
                                "safetyRatings": [],
                            }
                        ],
                        "modelVersion": job.model,
                    }
                )
            if job.status in TERMINAL:
                break
            try:
                bucket.get(timeout=15.0)
            except queue_module.Empty:
                yield sse_keepalive()
        if job.status != "answered":
            yield sse(
                {
                    "error": {
                        "code": 504 if job.status == "expired" else 503,
                        "message": job.rejected_reason or "操作员未能按时作答",
                        "status": "DEADLINE_EXCEEDED" if job.status == "expired" else "UNAVAILABLE",
                    }
                }
            )
            return
        remaining_reasoning = job.reply_reasoning
        if emitted_reasoning and remaining_reasoning.startswith(emitted_reasoning):
            remaining_reasoning = remaining_reasoning[len(emitted_reasoning):]
        if remaining_reasoning:
            yield sse(
                {
                    "candidates": [
                        {
                            "content": {
                                "parts": [{"text": remaining_reasoning, "thought": True}],
                                "role": "model",
                            },
                            "index": 0,
                            "safetyRatings": [],
                        }
                    ],
                    "modelVersion": job.model,
                }
            )
        remainder = job.reply_text
        if emitted_text and remainder.startswith(emitted_text):
            remainder = remainder[len(emitted_text):]
        if remainder:
            yield sse(
                {
                    "candidates": [
                        {
                            "content": {"parts": [{"text": remainder}], "role": "model"},
                            "index": 0,
                            "safetyRatings": [],
                        }
                    ],
                    "modelVersion": job.model,
                }
            )
        if job.reply_tools:
            parts = [
                {
                    "functionCall": {
                        "name": call.get("name", ""),
                        "args": call.get("arguments_json") if isinstance(call.get("arguments_json"), dict) else {},
                    }
                }
                for call in job.reply_tools
            ]
            yield sse(
                {
                    "candidates": [{"content": {"parts": parts, "role": "model"}, "index": 0}],
                    "modelVersion": job.model,
                }
            )
        usage = usage_for(job.messages, job.reply_text, job.tools, job.reply_tools)
        yield sse(
            {
                "candidates": [
                    {
                        "content": {"parts": [{"text": ""}], "role": "model"},
                        "finishReason": "STOP",
                        "index": 0,
                    }
                ],
                "usageMetadata": {
                    "promptTokenCount": usage["prompt_tokens"],
                    "candidatesTokenCount": usage["completion_tokens"],
                    "totalTokenCount": usage["total_tokens"],
                },
                "modelVersion": job.model,
            }
        )
    finally:
        job.unsubscribe(bucket)
