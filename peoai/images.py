"""图片解析与安全校验。

支持的输入形态：
    * OpenAI      {"type": "image_url", "image_url": {"url": "data:image/png;base64,..."}}
    * Anthropic   {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": "..."}}
    * Gemini      {"inlineData": {"mimeType": "image/png", "data": "..."}}
    * Ollama      messages[].images = ["<base64>", ...]

安全策略：
    * 只接受白名单 MIME，并核对文件魔数，防止伪装成图片的任意内容；
    * 严格限制单图字节数与单请求图片数量；
    * 远端 URL 不做服务端抓取（避免 SSRF），只做格式校验后交给浏览器展示；
    * base64 解码失败、超出大小、MIME 不符一律拒绝并给出明确错误。
"""
from __future__ import annotations

import base64
import binascii
import hashlib
import re
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

from .errors import bad_request
from .util import truncate

ALLOWED_MIME = {
    "image/png",
    "image/jpeg",
    "image/gif",
    "image/webp",
    "image/bmp",
}

_EXT_MIME = {
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "gif": "image/gif",
    "webp": "image/webp",
    "bmp": "image/bmp",
}

_DATA_URL_RE = re.compile(r"^data:([a-zA-Z0-9.+-]+/[a-zA-Z0-9.+-]+)?(;[a-zA-Z0-9=._+-]+)*;base64,")


def sniff_mime(data: bytes) -> Optional[str]:
    """按魔数识别图片真实类型，识别失败返回 None。"""
    if not data:
        return None
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith(b"GIF87a") or data.startswith(b"GIF89a"):
        return "image/gif"
    if len(data) > 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    if data.startswith(b"BM"):
        return "image/bmp"
    return None


def parse_data_url(url: str, limits: Dict[str, int]) -> Tuple[str, bytes]:
    """解析 data URL，返回 (mime, 字节)。"""
    match = _DATA_URL_RE.match(url or "")
    if not match:
        raise bad_request("图片 data URL 格式不正确，应为 data:image/...;base64,...")
    declared = (match.group(1) or "").lower()
    payload = url[match.end():].strip()
    if not payload:
        raise bad_request("图片 data URL 内容为空")
    max_bytes = int(limits.get("max_image_bytes", 2 * 1024 * 1024))
    # base64 膨胀约 4/3，先按长度预检，避免解码超大字符串耗尽内存
    if len(payload) > (max_bytes * 4) // 3 + 64:
        raise bad_request("图片超过单张大小上限（%d 字节）" % max_bytes)
    try:
        data = base64.b64decode(payload, validate=False)
    except (binascii.Error, ValueError):
        raise bad_request("图片 base64 解码失败")
    if not data:
        raise bad_request("图片内容为空")
    if len(data) > max_bytes:
        raise bad_request("图片超过单张大小上限（%d 字节）" % max_bytes)
    real = sniff_mime(data)
    if not real:
        raise bad_request("无法识别的图片格式，仅支持 PNG / JPEG / GIF / WebP / BMP")
    if declared and declared != real:
        # 允许 jpg 与 jpeg 的等价写法
        if not (declared in ("image/jpg", "image/jpeg") and real == "image/jpeg"):
            raise bad_request("图片声明类型 %s 与实际内容 %s 不一致" % (declared, real))
    if real not in ALLOWED_MIME:
        raise bad_request("不支持的图片类型 %s" % real)
    return real, data


def _inline_media(mime: str, data: bytes, name: str = "") -> Dict[str, Any]:
    encoded = base64.b64encode(data).decode("ascii")
    return {
        "kind": "inline",
        "mime": mime,
        "bytes": len(data),
        "data_url": "data:%s;base64,%s" % (mime, encoded),
        "name": name or "",
        "sha256": hashlib.sha256(data).hexdigest()[:16],
        "detail": "auto",
    }


