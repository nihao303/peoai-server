# 协议兼容矩阵

## 总览

| 特性 | OpenAI Chat | OpenAI Completions | OpenAI Responses | Anthropic | Gemini | Ollama |
| --- | :---: | :---: | :---: | :---: | :---: | :---: |
| 非流式 | 是 | 是 | 是 | 是 | 是 | 是 |
| 流式 | SSE | SSE | SSE | 事件流 | SSE | NDJSON |
| 工具调用 | 是 | - | 是 | 是 | 是 | 是 |
| 思考内容 | 是（reasoning_content） | - | 是（output） | 是（thinking） | 是（thought） | 是（thinking） |
| 并行工具调用 | 是 | - | 是 | 是 | 是 | 是 |
| 图片输入 | 是 | - | 是 | 是 | 是 | 是 |
| 图片 URL | 是 | - | 是 | 是 | 是（fileData） | 否（仅 base64） |
| system 消息 | 是 | - | instructions | system | systemInstruction | 是 |
| JSON 模式 | 标记 | - | 标记 | - | responseMimeType | - |
| 多候选 n | 仅 1 | 仅 1 | 仅 1 | - | 仅 1 | - |
| 音频输入 | 拒绝 | - | 拒绝 | 拒绝 | 拒绝 | 拒绝 |
| Embeddings | 501 | - | - | - | - | - |

## 常见差异与处理

### 模型名

响应的 `model` 字段总是**规范化的模型 ID**（例如 `peo-human-1`），而不是客户端请求的原始字符串。若请求了未知模型且开启了 `server.allow_fallback_model`，会回退到默认模型，并在 `meta.warnings` 与操作台顶部提示。

### 思考内容

操作台可以单独发送「思考」消息，各协议的映射：

| 协议 | 非流式 | 流式 |
| --- | --- | --- |
| OpenAI Chat | message.reasoning_content | delta.reasoning_content |
| Anthropic | {"type": "thinking", "thinking": "...", "signature": ""} 内容块 | thinking_delta 事件 |
| Gemini | {"text": "...", "thought": true} part | 同左，逐块 |
| Ollama | message.thinking | 同左，逐行 |

思考内容不会混入 content。Anthropic 的 signature 为空字符串，若客户端要求签名需自行处理；OpenAI Responses 目前不输出思考项。

### 工具调用 ID

- OpenAI 风格：`call_xxx`；
- Anthropic：`toolu_xxx` 形式由操作台生成（`call_xxx`）；
- Gemini：`functionCall.name + args` 不带 ID，回填时使用函数名。

### 停止原因

| 场景 | OpenAI finish_reason | Anthropic stop_reason | Gemini finishReason |
| --- | --- | --- | --- |
| 正常作答 | stop | end_turn | STOP |
| 工具调用 | tool_calls | tool_use | STOP |
| 操作员拒绝 | 错误体 503 | error 事件 | error |
| 等待超时 | 错误体 504 | error 事件 | error |

### Token 计数

真人没有分词器：中日韩字符按 1 token、其他按 4 字符 ≈ 1 token，每条消息与每张图片有固定开销。数值稳定、量级正确，但不适合精确计费。

### OpenAI Responses

实现了核心子集：`input`（字符串或消息数组）、`instructions`、`tools`、`max_output_tokens`、`stream`。以下能力未实现：`previous_response_id`、内置工具、`reasoning` 详细事件、`include`、`background`。客户端收到 `object: "response"` 与 `output` 数组即可正常工作。

### Gemini

- 使用 `alt=sse` 或直接请求 `:streamGenerateContent` 都会得到 SSE；
- `candidateCount` 只支持 1；
- `safetyRatings` 返回空数组；
- `fileData` 只支持 http(s) 链接（转换为远端图片），不支持 `gs://`。

### Ollama

- `stream` 默认 `true`（与官方一致），需要一次性结果请显式传 `false`；
- `/api/tags` 中的模型名为 `<id>:latest`；
- `/api/ps` 返回空列表（没有本地模型加载的概念）；
- `options.num_predict` 会映射为 `max_tokens`。

### 请求体中的未知字段

协议层只保留白名单字段，未知字段不会进入队列，也不会报错（与主流 SDK 的宽容行为一致）。但 `messages`、`tools`、`model` 等核心字段的类型错误会返回 400。

### 流式保活

等待真人作答期间，SSE 每 15 秒发送一行注释（`: keepalive`，Ollama 为换行），不会产生 `data` 帧，客户端解析器通常会自动忽略。

## 建议的客户端设置

| 场景 | 建议 |
| --- | --- |
| IDE / Agent | 关闭自动重试，或把超时设为 10 分钟以上 |
| 批量任务 | 使用非流式，配合并发上限 |
| 演示 | 使用流式，操作员边打边推，体验更接近模型 |
| 移动端 | 非流式 + 较短 `request_ttl_seconds` |
