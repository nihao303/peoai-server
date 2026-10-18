"""Flask 应用工厂：装配上下文、安全响应头、错误处理与路由。"""
from __future__ import annotations

import logging
import os
import secrets
import sys
from dataclasses import dataclass, field
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any, Dict, Optional

from flask import Flask, Response, jsonify, request, send_from_directory
from werkzeug.exceptions import HTTPException

from . import __version__
from .audit import AuditLog
from .auth import LoginGuard, SessionStore
from .config import ConfigStore
from .errors import PeoaiError, error_payload, payload_too_large
from .ratelimit import RateLimiter
from .store import JobStore
from .util import client_ip, iso_time, now

MAX_BODY_HARD_CAP = 32 * 1024 * 1024

CONSOLE_CSP = (
    "default-src 'self'; "
    "img-src 'self' data: blob: https: http:; "
    "style-src 'self' 'unsafe-inline'; "
    "script-src 'self' 'unsafe-inline'; "
    "connect-src 'self' http: https:; "
    "font-src 'self' data:; "
    "base-uri 'none'; "
    "form-action 'self'; "
    "frame-ancestors 'none'"
)


@dataclass
class AppContext:
    """应用级单例集合，挂在 app.extensions['peoai'] 上。"""

    root: Path
    data_dir: Path
    static_dir: Path
    config: ConfigStore
    store: JobStore
    sessions: SessionStore
    guard: LoginGuard
    limiter: RateLimiter
    audit: AuditLog
    logger: logging.Logger
    started_at: float = field(default_factory=now)
    credentials: Dict[str, Any] = field(default_factory=dict)

    def limits(self) -> Dict[str, int]:
        return self.config.limits()

    def uptime(self) -> float:
        return max(0.0, now() - self.started_at)

    def show_client_ip(self) -> bool:
        return bool(self.config.get("operator.show_client_ip", True))


def setup_logging(data_dir: Path, level: str = "INFO") -> logging.Logger:
    """日志同时写文件与控制台，文件按 5MB 滚动。"""
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass
    logger = logging.getLogger("peoai")
    logger.setLevel(getattr(logging, str(level).upper(), logging.INFO))
    if logger.handlers:
        return logger
    formatter = logging.Formatter(
        "%(asctime)s %(levelname)-7s %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
    )
    try:
        data_dir.mkdir(parents=True, exist_ok=True)
        file_handler = RotatingFileHandler(
            str(data_dir / "peoai.log"), maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"
        )
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    except OSError:
        pass
    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(formatter)
    logger.addHandler(stream_handler)
    logger.propagate = False
    return logger


def build_context(root: Optional[Path] = None) -> AppContext:
    """按环境变量 / 传入目录构建上下文（测试可传临时目录）。"""
    resolved_root = Path(
        root or os.environ.get("PEOAI_HOME") or Path(__file__).resolve().parent.parent
    ).resolve()
    data_dir = Path(os.environ.get("PEOAI_DATA") or (resolved_root / "data"))
    data_dir.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(data_dir, 0o700)
    except OSError:
        pass
    logger = setup_logging(data_dir, os.environ.get("PEOAI_LOG_LEVEL", "INFO"))

    config_path = Path(os.environ.get("PEOAI_CONFIG") or (resolved_root / "config.json"))
    first_run = not config_path.exists()
    config = ConfigStore(config_path, logger)
    if first_run:
        config.save()

    audit = AuditLog(
        data_dir / "audit.log",
        enabled=bool(config.get("logging.audit", True)),
        max_bytes=int(config.get("logging.max_bytes", 5 * 1024 * 1024)),
        backups=int(config.get("logging.backups", 3)),
    )
    store = JobStore(config, data_dir, logger)
    sessions = SessionStore(int(config.get("security.session_ttl_seconds", 43200)))
    guard = LoginGuard(
        int(config.get("security.login_max_attempts", 6)),
        int(config.get("security.login_lock_seconds", 300)),
    )
    limiter = RateLimiter(60)

    ctx = AppContext(
        root=resolved_root,
        data_dir=data_dir,
        static_dir=Path(__file__).resolve().parent.parent / "static",
        config=config,
        store=store,
        sessions=sessions,
        guard=guard,
        limiter=limiter,
        audit=audit,
        logger=logger,
    )
    bootstrap_credentials(ctx)
    return ctx


