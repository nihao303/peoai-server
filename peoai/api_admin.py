"""管理接口：模型、API Key、安全参数、密码与审计。

鉴权：操作员会话（单操作员部署默认具备管理权）或 X-Admin-Token / Bearer 管理令牌。
所有写操作都会记入审计日志。
"""
from __future__ import annotations

import secrets
from typing import Any, Dict, List

from flask import Blueprint, current_app, jsonify, request

from .auth import bearer_token, operator_from_request, require_admin
from .config import normalize_model
from .errors import bad_request, not_found
from .util import client_ip, iso_time

bp = Blueprint("api_admin", __name__)


def _ctx():
    return current_app.extensions["peoai"]


def _guard() -> Dict[str, Any]:
    ctx = _ctx()
    operator = operator_from_request(ctx.config, ctx.sessions, request)
    require_admin(ctx.config, operator, request)
    return operator or {"role": "admin"}


def _actor(operator: Dict[str, Any]) -> str:
    token = str(operator.get("token") or bearer_token(request.headers) or "")
    if token:
        return "admin:" + token[:10]
    return "admin:token"


def _ip() -> str:
    ctx = _ctx()
    return client_ip(request, bool(ctx.config.get("security.trust_proxy_headers", True)))


def _json_body() -> Dict[str, Any]:
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        raise bad_request("请求体必须是 JSON 对象")
    return body


SECTION_KEYS = {
    "server": (
        "name",
        "tagline",
        "default_model",
        "allow_fallback_model",
        "public_base_url",
        "console_enabled",
    ),
    "security": (
        "require_api_key",
        "allowed_origins",
        "operator_origins",
        "session_ttl_seconds",
        "login_max_attempts",
        "login_lock_seconds",
        "max_body_bytes",
        "max_messages",
        "max_message_chars",
        "max_images",
        "max_image_bytes",
        "max_reply_chars",
        "trust_proxy_headers",
        "allow_remote_images",
        "hsts",
    ),
    "queue": (
        "max_pending",
        "request_ttl_seconds",
        "claim_ttl_seconds",
        "keepalive_seconds",
        "history_limit",
        "max_concurrent_per_key",
        "persist_media",
        "typing_indicator",
    ),
    "operator": ("display_name", "show_client_ip", "auto_claim"),
    "logging": ("level", "audit"),
}

INT_RANGES = {
    ("security", "session_ttl_seconds"): (300, 30 * 86400),
    ("security", "login_max_attempts"): (1, 100),
    ("security", "login_lock_seconds"): (10, 86400),
    ("security", "max_body_bytes"): (64 * 1024, 32 * 1024 * 1024),
    ("security", "max_messages"): (1, 1000),
    ("security", "max_message_chars"): (256, 2 * 1024 * 1024),
    ("security", "max_images"): (1, 16),
    ("security", "max_image_bytes"): (16 * 1024, 16 * 1024 * 1024),
    ("security", "max_reply_chars"): (256, 2 * 1024 * 1024),
    ("queue", "max_pending"): (1, 5000),
    ("queue", "request_ttl_seconds"): (10, 86400),
    ("queue", "claim_ttl_seconds"): (10, 86400),
    ("queue", "keepalive_seconds"): (5, 120),
    ("queue", "history_limit"): (10, 5000),
    ("queue", "max_concurrent_per_key"): (1, 100),
}

BOOL_KEYS = {
    ("server", "allow_fallback_model"),
    ("server", "console_enabled"),
    ("security", "require_api_key"),
    ("security", "trust_proxy_headers"),
    ("security", "allow_remote_images"),
    ("security", "hsts"),
    ("queue", "persist_media"),
    ("queue", "typing_indicator"),
    ("operator", "show_client_ip"),
    ("operator", "auto_claim"),
    ("logging", "audit"),
}

LIST_KEYS = {("security", "allowed_origins"), ("security", "operator_origins")}


