"""统一错误对象与多协议错误体渲染。

不同客户端对错误体的格式要求不同：
    OpenAI      {"error": {"message", "type", "code", "param"}}
    Anthropic   {"type": "error", "error": {"type", "message"}}
    Gemini      {"error": {"code", "message", "status"}}
    Ollama      {"error": "..."}

内部一律抛 PeoaiError，由路由层根据协议序列化。
"""
from __future__ import annotations

from typing import Any, Dict, Optional, Tuple


class PeoaiError(Exception):
    """业务错误：同时携带 HTTP 状态码与协议错误类型。"""

    def __init__(
        self,
        message: str,
        status: int = 400,
        type: str = "invalid_request_error",
        code: Optional[str] = None,
        param: Optional[str] = None,
        retry_after: Optional[int] = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.status = status
        self.type = type
        self.code = code or type
        self.param = param
        self.retry_after = retry_after

    def __str__(self) -> str:  # pragma: no cover - 便于日志
        return "PeoaiError(status=%s, type=%s, message=%s)" % (
            self.status,
            self.type,
            self.message,
        )


# ---------------------------------------------------------------------------
# 预置错误构造器：语义一目了然，便于路由层复用
# ---------------------------------------------------------------------------

def bad_request(message: str, param: Optional[str] = None) -> PeoaiError:
    return PeoaiError(message, 400, "invalid_request_error", "invalid_request", param)


def unauthorized(message: str = "缺少或无效的 API Key") -> PeoaiError:
    return PeoaiError(message, 401, "authentication_error", "invalid_api_key")


def forbidden(message: str = "没有访问该资源的权限") -> PeoaiError:
    return PeoaiError(message, 403, "permission_error", "permission_denied")


def not_found(message: str) -> PeoaiError:
    return PeoaiError(message, 404, "not_found_error", "not_found")


def payload_too_large(message: str = "请求体过大") -> PeoaiError:
    return PeoaiError(message, 413, "invalid_request_error", "payload_too_large")


def unsupported(message: str) -> PeoaiError:
    return PeoaiError(message, 400, "invalid_request_error", "unsupported_parameter")


def timeout_error(message: str = "操作员在规定时间内未响应") -> PeoaiError:
    return PeoaiError(message, 504, "timeout_error", "request_timeout")


def unavailable(message: str = "暂时没有可用的操作员") -> PeoaiError:
    return PeoaiError(message, 503, "service_unavailable_error", "operator_unavailable")


def rate_limited(message: str, retry_after: int = 60) -> PeoaiError:
    return PeoaiError(message, 429, "rate_limit_error", "rate_limit_exceeded", retry_after=retry_after)


# ---------------------------------------------------------------------------
# 状态码 -> 各协议错误类型
# ---------------------------------------------------------------------------

_GEMINI_STATUS = {
    400: "INVALID_ARGUMENT",
    401: "UNAUTHENTICATED",
    403: "PERMISSION_DENIED",
    404: "NOT_FOUND",
    409: "ABORTED",
    413: "INVALID_ARGUMENT",
    429: "RESOURCE_EXHAUSTED",
    500: "INTERNAL",
    501: "UNIMPLEMENTED",
    503: "UNAVAILABLE",
    504: "DEADLINE_EXCEEDED",
}

_ANTHROPIC_TYPE = {
    400: "invalid_request_error",
    401: "authentication_error",
    403: "permission_error",
    404: "not_found_error",
    413: "request_too_large",
    429: "rate_limit_error",
    500: "api_error",
    501: "api_error",
    503: "overloaded_error",
    504: "timeout_error",
}


def error_payload(family: str, err: PeoaiError) -> Tuple[Dict[str, Any], int]:
    """按协议族生成 (body, status)。family 取值见 protocols 模块。"""
    status = err.status
    if family == "anthropic":
        body = {
            "type": "error",
            "error": {"type": _ANTHROPIC_TYPE.get(status, "api_error"), "message": err.message},
        }
        return body, status
    if family == "gemini":
        body = {
            "error": {
                "code": status,
                "message": err.message,
                "status": _GEMINI_STATUS.get(status, "UNKNOWN"),
            }
        }
        return body, status
    if family == "ollama":
        return {"error": err.message}, status
    if family == "console":
        return {
            "ok": False,
            "error": {
                "message": err.message,
                "type": err.type,
                "code": err.code,
                "param": err.param,
            },
        }, status
    body = {
        "error": {
            "message": err.message,
            "type": err.type,
            "code": err.code,
            "param": err.param,
        }
    }
    return body, status
