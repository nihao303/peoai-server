"""配置中心：config.json 的默认值、读写、模型注册表与 API Key 管理。

设计要点：
    * 单文件 JSON 配置，便于运维手工编辑与备份；
    * 所有写入走临时文件 + 原子替换，避免半截文件；
    * 密码与令牌只保存哈希，明文仅在首次生成时输出一次；
    * 模型能力（vision / tools / streaming ...）是配置项，服务端据此校验请求。
"""
from __future__ import annotations

import copy
import hmac
import json
import os
import re
import secrets
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .util import deep_merge, digest, iso_time, now

# ---------------------------------------------------------------------------
# 默认模型能力
# ---------------------------------------------------------------------------

CAPABILITIES = (
    "vision",       # 是否接受图片输入（前端会自动解码展示）
    "tools",        # 是否支持工具/函数调用
    "streaming",    # 是否支持流式输出
    "reasoning",    # 是否标记为推理模型
    "json_mode",    # 是否支持 response_format=json_object
    "code",         # 是否标注为代码模型
    "audio",        # 是否接受音频输入（预留）
    "embeddings",   # 是否提供 embedding（人类无法提供，默认关闭）
)

DEFAULT_CAPABILITIES = {
    "vision": False,
    "tools": True,
    "streaming": True,
    "reasoning": False,
    "json_mode": True,
    "code": False,
    "audio": False,
    "embeddings": False,
}


