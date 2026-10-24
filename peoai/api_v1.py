"""对外 API 路由（OpenAI / Anthropic / Gemini / Ollama 四家兼容）。

统一流程：
    校验 API Key -> 解析协议 -> 校验模型能力 -> 入队 -> 等待真人作答 -> 按协议渲染。
"""
from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

from flask import Blueprint, Response, current_app, jsonify, request

from .auth import key_allows_model, resolve_api_key
from .errors import (
    PeoaiError,
    bad_request,
    forbidden,
    not_found,
    rate_limited,
    unsupported,
)
from .protocols import anthropic, gemini, ollama, openai
from .store import Job, raw_preview
from .tokens import usage_for
from .util import client_ip, user_agent

bp = Blueprint("api_v1", __name__)


def _ctx():
    return current_app.extensions["peoai"]


def _json_body() -> Dict[str, Any]:
    if not request.get_data(cache=True):
        raise bad_request("请求体不能为空")
    body = request.get_json(silent=True)
    if body is None:
        raise bad_request("请求体必须是合法 JSON（Content-Type: application/json）")
    if not isinstance(body, dict):
        raise bad_request("请求体必须是 JSON 对象")
    return body


def _client_info() -> Tuple[str, str]:
    ctx = _ctx()
    trust_proxy = bool(ctx.config.get("security.trust_proxy_headers", True))
    return client_ip(request, trust_proxy), user_agent(request)


def _resolve_key() -> Dict[str, Any]:
    ctx = _ctx()
    key, _mode = resolve_api_key(ctx.config, request)
    rpm = int(key.get("rpm") or 0)
    if rpm > 0:
        allowed, retry, _remaining = ctx.limiter.hit(
            "key:" + str(key.get("prefix") or "anonymous"), rpm
        )
        if not allowed:
            raise rate_limited(
                "该 API Key 请求过于频繁（上限 %d 次/分钟）" % rpm, retry_after=retry
            )
    ctx.config.touch_api_key(str(key.get("prefix") or ""))
    return key


def _pick_model(requested: str) -> Tuple[Dict[str, Any], str]:
    ctx = _ctx()
    model, match = ctx.config.resolve_model(requested)
    if not model:
        raise not_found("模型不存在：%s" % (requested or "(空)"))
    if not model.get("enabled", True):
        raise not_found("模型已停用：%s" % model["id"])
    return model, match


def _prepare(
    parsed: Any,
    key: Dict[str, Any],
    protocol: str,
    body: Dict[str, Any],
) -> Tuple[Job, Dict[str, Any]]:
    """能力校验 + 参数裁剪 + 入队。"""
    ctx = _ctx()
    model, match = _pick_model(parsed.model)
    if not key_allows_model(key, model["id"]):
        raise forbidden("当前 API Key 无权使用模型 %s" % model["id"])
    caps = model.get("capabilities") or {}
    if any(message.get("images") for message in parsed.messages) and not caps.get("vision"):
        raise bad_request(
            "模型 %s 未开启图片输入能力，请改用支持多模态的模型" % model["id"]
        )
    if parsed.tools and not caps.get("tools"):
        raise bad_request("模型 %s 未开启工具调用能力" % model["id"])
    if parsed.stream and not caps.get("streaming"):
        raise unsupported("模型 %s 未开启流式输出，请设置 stream=false" % model["id"])

    params = dict(parsed.params or {})
    warnings = []
    if match == "fallback" and parsed.model:
        warnings.append("请求的模型 %s 不存在，已回退到 %s" % (parsed.model, model["id"]))
    defaults = model.get("default_params") or {}
    applied_defaults = []
    for param_name in ("temperature", "top_p", "max_tokens", "stop"):
        if param_name in params:
            continue
        value = defaults.get(param_name)
        if value is None or value == [] or value == "":
            continue
        params[param_name] = value
        applied_defaults.append(param_name)
    max_output = int(model.get("max_output_tokens") or 4096)
    max_tokens = params.get("max_tokens")
    if isinstance(max_tokens, (int, float)) and max_tokens > max_output:
        params["max_tokens"] = max_output
        warnings.append("max_tokens 已按模型上限裁剪为 %d" % max_output)
    response_format = params.get("response_format")
    if isinstance(response_format, dict):
        fmt = str(response_format.get("type") or "")
        if fmt in ("json_object", "json_schema") and not caps.get("json_mode"):
            warnings.append("模型未开启 JSON 模式，结构化输出得不到保证")
        if fmt == "json_schema" and not isinstance(response_format.get("json_schema"), dict):
            raise bad_request("response_format.json_schema 必须是对象")

    ip, ua = _client_info()
    conversation_hint = (
        request.headers.get("X-PeoAI-Conversation")
        or request.headers.get("X-Conversation-Id")
        or ""
    ).strip()
    meta = {
        "protocol": protocol,
        "family": "openai" if protocol.startswith("openai") else protocol.split(".")[0],
        "match": match,
        "capabilities": caps,
        "warnings": warnings,
        "applied_defaults": applied_defaults,
        "api_key_mode": "anonymous",
    }
    if conversation_hint:
        meta["conversation"] = conversation_hint[:128]
    parsed_user = ""
    if isinstance(getattr(parsed, "meta", None), dict):
        parsed_user = str(parsed.meta.get("user") or "").strip()
    if parsed_user:
        meta["user"] = parsed_user[:128]
    job = ctx.store.create(
        protocol=protocol,
        model=model["id"],
        request_model=parsed.model or model["id"],
        stream=bool(parsed.stream),
        messages=parsed.messages,
        tools=parsed.tools,
        tool_choice=parsed.tool_choice,
        params=params,
        api_key=str(key.get("name") or "anonymous"),
        client_ip=ip,
        user_agent=ua,
        meta=meta,
        raw=raw_preview(body),
    )
    return job, model


