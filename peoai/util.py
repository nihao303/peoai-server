"""通用工具：时间、ID、JSON、脱敏、客户端信息。"""
from __future__ import annotations

import hashlib
import json
import secrets
import time
from datetime import datetime, timezone
from typing import Any, Dict, Optional


def now() -> float:
    """当前 Unix 时间戳（秒，浮点）。"""
    return time.time()


def iso_time(ts: Optional[float] = None) -> str:
    """把时间戳格式化为 UTC ISO8601（秒精度）。"""
    value = now() if ts is None else ts
    return (
        datetime.fromtimestamp(value, tz=timezone.utc)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z")
    )


def new_id(prefix: str = "req_") -> str:
    """生成短随机 ID，用于请求、工具调用等。"""
    return prefix + secrets.token_hex(9)


def json_dumps(value: Any) -> str:
    """紧凑 JSON 序列化，保留中文。"""
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str)


def json_loads(text: Any, default: Any = None) -> Any:
    """安全 JSON 解析，失败返回默认值。"""
    if isinstance(text, (bytes, bytearray)):
        try:
            text = text.decode("utf-8")
        except UnicodeDecodeError:
            return default
    if not isinstance(text, str):
        return default
    try:
        return json.loads(text)
    except (ValueError, TypeError):
        return default


def truncate(text: Any, limit: int = 200) -> str:
    """截断文本并追加省略号，用于预览与日志。"""
    if text is None:
        return ""
    value = str(text)
    if limit <= 0:
        return ""
    return value if len(value) <= limit else value[: max(0, limit - 1)] + "\u2026"


def mask_secret(secret: Any, keep: int = 4) -> str:
    """把密钥脱敏为前 keep 位加星号，避免日志泄漏。"""
    value = "" if secret is None else str(secret)
    if not value:
        return ""
    if len(value) <= keep:
        return "*" * len(value)
    return value[:keep] + "*" * min(8, len(value) - keep)


def digest(text: Any) -> str:
    """计算 SHA-256 十六进制摘要（用于 API Key 存储）。"""
    return hashlib.sha256(str(text).encode("utf-8")).hexdigest()


def human_bytes(size: Any) -> str:
    """把字节数格式化成人类可读形式。"""
    try:
        value = float(size)
    except (TypeError, ValueError):
        return "0 B"
    if value < 1024:
        return "%d B" % int(value)
    for unit in ("KB", "MB", "GB"):
        value /= 1024.0
        if value < 1024:
            return "%.1f %s" % (value, unit)
    return "%.1f TB" % (value / 1024.0)


def client_ip(flask_request: Any, trust_proxy: bool = True) -> str:
    """读取真实客户端 IP；仅在信任反代时使用转发头。"""
    if flask_request is None:
        return "unknown"
    if trust_proxy:
        forwarded = flask_request.headers.get("X-Forwarded-For")
        if forwarded:
            first = forwarded.split(",")[0].strip()
            if first:
                return first[:64]
        real_ip = flask_request.headers.get("X-Real-IP")
        if real_ip:
            return real_ip.strip()[:64]
    return (flask_request.remote_addr or "unknown")[:64]


def user_agent(flask_request: Any, limit: int = 200) -> str:
    """读取 User-Agent 并截断，避免超长头污染存储。"""
    if flask_request is None:
        return ""
    return truncate(flask_request.headers.get("User-Agent", ""), limit)


def clamp(value: Any, low: float, high: float, default: Any) -> Any:
    """把数值限制在区间内，非法值返回默认值。"""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    if number != number:  # NaN
        return default
    return max(low, min(high, number))


def parse_bool(value: Any, default: bool = False) -> bool:
    """宽容解析布尔值（支持字符串与数字）。"""
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in ("1", "true", "yes", "on"):
            return True
        if lowered in ("0", "false", "no", "off", ""):
            return False
    return default


def ensure_list(value: Any) -> list:
    """把单值或 None 归一化为列表。"""
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return [value]


def deep_merge(base: Dict[str, Any], patch: Dict[str, Any]) -> Dict[str, Any]:
    """递归合并字典；列表与标量直接覆盖，返回新对象。"""
    result = dict(base)
    for key, value in (patch or {}).items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value
    return result