def _model(
    model_id: str,
    label: str,
    description: str,
    capabilities: Optional[Dict[str, Any]] = None,
    context_window: int = 32000,
    max_output_tokens: int = 4096,
    default_params: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """构造一个模型定义，统一补齐字段。"""
    caps = dict(DEFAULT_CAPABILITIES)
    caps.update(capabilities or {})
    params = {"temperature": 0.7, "top_p": 1.0, "max_tokens": None, "stop": []}
    params.update(default_params or {})
    return {
        "id": model_id,
        "label": label,
        "description": description,
        "enabled": True,
        "aliases": [],
        "capabilities": caps,
        "context_window": context_window,
        "max_output_tokens": max_output_tokens,
        "default_params": params,
        "notes": "",
    }


DEFAULT_MODELS: List[Dict[str, Any]] = [
    _model(
        "peo-human-1",
        "PeoAI Human 1",
        "通用旗舰：图片理解、工具调用、流式输出全部开启，由真人操作员作答。",
        {"vision": True, "tools": True, "streaming": True, "reasoning": True, "code": True},
        context_window=128000,
        max_output_tokens=8192,
    ),
    _model(
        "peo-human-fast",
        "PeoAI Human Fast",
        "低延迟优先：适合短问答与轻量对话，不支持图片。",
        {"vision": False, "tools": True, "streaming": True},
        context_window=32000,
        max_output_tokens=2048,
        default_params={"temperature": 0.4},
    ),
    _model(
        "peo-human-vision",
        "PeoAI Human Vision",
        "多模态专用：专注截图、图表、试卷等图像理解，自动展示原图。",
        {"vision": True, "tools": True, "streaming": True, "reasoning": True},
        context_window=64000,
        max_output_tokens=4096,
    ),
    _model(
        "peo-human-code",
        "PeoAI Human Code",
        "代码与工具调用：适合 Agent、IDE 插件与需要结构化输出的场景。",
        {"vision": False, "tools": True, "streaming": True, "code": True, "json_mode": True},
        context_window=64000,
        max_output_tokens=8192,
        default_params={"temperature": 0.2},
    ),
    _model(
        "peo-human-mini",
        "PeoAI Human Mini",
        "轻量档：便宜、够快，用于连通性测试与简单分类任务。",
        {"vision": False, "tools": False, "streaming": True},
        context_window=16000,
        max_output_tokens=1024,
    ),
]


def default_config() -> Dict[str, Any]:
    """返回一份全新的默认配置（深拷贝，调用方可随意修改）。"""
    return copy.deepcopy(
        {
            "version": 1,
            "server": {
                "name": "PeoAI",
                "tagline": "把真人接入任何 AI API",
                "host": "0.0.0.0",
                "port": 5007,
                "public_base_url": "",
                "default_model": "peo-human-1",
                "allow_fallback_model": True,
                "console_enabled": True,
            },
            "security": {
                "operator_password_hash": "",
                "admin_token_hash": "",
                "require_api_key": True,
                "allowed_origins": ["*"],
                "operator_origins": ["*"],
                "session_ttl_seconds": 43200,
                "login_max_attempts": 6,
                "login_lock_seconds": 300,
                "max_body_bytes": 8 * 1024 * 1024,
                "max_messages": 200,
                "max_message_chars": 120000,
                "max_images": 4,
                "max_image_bytes": 2 * 1024 * 1024,
                "max_reply_chars": 200000,
                "trust_proxy_headers": True,
                "allow_remote_images": False,
                "hsts": False,
            },
            "queue": {
                "max_pending": 100,
                "request_ttl_seconds": 600,
                "claim_ttl_seconds": 900,
                "keepalive_seconds": 15,
                "history_limit": 300,
                "max_concurrent_per_key": 3,
                "persist_media": False,
                "typing_indicator": True,
            },
            "operator": {
                "display_name": "PeoAI 操作员",
                "show_client_ip": True,
                "auto_claim": True,
            },
            "models": DEFAULT_MODELS,
            "api_keys": [],
            "logging": {
                "level": "INFO",
                "audit": True,
                "max_bytes": 5 * 1024 * 1024,
                "backups": 3,
            },
        }
    )


def normalize_model(raw: Any) -> Dict[str, Any]:
    """把用户手写的模型定义补齐成完整结构。"""
    if not isinstance(raw, dict):
        raise ValueError("模型定义必须是对象")
    model_id = str(raw.get("id") or "").strip()
    if not model_id:
        raise ValueError("模型定义缺少 id")
    caps = dict(DEFAULT_CAPABILITIES)
    caps.update(raw.get("capabilities") or {})
    caps = {name: bool(caps.get(name)) for name in DEFAULT_CAPABILITIES}
    params = {"temperature": 0.7, "top_p": 1.0, "max_tokens": None, "stop": []}
    if isinstance(raw.get("default_params"), dict):
        params.update(raw["default_params"])
    aliases = raw.get("aliases") or []
    if not isinstance(aliases, list):
        aliases = [aliases]
    try:
        context_window = int(raw.get("context_window") or 32000)
    except (TypeError, ValueError):
        context_window = 32000
    try:
        max_output = int(raw.get("max_output_tokens") or 4096)
    except (TypeError, ValueError):
        max_output = 4096
    return {
        "id": model_id,
        "label": str(raw.get("label") or model_id),
        "description": str(raw.get("description") or ""),
        "enabled": bool(raw.get("enabled", True)),
        "aliases": [str(item).strip() for item in aliases if str(item).strip()],
        "capabilities": caps,
        "context_window": max(1024, context_window),
        "max_output_tokens": max(1, max_output),
        "default_params": params,
        "notes": str(raw.get("notes") or ""),
    }


class ConfigStore:
    """线程安全的配置仓库。"""

    def __init__(self, path: Path, logger: Any = None) -> None:
        self.path = Path(path)
        self.log = logger
        self._lock = threading.RLock()
        self.data = self._load()
        self.create_time = iso_time()

    # -- 载入与保存 ------------------------------------------------------
    def _load(self) -> Dict[str, Any]:
        raw: Dict[str, Any] = {}
        if self.path.exists():
            try:
                raw = json.loads(self.path.read_text("utf-8"))
            except (OSError, ValueError) as exc:
                if self.log:
                    self.log.warning("配置文件解析失败，使用默认配置: %s", exc)
                raw = {}
        if not isinstance(raw, dict):
            raw = {}
        data = deep_merge(default_config(), raw)
        models: List[Dict[str, Any]] = []
        for item in data.get("models") or []:
            try:
                models.append(normalize_model(item))
            except ValueError as exc:
                if self.log:
                    self.log.warning("跳过非法模型定义: %s", exc)
        data["models"] = models or copy.deepcopy(DEFAULT_MODELS)
        keys: List[Dict[str, Any]] = []
        for item in data.get("api_keys") or []:
            if not isinstance(item, dict) or not item.get("hash"):
                continue
            keys.append(
                {
                    "name": str(item.get("name") or "key"),
                    "prefix": str(item.get("prefix") or ""),
                    "hash": str(item["hash"]),
                    "created_at": item.get("created_at") or iso_time(),
                    "enabled": bool(item.get("enabled", True)),
                    "rpm": int(item.get("rpm") or 0),
                    "models": item.get("models") or ["*"],
                    "note": str(item.get("note") or ""),
                    "last_used": item.get("last_used"),
                }
            )
        data["api_keys"] = keys
        return data

    def save(self) -> None:
        """原子写盘（同目录临时文件 + os.replace）。"""
        with self._lock:
            payload = json.dumps(self.data, ensure_ascii=False, indent=2) + "\n"
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temp = self.path.parent / (self.path.name + ".tmp")
            temp.write_text(payload, "utf-8")
            try:
                os.chmod(temp, 0o600)
            except OSError:
                pass
            os.replace(str(temp), str(self.path))

    # -- 读取 ------------------------------------------------------------
    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            return copy.deepcopy(self.data)

    def public_snapshot(self) -> Dict[str, Any]:
        """给管理端用的脱敏快照：不含任何哈希。"""
        with self._lock:
            data = copy.deepcopy(self.data)
        security = data.get("security", {})
        security["operator_password_set"] = bool(security.pop("operator_password_hash", ""))
        security["admin_token_set"] = bool(security.pop("admin_token_hash", ""))
        keys = []
        for item in data.get("api_keys", []):
            keys.append(
                {
                    "name": item.get("name"),
                    "prefix": item.get("prefix"),
                    "created_at": item.get("created_at"),
                    "enabled": item.get("enabled", True),
                    "rpm": item.get("rpm", 0),
                    "models": item.get("models", ["*"]),
                    "note": item.get("note", ""),
                    "last_used": item.get("last_used"),
                }
            )
        data["api_keys"] = keys
        data["models"] = self.models(include_disabled=True)
        return data

    def get(self, dotted: str, default: Any = None) -> Any:
        """按 a.b.c 路径读取配置。"""
        node: Any = self.data
        for part in dotted.split("."):
            if not isinstance(node, dict) or part not in node:
                return default
            node = node[part]
        return node

    # -- 写入 ------------------------------------------------------------
    def update(self, patch: Dict[str, Any]) -> Dict[str, Any]:
        """合并写入并落盘；返回脱敏后的最新配置。"""
        with self._lock:
            merged = deep_merge(self.data, patch or {})
            if "models" in (patch or {}):
                models = []
                for item in merged.get("models") or []:
                    try:
                        models.append(normalize_model(item))
                    except ValueError:
                        continue
                merged["models"] = models or merged.get("models") or []
            self.data = merged
            self.save()
            return self.public_snapshot()

    def models(self, include_disabled: bool = False) -> List[Dict[str, Any]]:
        with self._lock:
            models = copy.deepcopy(self.data.get("models") or [])
        if not include_disabled:
            models = [item for item in models if item.get("enabled", True)]
        return models

    def model(self, name: str, include_disabled: bool = False) -> Optional[Dict[str, Any]]:
        """按 id 或别名查找模型（大小写不敏感）。"""
        needle = (name or "").strip().lower()
        for item in self.models(include_disabled=include_disabled):
            if item["id"].lower() == needle:
                return item
            for alias in item.get("aliases") or []:
                if str(alias).strip().lower() == needle:
                    return item
        return None

    def resolve_model(self, requested: str) -> Tuple[Optional[Dict[str, Any]], str]:
        """返回 (模型, 匹配方式)：exact / alias / fallback / missing。"""
        requested = (requested or "").strip()
        if requested:
            needle = requested.lower()
            for item in self.models(include_disabled=True):
                if item["id"].lower() == needle:
                    return item, ("exact" if item.get("enabled", True) else "disabled")
                for alias in item.get("aliases") or []:
                    if str(alias).strip().lower() == needle:
                        return item, "alias"
        if not requested:
            default_id = self.get("server.default_model")
            model = self.model(default_id)
            return model, "fallback" if model else "missing"
        if self.get("server.allow_fallback_model", True):
            model = self.model(self.get("server.default_model"))
            return model, ("fallback" if model else "missing")
        return None, "missing"

    def default_model(self) -> Optional[Dict[str, Any]]:
        return self.model(self.get("server.default_model", ""))

    # -- API Key ---------------------------------------------------------
    def add_api_key(
        self,
        name: str,
        rpm: int = 60,
        models: Optional[List[str]] = None,
        note: str = "",
        secret: Optional[str] = None,
    ) -> str:
        """创建 API Key，返回明文（仅此一次可见）。

        secret 非空时使用调用方自定义的值，否则随机生成 pk_ 开头的密钥。
        服务端始终只保存 SHA-256 摘要。
        """
        custom = (secret or "").strip()
        if custom:
            if not 16 <= len(custom) <= 128:
                raise ValueError("自定义 API Key 长度需在 16 到 128 个字符之间")
            if not re.match(r"^[A-Za-z0-9._\-]+$", custom):
                raise ValueError("自定义 API Key 只能包含字母、数字、点、下划线和连字符")
            if self.find_api_key(custom):
                raise ValueError("该 API Key 已存在，请换一个")
            token = custom
        else:
            token = "pk_" + secrets.token_urlsafe(30)
        prefix = token[:10]
        record = {
            "name": (name or "key").strip()[:48],
            "prefix": prefix,
            "hash": digest(token),
            "created_at": iso_time(now()),
            "enabled": True,
            "rpm": int(rpm or 0),
            "models": models or ["*"],
            "note": (note or "")[:200],
            "last_used": None,
        }
        with self._lock:
            if any(item.get("prefix") == prefix for item in self.data.get("api_keys") or []):
                raise ValueError("该 API Key 前 10 位与现有密钥冲突，请换一个")
            self.data.setdefault("api_keys", []).append(record)
            self.save()
        return token

    def find_api_key(self, token: str) -> Optional[Dict[str, Any]]:
        """按明文校验 API Key，返回对应记录（大小写恒定时间比较）。"""
        if not token:
            return None
        hashed = digest(token)
        with self._lock:
            keys = [copy.deepcopy(item) for item in self.data.get("api_keys") or []]
        for item in keys:
            stored = item.get("hash") or ""
            if stored and hmac.compare_digest(stored, hashed) and item.get("enabled", True):
                return item
        return None

    def touch_api_key(self, prefix: str) -> None:
        """记录密钥最近使用时间（不落盘，避免高频写）。"""
        with self._lock:
            for item in self.data.get("api_keys") or []:
                if item.get("prefix") == prefix:
                    item["last_used"] = iso_time(now())

    def remove_api_key(self, prefix: str) -> bool:
        with self._lock:
            keys = self.data.get("api_keys") or []
            kept = [item for item in keys if item.get("prefix") != prefix]
            if len(kept) == len(keys):
                return False
            self.data["api_keys"] = kept
            self.save()
            return True

    def toggle_api_key(self, prefix: str, enabled: bool) -> Optional[Dict[str, Any]]:
        with self._lock:
            for item in self.data.get("api_keys") or []:
                if item.get("prefix") == prefix:
                    item["enabled"] = bool(enabled)
                    self.save()
                    return copy.deepcopy(item)
        return None

    # -- 凭据 ------------------------------------------------------------
    def set_operator_password(self, plain: str) -> None:
        from werkzeug.security import generate_password_hash

        with self._lock:
            self.data.setdefault("security", {})["operator_password_hash"] = generate_password_hash(
                plain, method="pbkdf2:sha256:260000"
            )
            self.save()

    def verify_operator_password(self, plain: str) -> bool:
        from werkzeug.security import check_password_hash

        stored = self.get("security.operator_password_hash", "")
        if not stored or not plain:
            return False
        try:
            return check_password_hash(stored, plain)
        except (ValueError, TypeError):
            return False

    def set_admin_token(self, plain: str) -> None:
        with self._lock:
            self.data.setdefault("security", {})["admin_token_hash"] = digest(plain)
            self.save()

    def verify_admin_token(self, plain: str) -> bool:
        stored = self.get("security.admin_token_hash", "")
        if not stored or not plain:
            return False
        return hmac.compare_digest(stored, digest(plain))

    # -- 便捷派生 --------------------------------------------------------
    def limits(self) -> Dict[str, int]:
        """把安全限制整理成协议层直接使用的整数。"""
        security = self.get("security", {}) or {}
        return {
            "max_body_bytes": int(security.get("max_body_bytes", 8 * 1024 * 1024)),
            "max_messages": int(security.get("max_messages", 200)),
            "max_message_chars": int(security.get("max_message_chars", 120000)),
            "max_images": int(security.get("max_images", 4)),
            "max_image_bytes": int(security.get("max_image_bytes", 2 * 1024 * 1024)),
            "max_reply_chars": int(security.get("max_reply_chars", 200000)),
        }

    def origins(self, kind: str = "api") -> List[str]:
        security = self.get("security", {}) or {}
        key = "allowed_origins" if kind == "api" else "operator_origins"
        values = security.get(key) or ["*"]
        if not isinstance(values, list):
            values = [values]
        return [str(item).strip() for item in values if str(item).strip()]