def _stamp(response: Response, job: Job) -> Response:
    response.headers["X-PeoAI-Request"] = job.id
    response.headers["X-PeoAI-Model"] = job.model
    response.headers["X-PeoAI-Protocol"] = job.protocol
    response.headers["X-PeoAI-Human"] = "1"
    return response


def _sse_response(generator) -> Response:
    response = Response(generator, mimetype="text/event-stream")
    response.headers["Cache-Control"] = "no-cache, no-transform"
    response.headers["X-Accel-Buffering"] = "no"
    return response


def _ndjson_response(generator) -> Response:
    response = Response(generator, mimetype="application/x-ndjson")
    response.headers["Cache-Control"] = "no-cache, no-transform"
    response.headers["X-Accel-Buffering"] = "no"
    return response


def _usage(job: Job) -> Dict[str, int]:
    return usage_for(job.messages, job.reply_text, job.tools, job.reply_tools)


# ---------------------------------------------------------------------------
# OpenAI 兼容
# ---------------------------------------------------------------------------

@bp.get("/v1/models")
def list_models():
    _resolve_key()
    return jsonify(openai.models_payload(_ctx().config.models()))


@bp.get("/v1/models/<path:model_id>")
def get_model(model_id: str):
    _resolve_key()
    model = _ctx().config.model(model_id)
    if not model or not model.get("enabled", True):
        raise not_found("模型不存在：%s" % model_id)
    payload = openai.models_payload([model])["data"][0]
    return jsonify(payload)


@bp.post("/v1/chat/completions")
def chat_completions():
    ctx = _ctx()
    key = _resolve_key()
    body = _json_body()
    parsed = openai.parse_chat(body, ctx.limits())
    job, _model = _prepare(parsed, key, openai.PROTOCOL, body)
    if job.stream:
        return _stamp(_sse_response(openai.chat_stream(job)), job)
    ctx.store.wait(job)
    return _stamp(jsonify(openai.response_payload(job, _usage(job))), job)


@bp.post("/v1/completions")
def completions():
    ctx = _ctx()
    key = _resolve_key()
    body = _json_body()
    parsed = openai.parse_completions(body, ctx.limits())
    job, _model = _prepare(parsed, key, "openai.completions", body)
    if job.stream:
        return _stamp(_sse_response(openai.completions_stream(job)), job)
    ctx.store.wait(job)
    return _stamp(jsonify(openai.completions_payload(job, _usage(job))), job)


