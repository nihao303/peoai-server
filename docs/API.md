# API 参考

所有接口都以服务的根地址为前缀，例如 `http://127.0.0.1:5007` 或 `https://your-domain/peoai`。

## 认证

| 方式 | 示例 | 适用 |
| --- | --- | --- |
| Bearer | `Authorization: Bearer pk_xxx` | OpenAI、Ollama、操作台 |
| x-api-key | `x-api-key: pk_xxx` | Anthropic SDK |
| x-goog-api-key | `x-goog-api-key: pk_xxx` | Gemini 工具链 |
| 查询参数 | `?key=pk_xxx` | 不支持自定义头的简单客户端 |

- API Key 以 `pk_` 开头，控制台「设置 → API Key」或管理接口创建，明文只返回一次。
- `security.require_api_key = false` 时可以无密钥调用（仅建议内网使用）。
- 操作台接口使用 `po_` 开头的会话令牌（登录后获得），管理员接口也接受 `adm_` 开头的新管理令牌。

## 跨域（CORS）

默认 `security.allowed_origins = ["*"]`，任何前端域名都可以直接调用（包括部署在 `https://frontend.example.com` 的页面）。响应头包含：

- `Access-Control-Allow-Origin: *`（配置为白名单时回显具体 Origin）
- `Access-Control-Allow-Methods: GET, POST, PUT, PATCH, DELETE, OPTIONS`
- `Access-Control-Allow-Headers`：Authorization / Content-Type / X-Api-Key / X-Goog-Api-Key / X-Admin-Token 等
- `Access-Control-Expose-Headers`：`X-PeoAI-*` / `Retry-After`
- `Access-Control-Max-Age: 600`

预检请求（OPTIONS）直接返回 204，错误响应也带 CORS 头。若把 `allowed_origins` 收紧为具体域名，请包含前端实际使用的每个 origin（例如同时包含 `https://frontend.example.com` 与 `http://frontend.example.com`）。

> 注意：前端页面是 HTTPS、后端只提供 HTTP 时，浏览器会按「混合内容」拦截。此时请给后端配 HTTPS，或在前端域名的 Nginx 上反代 `/peoai/`，让请求变成同源。

## 错误格式

| 协议 | 错误体 |
| --- | --- |
| OpenAI | `{"error": {"message", "type", "code", "param"}}` |
| Anthropic | `{"type": "error", "error": {"type", "message"}}` |
| Gemini | `{"error": {"code", "message", "status"}}` |
| Ollama | `{"error": "..."}` |
| 操作台 | `{"ok": false, "error": {...}}` |

常见状态码：

| 状态码 | 含义 | 典型 `code` |
| --- | --- | --- |
| 400 | 参数或能力不匹配 | `invalid_request`、`unsupported_parameter` |
| 401 | 缺少/无效密钥 | `invalid_api_key`、`authentication_error` |
| 403 | 密钥无权使用该模型 | `permission_denied` |
| 404 | 模型或请求不存在 | `not_found` |
| 413 | 请求体过大 | `payload_too_large` |
| 429 | 触发限流 / 队列满 | `rate_limit_exceeded`、`queue_full` |
| 503 | 操作员拒绝或不可用 | `operator_unavailable` |
| 504 | 等待超时 | `request_timeout` |

## OpenAI：Chat Completions

### 请求

~~~http
POST /v1/chat/completions
Authorization: Bearer pk_xxx
Content-Type: application/json
~~~

~~~json
{
  "model": "peo-human-1",
  "messages": [
    {"role": "system", "content": "你是运维助手"},
    {"role": "user", "content": [
      {"type": "text", "text": "看下这张图"},
      {"type": "image_url", "image_url": {"url": "data:image/png;base64,..."}}
    ]}
  ],
  "tools": [{
    "type": "function",
    "function": {
      "name": "search_tickets",
      "description": "检索工单",
      "parameters": {
        "type": "object",
        "properties": {"keyword": {"type": "string"}},
        "required": ["keyword"]
      }
    }
  }],
  "tool_choice": "auto",
  "temperature": 0.3,
  "max_tokens": 1024,
  "stream": false
}
~~~

支持的字段：`messages`（字符串或多段数组）、`tools`、`tool_choice`、`temperature`、`top_p`、`max_tokens` / `max_completion_tokens`、`stop`、`presence_penalty`、`frequency_penalty`、`seed`、`response_format`、`reasoning_effort`、`stream`、`stream_options.include_usage`、`user`、`n`（只支持 1）、`logit_bias`、`parallel_tool_calls`。