def _clean_patch(patch: Dict[str, Any]) -> Dict[str, Any]:
    """只接受白名单字段，并做类型与范围校验。"""
    cleaned: Dict[str, Any] = {}
    for section, keys in SECTION_KEYS.items():
        if section not in patch:
            continue
        raw_section = patch[section]
        if not isinstance(raw_section, dict):
            raise bad_request("%s 必须是对象" % section)
        target: Dict[str, Any] = {}
        for key in keys:
            if key not in raw_section:
                continue
            value = raw_section[key]
            pair = (section, key)
            if pair in INT_RANGES:
                low, high = INT_RANGES[pair]
                try:
                    number = int(value)
                except (TypeError, ValueError):
                    raise bad_request("%s.%s 必须是整数" % (section, key))
                target[key] = max(low, min(high, number))
            elif pair in BOOL_KEYS:
                target[key] = bool(value)
            elif pair in LIST_KEYS:
                if isinstance(value, str):
                    value = [value]
                if not isinstance(value, list):
                    raise bad_request("%s.%s 必须是数组" % (section, key))
                items = [str(item).strip() for item in value if str(item).strip()]
                target[key] = items[:32] or ["*"]
            elif key in ("name", "tagline", "default_model", "public_base_url", "display_name", "level"):
                target[key] = str(value)[:200]
            else:
                target[key] = value
        if target:
            cleaned[section] = target
    if not cleaned:
        raise bad_request("没有可更新的字段")
    return cleaned


@bp.get("/api/admin/config")
def get_config():
    ctx = _ctx()
    _guard()
    return jsonify(
        {
            "ok": True,
            "config": ctx.config.public_snapshot(),
            "limits": ctx.limits(),
            "version": current_app.extensions.get("peoai_version"),
            "data_dir": str(ctx.data_dir),
            "server_time": iso_time(),
        }
    )


@bp.put("/api/admin/config")
def put_config():
    ctx = _ctx()
    operator = _guard()
    patch = _clean_patch(_json_body())
    if "server" in patch and "default_model" in patch["server"]:
        model_id = patch["server"]["default_model"]
        if not ctx.config.model(model_id):
            raise bad_request("默认模型不存在：%s" % model_id)
    updated = ctx.config.update(patch)
    ctx.audit.write(
        "config.update",
        actor=_actor(operator),
        target=",".join("%s" % key for key in patch.keys()),
        ip=_ip(),
        detail={"sections": ",".join(patch.keys())},
    )
    return jsonify({"ok": True, "config": updated})


@bp.post("/api/admin/models")
def upsert_model():
    ctx = _ctx()
    operator = _guard()
    try:
        model = normalize_model(_json_body())
    except ValueError as exc:
        raise bad_request(str(exc))
    models = ctx.config.snapshot().get("models") or []
    replaced = False
    for index, item in enumerate(models):
        if item.get("id") == model["id"]:
            models[index] = model
            replaced = True
            break
    if not replaced:
        models.append(model)
    ctx.config.update({"models": models})
    ctx.audit.write(
        "model.upsert",
        actor=_actor(operator),
        target=model["id"],
        ip=_ip(),
        detail={"replaced": replaced},
    )
    return jsonify({"ok": True, "model": model, "models": ctx.config.models(include_disabled=True)})


@bp.delete("/api/admin/models/<model_id>")
def delete_model(model_id: str):
    ctx = _ctx()
    operator = _guard()
    models = ctx.config.snapshot().get("models") or []
    kept = [item for item in models if item.get("id") != model_id]
    if len(kept) == len(models):
        raise not_found("模型不存在：%s" % model_id)
    if not kept:
        raise bad_request("至少需要保留一个模型")
    ctx.config.update({"models": kept})
    if ctx.config.get("server.default_model") == model_id:
        ctx.config.update({"server": {"default_model": kept[0]["id"]}})
    ctx.audit.write("model.delete", actor=_actor(operator), target=model_id, ip=_ip())
    return jsonify({"ok": True, "models": ctx.config.models(include_disabled=True)})


