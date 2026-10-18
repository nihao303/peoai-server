"""凭据与鉴权：操作员会话、登录防爆破、API Key 校验。

安全约定：
    * 操作员会话使用随机 Bearer Token（进程内存储，可随时吊销），
      不使用 Cookie，因此天然免疫 CSRF；
    * 登录失败按 IP 计数并锁定，防止在线爆破；
    * API Key 只存 SHA-256 摘要，比对使用恒定时间比较；
    * 管理端令牌同样只存摘要，可独立于操作员密码轮换。
"""
from __future__ import annotations

import hmac
import secrets
import threading
import time
from typing import Any, Dict, Optional, Tuple

from .errors import forbidden, rate_limited, unauthorized
from .util import digest, iso_time, now, truncate


def new_session_token() -> str:
    """生成操作员会话令牌（前缀便于日志检索与泄漏扫描）。"""
    return "po_" + secrets.token_urlsafe(32)


class SessionStore:
    """内存会话表：令牌 -> 会话信息。重启即失效，防止旧令牌长期可用。"""

    def __init__(self, ttl_seconds: int = 43200, max_sessions: int = 100) -> None:
        self.ttl = max(60, int(ttl_seconds))
        self.max_sessions = max(1, int(max_sessions))
        self._lock = threading.Lock()
        self._sessions: Dict[str, Dict[str, Any]] = {}

    def issue(self, role: str = "operator", label: str = "") -> Dict[str, Any]:
        token = new_session_token()
        created = now()
        record = {
            "token": token,
            "role": role,
            "label": label,
            "created_at": created,
            "expires_at": created + self.ttl,
            "csrf": secrets.token_urlsafe(18),
        }
        with self._lock:
            self._prune_locked()
            if len(self._sessions) >= self.max_sessions:
                oldest = min(self._sessions.items(), key=lambda kv: kv[1]["created_at"])[0]
                self._sessions.pop(oldest, None)
            self._sessions[token] = record
        return dict(record)

    def verify(self, token: Optional[str]) -> Optional[Dict[str, Any]]:
        if not token:
            return None
        with self._lock:
            record = self._sessions.get(token)
            if not record:
                return None
            if record["expires_at"] <= now():
                self._sessions.pop(token, None)
                return None
            return dict(record)

    def revoke(self, token: Optional[str]) -> bool:
        if not token:
            return False
        with self._lock:
            return self._sessions.pop(token, None) is not None

    def revoke_all(self) -> int:
        with self._lock:
            count = len(self._sessions)
            self._sessions.clear()
            return count

    def prune(self) -> int:
        with self._lock:
            return self._prune_locked()

    def _prune_locked(self) -> int:
        cutoff = now()
        expired = [key for key, value in self._sessions.items() if value["expires_at"] <= cutoff]
        for key in expired:
            self._sessions.pop(key, None)
        return len(expired)

    def count(self) -> int:
        with self._lock:
            return len(self._sessions)


class LoginGuard:
    """登录失败计数：超过阈值后按 IP 锁定一段时间。"""

    def __init__(self, max_attempts: int = 6, lock_seconds: int = 300) -> None:
        self.max_attempts = max(1, int(max_attempts))
        self.lock_seconds = max(10, int(lock_seconds))
        self._lock = threading.Lock()
        self._state: Dict[str, Dict[str, Any]] = {}

    def check(self, identity: str) -> Tuple[bool, int]:
        """返回 (是否允许尝试, 剩余锁定秒数)。"""
        with self._lock:
            item = self._state.get(identity)
            if not item:
                return True, 0
            locked_until = item.get("locked_until", 0)
            if locked_until and locked_until > now():
                return False, int(locked_until - now()) + 1
            if locked_until and locked_until <= now():
                self._state.pop(identity, None)
            return True, 0

    def fail(self, identity: str) -> int:
        """记录一次失败，返回剩余可尝试次数（0 表示已锁定）。"""
        with self._lock:
            item = self._state.setdefault(identity, {"count": 0, "locked_until": 0, "last": 0})
            item["count"] += 1
            item["last"] = now()
            if item["count"] >= self.max_attempts:
                item["locked_until"] = now() + self.lock_seconds
                return 0
            return self.max_attempts - item["count"]

    def success(self, identity: str) -> None:
        with self._lock:
            self._state.pop(identity, None)

    def reset(self, identity: Optional[str] = None) -> None:
        with self._lock:
            if identity is None:
                self._state.clear()
            else:
                self._state.pop(identity, None)