### 非流式响应

~~~json
{
  "id": "chatcmpl-5b80023bcf400f4a4c",
  "object": "chat.completion",
  "created": 1792250159,
  "model": "peo-human-1",
  "system_fingerprint": "peoai-human",
  "choices": [{
    "index": 0,
    "message": {"role": "assistant", "content": "已定位到配置回滚点。"},
    "logprobs": null,
    "finish_reason": "stop"
  }],
  "usage": {"prompt_tokens": 128, "completion_tokens": 42, "total_tokens": 170}
}
~~~

工具调用时：

~~~json
{
  "choices": [{
    "index": 0,
    "message": {
      "role": "assistant",
      "content": null,
      "tool_calls": [{
        "id": "call_abc",
        "type": "function",
        "function": {"name": "search_tickets", "arguments": "{\"keyword\":\"网关超时\"}"}
      }]
    },
    "finish_reason": "tool_calls"
  }]
}
~~~

### 流式响应

`Content-Type: text/event-stream`，每帧 `data: {...}`，以 `data: [DONE]` 结束；等待期间每 15 秒发送一行 `: keepalive` 注释。

~~~text
data: {"id":"chatcmpl-...","object":"chat.completion.chunk","choices":[{"index":0,"delta":{"role":"assistant","content":""},"finish_reason":null}]}

data: {"id":"chatcmpl-...","object":"chat.completion.chunk","choices":[{"index":0,"delta":{"content":"你好"},"finish_reason":null}]}

data: {"id":"chatcmpl-...","object":"chat.completion.chunk","choices":[{"index":0,"delta":{},"finish_reason":"stop"}]}

data: [DONE]
~~~

开启 `stream_options.include_usage` 时，在结束帧之后追加一个 `choices: []` 且带 `usage` 的帧。

如果操作员发送了思考内容，流里会先出现 `delta.reasoning_content` 帧，再出现 `delta.content` 帧；非流式响应则在 message 里带 `reasoning_content` 字段。

## OpenAI：Completions

~~~json
POST /v1/completions
{"model": "peo-human-1", "prompt": "写一句欢迎语", "max_tokens": 64, "stream": false}
~~~

响应为 `object: "text_completion"`，`choices[0].text` 为作答内容。`prompt` 会被包装成一条 user 消息。

## OpenAI：Responses

~~~json
POST /v1/responses
{
  "model": "peo-human-1",
  "instructions": "回答简短",
  "input": [{"role": "user", "content": [{"type": "input_text", "text": "你好"}]}],
  "stream": false
}
~~~

非流式返回 `object: "response"`、`output`（message 或 function_call）与 `usage.input_tokens / output_tokens`。流式返回简化事件：`response.created`、`response.output_text.delta`、`response.output_text.done`、`response.output_item.done`、`response.completed`（失败时 `response.failed`）。

## OpenAI：模型

~~~bash
GET /v1/models
GET /v1/models/peo-human-1
~~~

~~~json
{
  "object": "list",
  "data": [{
    "id": "peo-human-1",
    "object": "model",
    "created": 1700000000,
    "owned_by": "peoai",
    "label": "PeoAI Human 1",
    "capabilities": {"vision": true, "tools": true, "streaming": true, "reasoning": true, "json_mode": true, "code": true},
    "context_window": 128000,
    "context_length": 128000,
    "contextWindow": 128000,
    "max_output_tokens": 8192,
    "max_tokens": 8192,
    "maxOutputTokens": 8192,
    "maxTokens": 8192,
    "input_modalities": ["text", "image"],
    "inputModalities": ["text", "image"],
    "x_peoai": {
      "label": "PeoAI Human 1",
      "capabilities": {"vision": true, "tools": true, "streaming": true, "reasoning": true, "json_mode": true, "code": true},
      "context_window": 128000,
      "max_output_tokens": 8192,
      "input_modalities": ["text", "image"]
    }
  }]
}
~~~

顶层同时给出多种常见拼写，是为了兼容只读取标准字段的 Agent 客户端（DSH、OpenCode 等）；`x_peoai` 保留完整扩展。能力字段按模型独立计算：`peo-human-fast` 的 `input_modalities` 只有 `["text"]`，`peo-human-vision` 为 `["text", "image"]`。

## Anthropic：Messages

