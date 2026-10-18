"""Token 估算。

真人操作员没有真实的分词器，因此这里给出一个稳定的近似：
    * C 中日韩字符按 1 token 计；
    * 其余字符按 4 字符 1 token 计；
    * 每条消息附加固定开销，每张图片附加固定开销。

估算值会写入响应 usage 字段（并在 console 中标注 estimated），
让计费类客户端至少拿到「单调且量级正确」的数字。
"""
from __future__ import annotations

from typing import Any, Dict, Iterable, List

MESSAGE_OVERHEAD = 4
IMAGE_OVERHEAD = 220
SYSTEM_OVERHEAD = 3


def _is_cjk(code: int) -> bool:
    return (
        0x4E00 <= code <= 0x9FFF        # 基本汉字
        or 0x3400 <= code <= 0x4DBF     # 扩展 A
        or 0x3040 <= code <= 0x30FF     # 日文假名
        or 0xAC00 <= code <= 0xD7AF     # 韩文
        or 0x3000 <= code <= 0x303F     # 中文标点
        or 0xFF00 <= code <= 0xFFEF     # 全角字符
    )


def estimate_tokens(text: Any) -> int:
    """估算一段文本的 token 数（至少 1，空串为 0）。"""
    if not text:
        return 0
    value = str(text)
    cjk = 0
    other = 0
    for char in value:
        if _is_cjk(ord(char)):
            cjk += 1
        else:
            other += 1
    tokens = cjk + (other + 3) // 4
    return max(1, tokens) if value else 0


def estimate_messages(messages: Iterable[Dict[str, Any]]) -> int:
    """估算消息列表的总输入 token。"""
    total = 0
    for message in messages or []:
        total += MESSAGE_OVERHEAD
        text = message.get("text")
        if text:
            total += estimate_tokens(text)
        images = message.get("images") or []
        total += IMAGE_OVERHEAD * len(images)
        for call in message.get("tool_calls") or []:
            total += estimate_tokens(call.get("name", ""))
            total += estimate_tokens(call.get("arguments", ""))
        if message.get("role") == "system":
            total += SYSTEM_OVERHEAD
    return max(1, total) if messages else 0


def estimate_tools(tools: List[Dict[str, Any]]) -> int:
    """工具定义同样会占用上下文，按 JSON 文本折算。"""
    total = 0
    for tool in tools or []:
        total += 16
        total += estimate_tokens(tool.get("name", ""))
        total += estimate_tokens(tool.get("description", ""))
        total += estimate_tokens(str(tool.get("parameters") or {}))
    return total


def usage_for(
    messages: Iterable[Dict[str, Any]],
    reply_text: str = "",
    tools: List[Dict[str, Any]] = None,
    tool_calls: List[Dict[str, Any]] = None,
) -> Dict[str, int]:
    """组装 OpenAI 风格的 usage 字典。"""
    prompt = estimate_messages(messages) + estimate_tools(tools or [])
    completion = estimate_tokens(reply_text)
    for call in tool_calls or []:
        completion += estimate_tokens(call.get("name", ""))
        completion += estimate_tokens(call.get("arguments", ""))
    completion = max(0, completion)
    return {
        "prompt_tokens": prompt,
        "completion_tokens": completion,
        "total_tokens": prompt + completion,
    }