def bootstrap_credentials(ctx: AppContext) -> None:
    """首次启动生成操作员密码、管理令牌与默认 API Key，并提示一次。"""
    created: Dict[str, Any] = {}
    lines = []
    if not ctx.config.get("security.operator_password_hash"):
        password = secrets.token_urlsafe(12)
        ctx.config.set_operator_password(password)
        created["operator_password"] = password
        lines.append("operator password: " + password)
    if not ctx.config.get("security.admin_token_hash"):
        token = "adm_" + secrets.token_urlsafe(24)
        ctx.config.set_admin_token(token)
        created["admin_token"] = token
        lines.append("admin token: " + token)
    if not (ctx.config.get("api_keys") or []) and ctx.config.get("security.require_api_key", True):
        key = ctx.config.add_api_key("default", rpm=120, note="首次启动自动创建")
        created["api_key"] = key
        lines.append("api key: " + key + "  (name=default, rpm=120)")
    ctx.credentials = created
    if not created:
        return
    path = ctx.data_dir / "bootstrap.txt"
    try:
        path.write_text(
            "# PeoAI 初始凭据，仅生成一次。登录后请修改密码并删除本文件。\n"
            + "\n".join(lines)
            + "\n",
            "utf-8",
        )
        os.chmod(path, 0o600)
    except OSError:
        pass
    ctx.logger.warning("=" * 68)
    ctx.logger.warning("首次启动已生成凭据（详见 %s）", path)
    for line in lines:
        ctx.logger.warning("  %s", line)
    ctx.logger.warning("请尽快登录控制台修改密码，或删除 config.json 中的对应哈希后重启重新生成。")
    ctx.logger.warning("=" * 68)


def family_for_path(path: str) -> str:
    """按路径推断错误体格式。"""
    if path.startswith("/v1/messages"):
        return "anthropic"
    if path.startswith("/v1beta"):
        return "gemini"
    if path.startswith(("/api/chat", "/api/tags", "/api/show", "/api/version", "/api/ps")):
        return "ollama"
    if path.startswith("/api/"):
        return "console"
    return "openai"