@bp.post("/api/admin/keys")
def create_key():
    ctx = _ctx()
    operator = _guard()
    body = _json_body()
    name = str(body.get("name") or "")[:48]
    if not name:
        raise bad_request("请为该 API Key 取一个名字")
    try:
        rpm = int(body.get("rpm") or 60)
    except (TypeError, ValueError):
        raise bad_request("rpm 必须是整数")
    rpm = max(0, min(100000, rpm))
    models = body.get("models") or ["*"]
    if isinstance(models, str):
        models = [models]
    if not isinstance(models, list):
        raise bad_request("models 必须是数组")
    models = [str(item).strip() for item in models if str(item).strip()] or ["*"]
    known = {item["id"] for item in ctx.config.models(include_disabled=True)}
    for item in models:
        if item != "*" and item not in known:
            raise bad_request("模型不存在：%s" % item)
    custom = str(body.get("key") or "").strip() or None
    try:
        token = ctx.config.add_api_key(
            name,
            rpm=rpm,
            models=models,
            note=str(body.get("note") or ""),
            secret=custom,
        )
    except ValueError as exc:
        raise bad_request(str(exc))
    ctx.audit.write(
        "key.create",
        actor=_actor(operator),
        target=name,
        ip=_ip(),
        detail={"rpm": rpm, "custom": bool(custom)},
    )
    return jsonify(
        {
            "ok": True,
            "key": token,
            "name": name,
            "rpm": rpm,
            "models": models,
            "custom": bool(custom),
        }
    )


@bp.delete("/api/admin/keys/<prefix>")
def delete_key(prefix: str):
    ctx = _ctx()
    operator = _guard()
    if not ctx.config.remove_api_key(prefix):
        raise not_found("API Key 不存在")
    ctx.audit.write("key.delete", actor=_actor(operator), target=prefix, ip=_ip())
    return jsonify({"ok": True, "config": ctx.config.public_snapshot()})


@bp.post("/api/admin/keys/<prefix>/toggle")
def toggle_key(prefix: str):
    ctx = _ctx()
    operator = _guard()
    body = _json_body()
    record = ctx.config.toggle_api_key(prefix, bool(body.get("enabled", True)))
    if not record:
        raise not_found("API Key 不存在")
    ctx.audit.write(
        "key.toggle", actor=_actor(operator), target=prefix, ip=_ip(), detail={"enabled": record["enabled"]}
    )
    return jsonify({"ok": True, "config": ctx.config.public_snapshot()})


@bp.post("/api/admin/password")
def change_password():
    ctx = _ctx()
    operator = _guard()
    body = _json_body()
    current = str(body.get("current") or "")
    password = str(body.get("password") or "")
    if not password or len(password) < 10:
        raise bad_request("新密码至少 10 位")
    if not ctx.config.verify_operator_password(current):
        ctx.audit.write("password.change", actor=_actor(operator), target="operator", ip=_ip(), result="denied")
        raise bad_request("当前密码不正确")
    ctx.config.set_operator_password(password)
    ctx.sessions.revoke_all()
    ctx.guard.reset()
    ctx.audit.write("password.change", actor=_actor(operator), target="operator", ip=_ip())
    return jsonify({"ok": True, "relogin": True})


@bp.post("/api/admin/admin-token")
def rotate_admin_token():
    ctx = _ctx()
    operator = _guard()
    token = "adm_" + secrets.token_urlsafe(24)
    ctx.config.set_admin_token(token)
    ctx.audit.write("admin_token.rotate", actor=_actor(operator), target="admin", ip=_ip())
    return jsonify({"ok": True, "token": token})


@bp.get("/api/admin/audit")
def audit_tail():
    ctx = _ctx()
    _guard()
    try:
        limit = int(request.args.get("limit", 100))
    except (TypeError, ValueError):
        limit = 100
    return jsonify({"ok": True, "records": ctx.audit.tail(limit)})


@bp.post("/api/admin/sessions/revoke")
def revoke_sessions():
    ctx = _ctx()
    operator = _guard()
    count = ctx.sessions.revoke_all()
    ctx.audit.write("sessions.revoke", actor=_actor(operator), target="all", ip=_ip(), detail={"count": count})
    return jsonify({"ok": True, "revoked": count})
