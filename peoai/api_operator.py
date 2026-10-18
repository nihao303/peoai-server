"""操作台接口：登录、队列、认领、增量、提交、事件流。

面向「人」的接口都走 Bearer 会话令牌，不使用 Cookie，
因此无需 CSRF 令牌；登录接口有按 IP 的失败锁定。
"""
from __future__ import annotations

import queue as queue_module
import time
from typing import Any, Dict, List, Optional

from flask import Blueprint, Response, current_app, jsonify, request

from . import __version__
from .auth import bearer_token, operator_from_request, require_operator
from .errors import bad_request, not_found, unauthorized
from .store import TERMINAL
from .util import client_ip, iso_time, now, truncate

bp = Blueprint("api_operator", __name__)


def _ctx():
    return current_app.extensions["peoai"]


def _operator() -> Dict[str, Any]:
    ctx = _ctx()
    return require_operator(ctx.config, ctx.sessions, request)


def _actor(operator: Dict[str, Any]) -> str:
    token = str(operator.get("token") or "")
    return "operator:" + (token[3:11] if token else "unknown")


def _ip() -> str:
    ctx = _ctx()
    return client_ip(request, bool(ctx.config.get("security.trust_proxy_headers", True)))


def _json_body() -> Dict[str, Any]:
    body = request.get_json(silent=True)
    if body is None:
        body = {}
    if not isinstance(body, dict):
        raise bad_request("请求体必须是 JSON 对象")
    return body


def _sse_response(generator) -> Response:
    response = Response(generator, mimetype="text/event-stream")
    response.headers["Cache-Control"] = "no-cache, no-transform"
    response.headers["X-Accel-Buffering"] = "no"
    return response


def _sse(obj: Any) -> str:
    import json

    return "data: " + json.dumps(obj, ensure_ascii=False, separators=(",", ":")) + "\n\n"


# ---------------------------------------------------------------------------
# 登录与自我介绍
# ---------------------------------------------------------------------------

@bp.get("/api/operator/bootstrap")
def bootstrap():
    """登录页需要的公开信息（不包含任何秘密）。"""
    ctx = _ctx()
    stats = ctx.store.stats()
    models = ctx.config.models()
    return jsonify(
        {
            "ok": True,
            "name": ctx.config.get("server.name", "PeoAI"),
            "tagline": ctx.config.get("server.tagline", ""),
            "version": __version__,
            "operator_name": ctx.config.get("operator.display_name", "操作员"),
            "models": [
                {
                    "id": model["id"],
                    "label": model.get("label"),
                    "capabilities": model.get("capabilities"),
                }
                for model in models
            ],
            "queue": {"pending": stats["pending"], "claimed": stats["claimed"]},
            "password_set": bool(ctx.config.get("security.operator_password_hash")),
            "require_api_key": bool(ctx.config.get("security.require_api_key", True)),
            "has_api_keys": bool(ctx.config.get("api_keys")),
            "caps": {"max_images": ctx.limits()["max_images"], "max_body_bytes": ctx.limits()["max_body_bytes"]},
        }
    )


@bp.post("/api/operator/login")
def login():
    ctx = _ctx()
    ip = _ip()
    allowed, retry = ctx.guard.check(ip)
    if not allowed:
        ctx.audit.write("login", actor="anonymous", target="operator", ip=ip, result="locked")
        response = jsonify(
            {
                "ok": False,
                "error": {
                    "message": "失败次数过多，请 %d 秒后再试" % retry,
                    "type": "rate_limit_error",
                    "code": "login_locked",
                },
            }
        )
        response.status_code = 429
        response.headers["Retry-After"] = str(retry)
        return response
    body = _json_body()
    password = str(body.get("password") or "")
    if not password:
        raise bad_request("请输入操作员密码")
    if not ctx.config.verify_operator_password(password):
        remaining = ctx.guard.fail(ip)
        ctx.audit.write("login", actor="anonymous", target="operator", ip=ip, result="denied")
        if remaining <= 0:
            raise unauthorized("密码错误次数过多，账号已临时锁定")
        raise unauthorized("密码错误，还可尝试 %d 次" % remaining)
    ctx.guard.success(ip)
    session = ctx.sessions.issue("operator", label=ip)
    ctx.audit.write("login", actor=session["token"][:10], target="operator", ip=ip, result="ok")
    return jsonify(
        {
            "ok": True,
            "token": session["token"],
            "expires_at": session["expires_at"],
            "expires_iso": iso_time(session["expires_at"]),
            "role": session["role"],
            "name": ctx.config.get("operator.display_name", "操作员"),
        }
    )


