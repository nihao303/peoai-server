# 更新日志

本项目遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

## [Unreleased]

### 变更

- 依赖更新：Flask >=3.1.3、Waitress >=3.0.2、ruff >=0.17.1；requests 按 Python 版本约束（3.9 使用 <2.34，3.10+ 使用 >=2.34.2）；移除未使用的 flask-cors；
- CI：Python 3.9 固定 ubuntu-22.04，新增 3.13；Actions 升级到 checkout@v7 / setup-python@v7。
- 远端图片改为按需加载（「加载图片」按钮），避免自动请求泄漏操作员 IP；新增 `queue.persist_media` 设置，可选保留历史图片；
- 修复严格 CSP（`img-src blob: https:`）下 `data:` 图片与页面图标被拦截：图标与内联图片统一转为 `blob:` URL；
- 移除 Issue / PR 模板，贡献者直接描述问题与改动。

## [1.0.0] - 2025-01-01

首个公开版本。

### 新增

- 四种协议兼容：OpenAI Chat Completions / Completions / Responses、Anthropic Messages、Gemini generateContent、Ollama Chat 与元信息接口；
- 请求队列与状态机：pending → claimed → answered / rejected / expired / cancelled，支持重启恢复与历史清理；
- 流式输出：OpenAI SSE、Anthropic 事件流、Gemini alt=sse、Ollama NDJSON，含 15 秒保活；
- 工具调用：解析三家工具定义，操作台按 JSON Schema 生成表单并产出标准 tool_calls；
- 多模态：data URL、base64、inlineData、fileData 与 Ollama images 的解析与安全校验，控制台自动展示图片；
- 模型注册表：自定义 ID、别名、上下文与输出上限，vision / tools / streaming / reasoning / json_mode / code 能力开关，能力直接约束请求；
- API Key：SHA-256 摘要存储、rpm 限流、模型白名单、启停与删除；
- 操作台：Miuix 风格单文件前端，深浅主题，队列、对话、图片、工具、原始请求四个视图，SSE 实时更新；
- 管理功能：模型增删改、密钥管理、安全参数、密码修改、会话吊销、管理员令牌轮换、审计日志；
- 安全：登录失败锁定、无 Cookie 会话、请求体与图片上限、CSP 与安全响应头、SSRF 规避、审计记录；
- 部署：systemd 单元、Nginx 反代片段（含 SSE 配置）、命令行管理工具、配置示例；
- 文档：API、部署、架构、安全模型、协议差异、GitHub 仓库设置指南；
- 测试：46 个端到端与单元测试，覆盖四协议、流式、工具、多模态、限流、锁定、体积限制、持久化。

### 修复

- 移除 SSE/NDJSON 响应中的 hop-by-hop `Connection` 头：waitress 会以 AssertionError 拒绝该头，导致流式接口（/api/events、/v1/chat/completions stream 等）返回 500 且缺少 CORS 头；
- 修复「安全与限额」保存后被还原：开关改为读取复选框实时状态；
- 修复创建 API Key 后明文提示被列表刷新清空：现在会保留展示，直到手动关闭；
- 新增自定义 API Key：创建时可自己指定 16~128 位的 Key，服务端仍只保存 SHA-256 摘要；
- 操作台队列改为按会话聚合：一个会话展开后列出全部请求，点任意一条即可打开该请求的作答窗口，详情页支持会话内切换；
- 作答区新增「思考内容」与「发送思考片段」：按协议输出 reasoning_content / thinking / thought / thinking，支持流式；详情页单独展示思考过程；
- 补充真实 waitress 下的流式回归测试，以及 `/healthz` 的 CORS 支持。

### 已知限制

- 人工作答的 token 数为估算值；
- OpenAI Responses 仅实现核心子集；
- 单实例内存限流与会话，不支持横向扩展；
- 不支持音频与向量接口。

[1.0.0]: https://github.com/nihao303/peoai-server/releases/tag/v1.0.0