# ---------------------------------------------------------------------------
# 请求头解析
# ---------------------------------------------------------------------------

def bearer_token(headers: Any) -> Optional[str]:
    """从 Authorization 或自定义头取出 Bearer 令牌。"""
    raw = (headers.get("Authorization") or "").strip()
    if raw:
        parts = raw.split(None, 1)
        if len(parts) == 2 and parts[0].lower() in ("bearer", "token"):
            return parts[1].strip()
        if len(parts) == 1 and raw.lower().startswith(("sk-", "pk_", "po_", "adm_")):
            return raw
    for header in ("X-PeoAI-Token", "X-Api-Key", "X-Goog-Api-Key"):
        value = (headers.get(header) or "").strip()
        if value:
            return value
    return None


def api_key_candidates(request: Any) -> list:
    """收集请求中可能携带的 API Key（兼容各家 SDK 的习惯）。"""
    values = []
    bearer = bearer_token(request.headers)
    if bearer:
        values.append(bearer)
    for header in ("x-api-key", "api-key", "x-goog-api-key"):
        value = (request.headers.get(header) or "").strip()
        if value and value not in values:
            values.append(value)
    for name in ("key", "api_key", "api-key"):
        value = (request.args.get(name) or "").strip()
        if value and value not in values:
            values.append(value)
    return values


def resolve_api_key(config: Any, request: Any) -> Tuple[Dict[str, Any], str]:
    """校验 API Key，返回 (密钥记录, 说明)。

    * 配置中存在密钥且 require_api_key=true 时强制校验；
    * 未配置任何密钥时按「开放模式」放行（便于本地试用），
      但会在启动日志里给出明确警告。
    """
    keys = config.get("api_keys") or []
    required = bool(config.get("security.require_api_key", True))
    candidates = api_key_candidates(request)
    for value in candidates:
        record = config.find_api_key(value)
        if record:
            return record, "ok"
    if not required or not keys:
        return {"name": "anonymous", "prefix": "anonymous", "rpm": 0, "models": ["*"]}, "open"
    if candidates:
        raise unauthorized("API Key 无效或已被禁用")
    raise unauthorized("缺少 API Key：请在 Authorization: Bearer <key> 或 x-api-key 中提供")


def key_allows_model(key: Dict[str, Any], model_id: str) -> bool:
    """密钥可访问的模型白名单，["*"] 代表全部。"""
    allowed = key.get("models") or ["*"]
    if "*" in allowed:
        return True
    return model_id in allowed


def operator_from_request(config: Any, sessions: SessionStore, request: Any) -> Optional[Dict[str, Any]]:
    """读取操作员会话；支持 Authorization 与 X-PeoAI-Token。"""
    token = bearer_token(request.headers)
    record = sessions.verify(token)
    if not record:
        return None
    record["token"] = token
    # 会话有效期内允许把操作员视为管理员（单操作员部署模型）
    record["is_admin"] = True
    return record


def require_operator(config: Any, sessions: SessionStore, request: Any) -> Dict[str, Any]:
    record = operator_from_request(config, sessions, request)
    if not record:
        raise unauthorized("未登录或会话已过期，请重新登录")
    return record


def admin_ok(config: Any, operator: Optional[Dict[str, Any]], request: Any) -> bool:
    """管理员校验：操作员会话 或 管理令牌。"""
    if operator and operator.get("is_admin"):
        return True
    token = bearer_token(request.headers)
    if token and config.verify_admin_token(token):
        return True
    header = (request.headers.get("X-Admin-Token") or "").strip()
    if header and config.verify_admin_token(header):
        return True
    return False


def require_admin(config: Any, operator: Optional[Dict[str, Any]], request: Any) -> None:
    if not admin_ok(config, operator, request):
        raise forbidden("需要管理员权限：请使用操作员会话或 X-Admin-Token")