~~~http
POST /v1/messages
x-api-key: pk_xxx
anthropic-version: 2023-06-01
~~~

~~~json
{
  "model": "peo-human-1",
  "max_tokens": 1024,
  "system": "你是真人客服",
  "messages": [
    {"role": "user", "content": [
      {"type": "text", "text": "看下这张图"},
      {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": "..."}}
    ]}
  ],
  "tools": [{"name": "search", "description": "检索", "input_schema": {"type": "object", "properties": {"q": {"type": "string"}}}}]
}
~~~

~~~json
{
  "id": "msg_5b80023bcf400f4a4c",
  "type": "message",
  "role": "assistant",
  "model": "peo-human-1",
  "content": [{"type": "text", "text": "我看过了，是发布配置的问题。"}],
  "stop_reason": "end_turn",
  "stop_sequence": null,
  "usage": {"input_tokens": 120, "output_tokens": 30}
}
~~~

流式事件顺序：`message_start` → `content_block_start` → 若干 `content_block_delta`（`text_delta`）→ `content_block_stop` → 工具调用时追加 `tool_use` 块与 `input_json_delta` → `message_delta`（`stop_reason` 与 `usage.output_tokens`）→ `message_stop`。

`POST /v1/messages/count_tokens` 返回 `{"input_tokens": 123}`（估算）。

## Gemini：generateContent

~~~http
POST /v1beta/models/peo-human-1:generateContent
x-goog-api-key: pk_xxx
~~~

~~~json
{
  "systemInstruction": {"parts": [{"text": "回答简短"}]},
  "contents": [{"role": "user", "parts": [
    {"text": "看下这张图"},
    {"inlineData": {"mimeType": "image/png", "data": "..."}}
  ]}],
  "tools": [{"functionDeclarations": [{"name": "search", "description": "检索", "parameters": {"type": "object", "properties": {"q": {"type": "string"}}}}]}],
  "generationConfig": {"temperature": 0.3, "maxOutputTokens": 512, "candidateCount": 1}
}
~~~

~~~json
{
  "candidates": [{
    "content": {"parts": [{"text": "是发布配置导致的上游超时。"}], "role": "model"},
    "finishReason": "STOP",
    "index": 0
  }],
  "usageMetadata": {"promptTokenCount": 120, "candidatesTokenCount": 30, "totalTokenCount": 150},
  "modelVersion": "peo-human-1"
}
~~~

流式使用 `POST /v1beta/models/{model}:streamGenerateContent`（建议加 `?alt=sse`），帧为 `data: {...}`。也支持 `GET /v1beta/models` 列出模型。

## Ollama

~~~bash
POST /api/chat
GET /api/tags
GET /api/version
POST /api/show
GET /api/ps
~~~

~~~json
{
  "model": "peo-human-mini",
  "stream": true,
  "messages": [{"role": "user", "content": "你好", "images": ["<base64>"]}],
  "options": {"temperature": 0.6, "num_predict": 256}
}
~~~

流式响应为 NDJSON，每行一个对象：

~~~text
{"model":"peo-human-mini","created_at":"2025-01-01T00:00:00Z","message":{"role":"assistant","content":"你"},"done":false}
{"model":"peo-human-mini","created_at":"2025-01-01T00:00:01Z","message":{"role":"assistant","content":"好"},"done":false}
{"model":"peo-human-mini","created_at":"2025-01-01T00:00:02Z","message":{"role":"assistant","content":"你好"},"done":true,"done_reason":"stop","prompt_eval_count":8,"eval_count":2}
~~~

注意 `stream` 默认是 `true`，与 Ollama 官方一致；要一次性结果请显式传 `false`。

## 操作台 API

除登录与 `/api/operator/bootstrap` 外，都需要 `Authorization: Bearer po_xxx`。

会话分组规则：优先使用调用方传入的 `user`（OpenAI/Anthropic metadata）或 `X-PeoAI-Conversation` / `X-Conversation-Id` 请求头；都没有时用「system + 第一条 user 消息」的指纹，保证多轮请求能聚到同一会话。

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/operator/bootstrap` | 公开信息：名称、版本、模型列表、队列概况 |
| POST | `/api/operator/login` | `{"password": "..."}` → 会话令牌与过期时间 |
| POST | `/api/operator/logout` | 吊销当前会话 |
| GET | `/api/operator/me` | 当前操作员信息 |
| GET | `/api/queue?status=pending,claimed&limit=60&q=` | 队列摘要；每条请求带 `conversation_id` / `conversation_title`，前端据此聚合会话 |
| GET | `/api/queue/{id}` | 请求详情（含消息、图片、工具、参数、原始请求） |
| POST | `/api/queue/{id}/claim` | 认领 |
| POST | `/api/queue/{id}/release` | 退回队列 |
| POST | `/api/queue/{id}/delta` | `{"text": "...", "kind": "text"}` 推流片段；`kind` 可为 `text` 或 `reasoning` |
| POST | `/api/queue/{id}/reply` | `{"text": "...", "reasoning": "...", "tool_calls": [...], "finish_reason": "stop"}` |
| POST | `/api/queue/{id}/reject` | `{"reason": "..."}` |
| POST | `/api/queue/{id}/typing` | `{"typing": true}` |
| GET | `/api/events` | SSE：队列快照、状态变化、增量 |
| GET | `/api/stats` | 队列与会话统计 |
| GET | `/api/models` | 完整模型配置 |
| GET | `/api/config` | 脱敏后的配置 |

`/api/queue/{id}` 返回的 `job.messages[].images[]` 形如：

~~~json
{
  "kind": "inline",
  "mime": "image/png",
  "bytes": 2841,
  "sha256": "9f2c...",
  "data_url": "data:image/png;base64,..."
}
~~~

远端图片为 `{"kind": "remote", "url": "https://..."}`，不会在服务端下载；前端默认只显示链接和「加载图片」按钮。

历史请求默认不保留 base64（`queue.persist_media = false`），此时 `data_url` 会省略，只保留 `sha256` 与大小；如果希望重启后仍能查看历史图片，在设置页开启「持久化图片数据」，或在 `config.json` 设置 `queue.persist_media = true`。

## 管理 API

需要操作员会话，或 `X-Admin-Token: adm_xxx` / `Authorization: Bearer adm_xxx`。

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/admin/config` | 配置（含模型与密钥前缀，不含哈希） |
| PUT | `/api/admin/config` | 局部更新（白名单字段，越界自动裁剪） |
| POST | `/api/admin/models` | 新增或覆盖模型 |
| DELETE | `/api/admin/models/{id}` | 删除模型（至少保留一个） |
| POST | `/api/admin/keys` | 创建 API Key，返回一次明文；`key` 字段可选，用于自定义 |
| DELETE | `/api/admin/keys/{prefix}` | 删除 |
| POST | `/api/admin/keys/{prefix}/toggle` | 启用/停用 |
| POST | `/api/admin/password` | `{"current": "...", "password": "..."}` |
| POST | `/api/admin/admin-token` | 轮换管理令牌 |
| GET | `/api/admin/audit?limit=100` | 审计记录 |
| POST | `/api/admin/sessions/revoke` | 吊销全部会话 |

创建 API Key（`key` 省略时随机生成；自定义值需 16~128 位，且前 10 位不能与现有 Key 冲突）：

~~~json
{"name": "agent-prod", "key": "pk_my_fixed_key_0001", "rpm": 60, "models": ["peo-human-code"]}
~~~

`PUT /api/admin/config` 示例：

~~~json
{
  "security": {"max_images": 6, "allow_remote_images": true},
  "queue": {"request_ttl_seconds": 900},
  "server": {"default_model": "peo-human-vision"}
}
~~~

## 健康检查

~~~bash
GET /healthz
GET /api/health
~~~

~~~json
{"ok": true, "name": "PeoAI", "version": "1.0.0", "uptime_seconds": 42.5, "queue": {"pending": 0, "claimed": 0}, "models": 5}
~~~

## 限制一览

| 配置项 | 默认值 | 影响 |
| --- | --- | --- |
| `security.max_body_bytes` | 8 MiB | 请求体上限（Nginx `client_max_body_size` 需不小于它） |
| `security.max_messages` | 200 | 单请求消息条数 |
| `security.max_message_chars` | 120000 | 单条消息字符数 |
| `security.max_images` | 4 | 单请求图片数 |
| `security.max_image_bytes` | 2 MiB | 单图大小 |
| `security.max_reply_chars` | 200000 | 作答长度 |
| `queue.max_pending` | 100 | 待处理队列容量 |
| `queue.request_ttl_seconds` | 600 | 客户端最长等待 |
| `queue.max_concurrent_per_key` | 3 | 单 Key 并发 |
| `queue.history_limit` | 300 | 保留的历史请求文件数 |