@bp.post("/v1/responses")
def responses():
    ctx = _ctx()
    key = _resolve_key()
    body = _json_body()
    parsed = openai.parse_responses(body, ctx.limits())
    job, _model = _prepare(parsed, key, "openai.responses", body)
    if job.stream:
        return _stamp(_sse_response(openai.responses_stream(job)), job)
    ctx.store.wait(job)
    return _stamp(jsonify(openai.responses_object(job, _usage(job))), job)


# ---------------------------------------------------------------------------
# Anthropic
# ---------------------------------------------------------------------------

@bp.post("/v1/messages")
def anthropic_messages():
    ctx = _ctx()
    key = _resolve_key()
    body = _json_body()
    parsed = anthropic.parse_messages(body, ctx.limits())
    job, _model = _prepare(parsed, key, anthropic.PROTOCOL, body)
    if job.stream:
        return _stamp(_sse_response(anthropic.sse_stream(job)), job)
    ctx.store.wait(job)
    return _stamp(jsonify(anthropic.message_object(job, _usage(job))), job)


@bp.post("/v1/messages/count_tokens")
def anthropic_count_tokens():
    _resolve_key()
    body = _json_body()
    return jsonify(anthropic.count_tokens(body))


# ---------------------------------------------------------------------------
# Gemini
# ---------------------------------------------------------------------------

@bp.get("/v1beta/models")
def gemini_models():
    _resolve_key()
    data = []
    for model in _ctx().config.models():
        caps = model.get("capabilities") or {}
        input_modalities = ["text"]
        if caps.get("vision"):
            input_modalities.append("image")
        data.append(
            {
                "name": "models/" + model["id"],
                "displayName": model.get("label") or model["id"],
                "description": model.get("description") or "",
                "inputTokenLimit": model.get("context_window"),
                "outputTokenLimit": model.get("max_output_tokens"),
                "contextWindow": model.get("context_window"),
                "maxOutputTokens": model.get("max_output_tokens"),
                "capabilities": caps,
                "inputModalities": input_modalities,
                "supportedGenerationMethods": ["generateContent", "streamGenerateContent"]
                if caps.get("streaming")
                else ["generateContent"],
            }
        )
    return jsonify({"models": data})


@bp.post("/v1beta/models/<path:model_action>")
def gemini_generate(model_action: str):
    ctx = _ctx()
    if ":" not in model_action:
        raise not_found("路径应为 /v1beta/models/{model}:generateContent")
    model_name, action = model_action.rsplit(":", 1)
    model_name = model_name.split("/")[-1]
    if action not in ("generateContent", "streamGenerateContent"):
        raise not_found("不支持的 Gemini 方法：%s" % action)
    key = _resolve_key()
    body = _json_body()
    body = dict(body)
    body["_stream"] = action == "streamGenerateContent"
    parsed = gemini.parse_generate(body, ctx.limits(), model_hint=model_name)
    job, _model = _prepare(parsed, key, gemini.PROTOCOL, body)
    if job.stream:
        return _stamp(_sse_response(gemini.sse_stream(job)), job)
    ctx.store.wait(job)
    return _stamp(jsonify(gemini.response_payload(job, _usage(job))), job)


# ---------------------------------------------------------------------------
# Ollama
# ---------------------------------------------------------------------------

@bp.post("/api/chat")
def ollama_chat():
    ctx = _ctx()
    key = _resolve_key()
    body = _json_body()
    parsed = ollama.parse_chat(body, ctx.limits())
    job, _model = _prepare(parsed, key, ollama.PROTOCOL, body)
    if job.stream:
        return _stamp(_ndjson_response(ollama.ndjson_stream(job)), job)
    ctx.store.wait(job)
    return _stamp(jsonify(ollama.response_payload(job, _usage(job))), job)


@bp.get("/api/tags")
def ollama_tags():
    _resolve_key()
    return jsonify(ollama.tags_payload(_ctx().config.models()))


@bp.get("/api/version")
def ollama_version():
    from . import __version__

    return jsonify({"version": "0.0.0-peoai-" + __version__})


@bp.post("/api/show")
def ollama_show():
    _resolve_key()
    body = _json_body()
    name = str(body.get("name") or body.get("model") or "")
    model = _ctx().config.model(name)
    if not model:
        raise not_found("模型不存在：%s" % name)
    return jsonify(ollama.show_payload(model))


@bp.get("/api/ps")
def ollama_ps():
    _resolve_key()
    return jsonify({"models": []})