def create_app(root: Optional[Path] = None) -> Flask:
    """创建 Flask 应用。"""
    ctx = build_context(root)
    app = Flask(__name__, static_folder=str(ctx.static_dir), static_url_path="/static")
    app.config["MAX_CONTENT_LENGTH"] = max(
        MAX_BODY_HARD_CAP, int(ctx.limits()["max_body_bytes"]) * 2
    )
    app.config["JSON_AS_ASCII"] = False
    app.json.ensure_ascii = False
    app.extensions["peoai"] = ctx
    app.extensions["peoai_version"] = __version__

    from . import api_admin, api_operator, api_v1

    app.register_blueprint(api_v1.bp)
    app.register_blueprint(api_operator.bp)
    app.register_blueprint(api_admin.bp)

    # -- 请求前：体积预检与预检请求 -------------------------------------
    @app.before_request
    def _before() -> Optional[Response]:
        limit = int(ctx.limits()["max_body_bytes"])
        length = request.content_length or 0
        if length > limit:
            raise payload_too_large("请求体超过上限（%d 字节）" % limit)
        if request.method == "OPTIONS":
            return Response(status=204)
        return None

    # -- 响应头：CORS 与安全头 -------------------------------------------
    @app.after_request
    def _headers(response: Response) -> Response:
        origin = request.headers.get("Origin")
        is_api = request.path.startswith(("/v1", "/api", "/v1beta")) or request.path in ("/healthz",)
        if origin and is_api:
            kind = "operator" if request.path.startswith("/api/operator") else "api"
            allowed = ctx.config.origins(kind)
            if "*" in allowed or origin in allowed:
                response.headers["Access-Control-Allow-Origin"] = "*" if "*" in allowed else origin
                response.headers["Vary"] = "Origin"
                response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, PATCH, DELETE, OPTIONS"
                response.headers["Access-Control-Allow-Headers"] = (
                    "Authorization, Content-Type, Accept, X-Api-Key, X-Goog-Api-Key, "
                    "Anthropic-Version, Anthropic-Beta, X-Admin-Token, X-PeoAI-Token, "
                    "Cache-Control, Pragma, X-Requested-With"
                )
                response.headers["Access-Control-Expose-Headers"] = (
                    "X-PeoAI-Request, X-PeoAI-Model, X-PeoAI-Protocol, X-PeoAI-Human, Retry-After"
                )
                response.headers["Access-Control-Max-Age"] = "600"
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault(
            "Permissions-Policy", "geolocation=(), microphone=(), camera=(), payment=()"
        )
        if is_api:
            response.headers.setdefault("Cache-Control", "no-store")
        if request.path in ("/", "/console") and response.mimetype == "text/html":
            response.headers["Content-Security-Policy"] = CONSOLE_CSP
        if ctx.config.get("security.hsts"):
            response.headers.setdefault(
                "Strict-Transport-Security", "max-age=31536000; includeSubDomains"
            )
        return response

    # -- 错误处理 --------------------------------------------------------
    @app.errorhandler(PeoaiError)
    def _peoai_error(exc: PeoaiError):
        family = family_for_path(request.path)
        body, status = error_payload(family, exc)
        response = jsonify(body)
        response.status_code = status
        if exc.retry_after:
            response.headers["Retry-After"] = str(exc.retry_after)
        if family == "openai" and status == 401:
            response.headers["WWW-Authenticate"] = 'Bearer realm="peoai"'
        ctx.logger.info("请求失败 %s %s -> %s %s", request.method, request.path, status, exc.message)
        return response

    @app.errorhandler(413)
    def _too_large(_exc):
        limit = int(ctx.limits()["max_body_bytes"])
        body, status = error_payload(
            family_for_path(request.path), payload_too_large("请求体超过上限（%d 字节）" % limit)
        )
        response = jsonify(body)
        response.status_code = status
        return response

    @app.errorhandler(404)
    def _not_found(_exc):
        path = request.path
        if path.startswith(("/v1", "/api", "/v1beta")):
            from .errors import not_found

            body, status = error_payload(family_for_path(path), not_found("接口不存在: " + path))
            response = jsonify(body)
            response.status_code = status
            return response
        return Response("404 Not Found", status=404, mimetype="text/plain")

    @app.errorhandler(405)
    def _method_not_allowed(_exc):
        from .errors import PeoaiError as _Err

        body, status = error_payload(
            family_for_path(request.path),
            _Err("请求方法不允许: " + request.method, 405, "invalid_request_error", "method_not_allowed"),
        )
        response = jsonify(body)
        response.status_code = status
        return response

    @app.errorhandler(Exception)
    def _unhandled(exc):
        if isinstance(exc, HTTPException):
            return exc
        ctx.logger.exception("未处理异常: %s", exc)
        message = "服务器内部错误" if not app.debug else str(exc)
        body, status = error_payload(
            family_for_path(request.path),
            PeoaiError(message, 500, "api_error", "internal_error"),
        )
        response = jsonify(body)
        response.status_code = status
        return response

    # -- 控制台与健康检查 -------------------------------------------------
    @app.get("/")
    @app.get("/console")
    def console():
        if not ctx.config.get("server.console_enabled", True):
            return jsonify({"ok": False, "error": {"message": "控制台已关闭"}}), 403
        index = ctx.static_dir / "peoai.html"
        if not index.exists():
            return Response("console not installed", status=404, mimetype="text/plain")
        return send_from_directory(str(ctx.static_dir), "peoai.html")

    @app.get("/healthz")
    @app.get("/api/health")
    def health():
        stats = ctx.store.stats()
        return jsonify(
            {
                "ok": True,
                "name": ctx.config.get("server.name", "PeoAI"),
                "version": __version__,
                "uptime_seconds": round(ctx.uptime(), 1),
                "time": iso_time(),
                "queue": {"pending": stats["pending"], "claimed": stats["claimed"]},
                "models": len(ctx.config.models()),
            }
        )

    @app.get("/robots.txt")
    def robots():
        return Response("User-agent: *\nDisallow: /api/\nDisallow: /v1/\n", mimetype="text/plain")

    @app.get("/favicon.ico")
    def favicon():
        return Response(status=204)

    @app.teardown_appcontext
    def _teardown(_exc):
        return None

    ctx.logger.info(
        "PeoAI v%s 已就绪：模型 %d 个，数据目录 %s",
        __version__,
        len(ctx.config.models()),
        ctx.data_dir,
    )
    return app
