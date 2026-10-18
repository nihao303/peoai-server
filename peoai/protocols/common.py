"""协议适配公共工具。"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Tuple

from ..errors import bad_request, unsupported
from ..images import collect, media_from_base64, media_from_url
from ..util import clamp, json_loads


@dataclass
class Normalized:
    """与协议无关的请求表示。"""

    model: str = ""
    messages: List[Dict[str, Any]] = field(default_factory=list)
    tools: List[Dict[str, Any]] = field(default_factory=list)
    tool_choice: Any = None
    params: Dict[str, Any] = field(default_factory=dict)
    stream: bool = False
    meta: Dict[str, Any] = field(default_factory=dict)


def make_message(
    role: str,
    text: str = "",
    images: Optional[List[Dict[str, Any]]] = None,
    tool_calls: Optional[List[Dict[str, Any]]] = None,
    tool_call_id: str = "",
    name: str = "",
) -> Dict[str, Any]:
    """构造归一化消息。"""
    return {
        "role": role,
        "text": text or "",
        "images": images or [],
        "tool_calls": tool_calls or [],
        "tool_call_id": tool_call_id or "",
        "name": name or "",
    }


def flatten_parts(parts: Any, limits: Dict[str, int], images: List[Dict[str, Any]], label: str = "content") -> str:
    """把 content 的字符串 / 多段数组统一折叠成文本，同时收集图片。"""
    if parts is None:
        return ""
    if isinstance(parts, str):
        return parts
    if isinstance(parts, dict):
        parts = [parts]
    if not isinstance(parts, list):
        raise bad_request("%s 格式不正确：应为字符串或片段数组" % label)
    chunks: List[str] = []
    for index, part in enumerate(parts):
        if isinstance(part, str):
            chunks.append(part)
            continue
        if not isinstance(part, dict):
            continue
        kind = str(part.get("type") or "").lower()
        if kind in ("text", "input_text", "output_text", "text_delta"):
            value = part.get("text")
            if isinstance(value, str):
                chunks.append(value)
            continue
        if kind in ("image_url", "input_image"):
            payload = part.get("image_url") or part.get("image") or part
            url = payload if isinstance(payload, str) else payload.get("url")
            if not url:
                raise bad_request("%s[%d] 缺少图片地址" % (label, index))
            collect(media_from_url(str(url), limits, part.get("name") or ""), images, limits)
            chunks.append("[图片]")
            continue
        if kind in ("image",):
            source = part.get("source") or {}
            media_type = source.get("media_type") or source.get("mime_type") or "image/png"
            if source.get("type") == "base64" and source.get("data"):
                collect(media_from_base64(source["data"], media_type, limits), images, limits)
            elif source.get("type") == "url" and source.get("url"):
                collect(media_from_url(source["url"], limits), images, limits)
            else:
                raise bad_request("%s[%d] 图片缺少 base64 数据或 url" % (label, index))
            chunks.append("[图片]")
            continue
        if kind in ("inline_data", "inlinedata"):
            payload = part.get("inlineData") or part.get("inline_data") or {}
            data = payload.get("data")
            mime = payload.get("mimeType") or payload.get("mime_type") or "image/png"
            if not data:
                raise bad_request("%s[%d] 内联图片缺少 data" % (label, index))
            collect(media_from_base64(str(data), str(mime), limits), images, limits)
            chunks.append("[图片]")
            continue
        if kind in ("input_audio", "audio"):
            raise unsupported("当前服务不支持音频输入，请改用文本或图片")
        if kind in ("file", "document"):
            raise unsupported("当前服务不支持文件/文档输入，请改用文本或图片")
        # 未知片段：把可读字段兜底拼进去，避免信息丢失
        for key in ("text", "content", "value"):
            value = part.get(key)
            if isinstance(value, str) and value:
                chunks.append(value)
                break
    return "".join(chunks)


def normalize_arguments(raw: Any) -> Tuple[str, Any]:
    """把工具参数统一成 (字符串, 解析后的对象或 None)。"""
    if raw is None:
        return "{}", {}
    if isinstance(raw, str):
        text = raw.strip() or "{}"
        return text, json_loads(text, None)
    if isinstance(raw, (dict, list)):
        return json.dumps(raw, ensure_ascii=False), raw
    text = str(raw)
    return text, json_loads(text, None)


def normalize_tool_def(raw: Any, source: str = "openai") -> Dict[str, Any]:
    """统一工具定义：OpenAI function / Anthropic input_schema / Gemini declaration。"""
    if not isinstance(raw, dict):
        raise bad_request("tools 中的元素必须是对象")
    if source == "openai":
        inner = raw.get("function") if isinstance(raw.get("function"), dict) else raw
        kind = str(raw.get("type") or "function").lower()
        if kind not in ("function", "custom"):
            raise bad_request("目前只支持 type=function 的工具")
    elif source == "anthropic":
        inner = raw
    else:
        inner = raw
    name = str(inner.get("name") or "").strip()
    if not name:
        raise bad_request("工具定义缺少 name")
    if len(name) > 64:
        raise bad_request("工具名 %s 超过 64 字符" % name[:64])
    description = str(inner.get("description") or "")
    parameters = (
        inner.get("parameters")
        or inner.get("input_schema")
        or inner.get("parametersJsonSchema")
        or inner.get("parameters_json_schema")
    )
    if not isinstance(parameters, dict):
        parameters = {"type": "object", "properties": {}}
    return {
        "name": name,
        "description": description[:4000],
        "parameters": parameters,
        "strict": bool(inner.get("strict")),
        "source": source,
    }


def normalize_tools(raw: Any, source: str = "openai") -> List[Dict[str, Any]]:
    """批量归一化工具定义，限制数量与重复名。"""
    if raw in (None, "", []):
        return []
    if not isinstance(raw, list):
        raise bad_request("tools 必须是数组")
    if len(raw) > 128:
        raise bad_request("工具数量超过上限（128）")
    tools: List[Dict[str, Any]] = []
    seen = set()
    for item in raw:
        tool = normalize_tool_def(item, source)
        if tool["name"] in seen:
            continue
        seen.add(tool["name"])
        tools.append(tool)
    return tools


def normalize_tool_choice(raw: Any, source: str = "openai") -> Any:
    """把各家的 tool_choice 归一成：auto / none / required / {"name": ...}。"""
    if raw is None:
        return None
    if isinstance(raw, str):
        lowered = raw.lower()
        if lowered in ("auto", "none", "required", "any"):
            return "required" if lowered == "any" else lowered
        return raw
    if isinstance(raw, dict):
        if source == "anthropic":
            kind = str(raw.get("type") or "").lower()
            if kind in ("auto", "any", "none"):
                return "required" if kind == "any" else kind
            if kind == "tool" and raw.get("name"):
                return {"name": str(raw["name"])}
        if source == "gemini":
            mode = str(raw.get("mode") or raw.get("function_calling_config", {}).get("mode") or "").upper()
            if mode == "NONE":
                return "none"
            if mode == "ANY":
                allowed = raw.get("allowed_function_names") or raw.get("function_calling_config", {}).get("allowed_function_names")
                if isinstance(allowed, list) and allowed:
                    return {"name": str(allowed[0])}
                return "required"
            if mode == "AUTO":
                return "auto"
        fn = raw.get("function") if isinstance(raw.get("function"), dict) else raw
        if isinstance(fn, dict) and fn.get("name"):
            return {"name": str(fn["name"])}
        kind = str(raw.get("type") or "").lower()
        if kind in ("auto", "none", "required"):
            return kind
    return None


def enforce_limits(messages: Iterable[Dict[str, Any]], limits: Dict[str, int]) -> None:
    """消息数量与长度限制。"""
    items = list(messages)
    if not items:
        raise bad_request("messages 不能为空")
    if len(items) > limits["max_messages"]:
        raise bad_request("消息条数超过上限（%d）" % limits["max_messages"])
    total = 0
    for index, message in enumerate(items):
        length = len(message.get("text") or "")
        if length > limits["max_message_chars"]:
            raise bad_request("第 %d 条消息超过单条长度上限（%d 字符）" % (index + 1, limits["max_message_chars"]))
        total += length
        for call in message.get("tool_calls") or []:
            total += len(str(call.get("arguments") or ""))
    if total > limits["max_message_chars"] * 4:
        raise bad_request("消息总长度过大，请拆分后再发送")


def collect_params(body: Dict[str, Any], allowed: Iterable[str]) -> Dict[str, Any]:
    """只保留白名单参数，避免把未知字段带进队列。"""
    params: Dict[str, Any] = {}
    for key in allowed:
        if key in body and body[key] is not None:
            params[key] = body[key]
    return params


def numeric_param(params: Dict[str, Any], key: str, low: float, high: float, default: Any) -> Any:
    if key not in params:
        return default
    return clamp(params[key], low, high, default)


def sse(obj: Any) -> str:
    """OpenAI / Gemini 风格的数据帧。"""
    return "data: " + json.dumps(obj, ensure_ascii=False, separators=(",", ":")) + "\n\n"


def sse_named(event: str, obj: Any) -> str:
    """Anthropic 风格的事件帧。"""
    return "event: " + event + "\ndata: " + json.dumps(obj, ensure_ascii=False, separators=(",", ":")) + "\n\n"


def sse_done() -> str:
    return "data: [DONE]\n\n"


def sse_keepalive() -> str:
    return ": keepalive\n\n"


def now_created() -> int:
    import time

    return int(time.time())


def should_include_usage(job: Any) -> bool:
    """OpenAI stream_options.include_usage 兼容。"""
    options = (job.params or {}).get("stream_options") or {}
    return bool(isinstance(options, dict) and options.get("include_usage"))