@bp.post("/api/operator/logout")
def logout():
    ctx = _ctx()
    token = bearer_token(request.headers)
    ctx.sessions.revoke(token)
    ctx.audit.write("logout", actor=(token or "")[:10], target="operator", ip=_ip(), result="ok")
    return jsonify({"ok": True})


@bp.get("/api/operator/me")
def me():
    ctx = _ctx()
    operator = _operator()
    return jsonify(
        {
            "ok": True,
            "name": ctx.config.get("operator.display_name", "操作员"),
            "role": operator.get("role", "operator"),
            "is_admin": bool(operator.get("is_admin")),
            "expires_at": operator.get("expires_at"),
            "expires_iso": iso_time(operator.get("expires_at")),
            "server": {
                "name": ctx.config.get("server.name", "PeoAI"),
                "version": __version__,
                "uptime_seconds": round(ctx.uptime(), 1),
            },
        }
    )


# ---------------------------------------------------------------------------
# 队列
# ---------------------------------------------------------------------------

@bp.get("/api/queue")
def queue_list():
    ctx = _ctx()
    _operator()
    status = request.args.get("status", "pending,claimed") or "all"
    try:
        limit = int(request.args.get("limit", 60))
    except (TypeError, ValueError):
        limit = 60
    search = request.args.get("q", "")
    return jsonify(
        {
            "ok": True,
            "jobs": ctx.store.list(
                status=status, limit=limit, search=search, show_ip=ctx.show_client_ip()
            ),
            "stats": ctx.store.stats(),
            "server_time": iso_time(),
        }
    )


@bp.get("/api/queue/<job_id>")
def queue_detail(job_id: str):
    ctx = _ctx()
    _operator()
    job = ctx.store.require(job_id)
    return jsonify(
        {
            "ok": True,
            "job": job.detail(include_inline=True, show_ip=ctx.show_client_ip()),
            "server_time": now(),
        }
    )


@bp.post("/api/queue/<job_id>/claim")
def queue_claim(job_id: str):
    ctx = _ctx()
    operator = _operator()
    job = ctx.store.claim(job_id, _actor(operator))
    ctx.audit.write("claim", actor=_actor(operator), target=job_id, ip=_ip())
    return jsonify({"ok": True, "job": job.detail(show_ip=ctx.show_client_ip())})


@bp.post("/api/queue/<job_id>/release")
def queue_release(job_id: str):
    ctx = _ctx()
    operator = _operator()
    job = ctx.store.release(job_id, _actor(operator))
    ctx.audit.write("release", actor=_actor(operator), target=job_id, ip=_ip())
    return jsonify({"ok": True, "job": job.summary(show_ip=ctx.show_client_ip())})


@bp.post("/api/queue/<job_id>/typing")
def queue_typing(job_id: str):
    ctx = _ctx()
    _operator()
    body = _json_body()
    job = ctx.store.set_typing(job_id, bool(body.get("typing", True)))
    return jsonify({"ok": True, "typing": job.typing})


@bp.post("/api/queue/<job_id>/delta")
def queue_delta(job_id: str):
    ctx = _ctx()
    operator = _operator()
    body = _json_body()
    text = body.get("text")
    if not isinstance(text, str):
        raise bad_request("text 必须是字符串")
    kind = str(body.get("kind") or "text")
    job = ctx.store.delta(job_id, text, _actor(operator), kind=kind)
    return jsonify(
        {
            "ok": True,
            "reply_text": job.reply_text,
            "reply_reasoning": job.reply_reasoning,
            "kind": kind,
            "deltas": len(job.deltas),
            "version": job.version,
        }
    )