def _remote_media(url: str, name: str = "") -> Dict[str, Any]:
    parsed = urlparse(url or "")
    if parsed.scheme not in ("http", "https"):
        raise bad_request("远端图片只支持 http/https 链接")
    if not parsed.netloc or len(url) > 2048:
        raise bad_request("远端图片链接不合法或过长")
    if parsed.username or parsed.password:
        raise bad_request("远端图片链接不允许携带账号密码")
    extension = (parsed.path.rsplit(".", 1)[-1] if "." in parsed.path else "").lower()
    return {
        "kind": "remote",
        "mime": _EXT_MIME.get(extension, ""),
        "bytes": 0,
        "url": url,
        "name": name or truncate(parsed.path.rsplit("/", 1)[-1], 80),
        "sha256": "",
        "detail": "auto",
    }


def media_from_url(url: str, limits: Dict[str, int], name: str = "") -> Dict[str, Any]:
    """统一入口：data URL 解码为内联图，http(s) 保留为远端图。"""
    value = (url or "").strip()
    if not value:
        raise bad_request("图片地址为空")
    if value.lower().startswith("data:"):
        mime, data = parse_data_url(value, limits)
        return _inline_media(mime, data, name)
    return _remote_media(value, name)


def media_from_base64(payload: str, mime: str, limits: Dict[str, int], name: str = "") -> Dict[str, Any]:
    """Anthropic / Gemini / Ollama 使用独立的 base64 + mime 字段。"""
    text = (payload or "").strip()
    if not text:
        raise bad_request("图片 base64 内容为空")
    declared = (mime or "").lower() or "image/png"
    if declared == "image/jpg":
        declared = "image/jpeg"
    if declared not in ALLOWED_MIME:
        raise bad_request("不支持的图片类型 %s" % declared)
    max_bytes = int(limits.get("max_image_bytes", 2 * 1024 * 1024))
    if len(text) > (max_bytes * 4) // 3 + 64:
        raise bad_request("图片超过单张大小上限（%d 字节）" % max_bytes)
    if text.startswith("data:"):
        real, data = parse_data_url(text, limits)
        return _inline_media(real, data, name)
    try:
        data = base64.b64decode(text, validate=False)
    except (binascii.Error, ValueError):
        raise bad_request("图片 base64 解码失败")
    if not data:
        raise bad_request("图片内容为空")
    if len(data) > max_bytes:
        raise bad_request("图片超过单张大小上限（%d 字节）" % max_bytes)
    real = sniff_mime(data)
    if not real:
        raise bad_request("无法识别的图片格式，仅支持 PNG / JPEG / GIF / WebP / BMP")
    return _inline_media(real, data, name)


def collect(media: Dict[str, Any], bucket: List[Dict[str, Any]], limits: Dict[str, int]) -> None:
    """把一张图片加入集合，并检查单请求数量上限。"""
    maximum = int(limits.get("max_images", 4))
    if len(bucket) >= maximum:
        raise bad_request("单次请求最多携带 %d 张图片" % maximum)
    bucket.append(media)


def public_media(media: Dict[str, Any], include_inline: bool = True) -> Dict[str, Any]:
    """给前端的图片描述；include_inline=False 时省略 base64 大字段。"""
    if not isinstance(media, dict):
        return {}
    view = {
        "kind": media.get("kind"),
        "mime": media.get("mime") or "",
        "bytes": media.get("bytes") or 0,
        "name": media.get("name") or "",
        "detail": media.get("detail") or "auto",
        "sha256": media.get("sha256") or "",
    }
    if media.get("kind") == "inline":
        if include_inline:
            view["data_url"] = media.get("data_url") or ""
    else:
        view["url"] = media.get("url") or ""
    return view


def strip_inline(media: Dict[str, Any]) -> Dict[str, Any]:
    """持久化时去掉 base64，仅保留元信息，控制磁盘占用。"""
    view = public_media(media, include_inline=False)
    return view