@bp.post("/api/queue/<job_id>/reply")
def queue_reply(job_id: str):
    ctx = _ctx()
    operator = _operator()
    body = _json_body()
    text = body.get("text")
    if text is not None and not isinstance(text, str):
        raise bad_request("text 必须是字符串或省略")
    reasoning = body.get("reasoning")
    if reasoning is not None and not isinstance(reasoning, str):
        raise bad_request("reasoning 必须是字符串或省略")
    tool_calls = body.get("tool_calls") or []
    if not isinstance(tool_calls, list):
        raise bad_request("tool_calls 必须是数组")
    finish_reason = body.get("finish_reason")
    if finish_reason is not None and finish_reason not in ("stop", "length", "tool_calls", "content_filter"):
        raise bad_request("finish_reason 取值不合法")
    usage_note = body.get("usage_note")
    job = ctx.store.reply(
        job_id,
        text=text,
        reasoning=reasoning,
        tool_calls=tool_calls,
        finish_reason=finish_reason,
        usage_note=str(usage_note)[:200] if usage_note else None,
        actor=_actor(operator),
    )
    ctx.audit.write(
        "reply",
        actor=_actor(operator),
        target=job_id,
        ip=_ip(),
        detail={
            "chars": len(job.reply_text),
            "reasoning_chars": len(job.reply_reasoning),
            "tools": len(job.reply_tools),
        },
    )
    return jsonify({"ok": True, "job": job.detail(show_ip=ctx.show_client_ip())})


@bp.post("/api/queue/<job_id>/reject")
def queue_reject(job_id: str):
    ctx = _ctx()
    operator = _operator()
    body = _json_body()
    reason = str(body.get("reason") or "操作员拒绝了该请求")[:300]
    job = ctx.store.reject(job_id, reason, _actor(operator))
    ctx.audit.write("reject", actor=_actor(operator), target=job_id, ip=_ip(), detail={"reason": reason})
    return jsonify({"ok": True, "job": job.summary(show_ip=ctx.show_client_ip())})


# ---------------------------------------------------------------------------
# 事件流
# ---------------------------------------------------------------------------

@bp.get("/api/events")
def events():
    ctx = _ctx()
    token = bearer_token(request.headers) or request.args.get("access_token")
    session = ctx.sessions.verify(token)
    if not session:
        raise unauthorized("未登录或会话已过期")

    def generator():
        bucket = ctx.store.subscribe_events()
        try:
            yield "retry: 3000\n\n"
            yield _sse(
                {
                    "type": "queue",
                    "jobs": ctx.store.list(
                        status="all", limit=80, show_ip=ctx.show_client_ip()
                    ),
                    "stats": ctx.store.stats(),
                }
            )
            while True:
                try:
                    item = bucket.get(timeout=15)
                except queue_module.Empty:
                    yield ": ping\n\n"
                    continue
                yield _sse(item)
        finally:
            ctx.store.unsubscribe_events(bucket)

    return _sse_response(generator())


# ---------------------------------------------------------------------------
# 元信息
# ---------------------------------------------------------------------------

@bp.get("/api/stats")
def stats():
    ctx = _ctx()
    _operator()
    data = ctx.store.stats()
    data["sessions"] = ctx.sessions.count()
    data["uptime_seconds"] = round(ctx.uptime(), 1)
    data["version"] = __version__
    return jsonify({"ok": True, "stats": data})


@bp.get("/api/models")
def models():
    ctx = _ctx()
    _operator()
    return jsonify({"ok": True, "models": ctx.config.models()})


@bp.get("/api/config")
def config_view():
    ctx = _ctx()
    _operator()
    return jsonify(
        {
            "ok": True,
            "config": ctx.config.public_snapshot(),
            "limits": ctx.limits(),
            "uptime_seconds": round(ctx.uptime(), 1),
            "version": __version__,
            "data_dir": str(ctx.data_dir),
        }
    )
