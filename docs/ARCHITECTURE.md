# 架构说明

## 分层

| 层 | 文件 | 职责 |
| --- | --- | --- |
| 入口 | peoai_server.py | 解析参数、启动 waitress / Flask、打印接入地址 |
| 应用 | peoai/app.py | 上下文装配、安全响应头、错误处理、控制台路由 |
| 协议 | peoai/protocols/*.py | 把各家请求归一化为 Normalized，把作答渲染成各家响应 |
| 路由 | api_v1.py / api_operator.py / api_admin.py | 鉴权、限流、参数校验、入队、流式包装 |
| 领域 | store.py | Job 状态机、队列、订阅广播、落盘 |
| 支撑 | config.py / auth.py / images.py / tokens.py / ratelimit.py / audit.py | 配置、会话、图片、估算、限流、审计 |

## 一次调用的完整生命周期

1. 客户端 POST /v1/chat/completions；
2. 应用层 before_request 检查体积与 OPTIONS；
3. 路由层校验 API Key 与 rpm 限额；
4. 协议模块解析 JSON，得到 Normalized(model, messages, tools, params, stream)；
5. _prepare 解析模型、校验能力（vision / tools / streaming）、裁剪 max_tokens、写入 meta.warnings；
6. JobStore.create 检查队列容量与单 Key 并发，写入 data/requests/<id>.json，广播队列事件；
7. 非流式：store.wait 阻塞在 Condition 上，直到终态或超时（超时把 Job 标记 expired 并抛 504）；
   流式：返回生成器，客户端进入 SSE 读取；
8. 操作台通过 GET /api/events 收到队列快照，打开请求后调用 delta / reply；
9. reply 写入终态、唤醒等待线程、推给所有流式订阅者、落盘、广播；
10. 协议模块把 reply_text + reply_tools + usage 渲染成响应，附加 X-PeoAI-* 头。

## 状态机

~~~text
            claim / delta / reply
pending ─────────────────────────► claimed ──reply──► answered
   │                                  │
   │ reject                           ├─reject──► rejected
   ├──────────────────────────────────┤
   │ 超过 request_ttl_seconds          └─cancel──► cancelled
   └────────────────────────────► expired
~~~

- answered 之后不可再修改；重复提交返回 400；
- delta 可把 pending 隐式提升为 claimed（操作员直接开打的情况）；
- 服务重启时，未过期的 pending/claimed 会被恢复为 pending，并在 meta.restored 标记。

## 并发模型

- Flask/waitress 多线程，每请求一个线程；
- JobStore._lock 保护索引与计数，Job._lock 保护单个请求状态；
- Job._cv（Condition）用于非流式等待，所有 notify 都先获取其锁；
- 流式读取以 job.deltas 为唯一事实源，事件队列只负责唤醒，因此中途重连不会丢文本；
- 操作台事件流是多播队列，慢消费者丢最旧事件，不阻塞生产者。

## 流式实现细节

~~~text
操作员 delta("你好") ──► job.deltas += [{text:"你好"}] ──► 广播 {"type":"delta"}
                                          │
SSE 生成器循环：                          ▼
  while True:
      发送 sent..len(deltas) 之间的新文本
      若终态：发送结束帧与 [DONE]
      等待事件队列（15s 超时则发 keepalive 注释）
~~~

工具调用在结束时一次性发出：

- OpenAI：delta.tool_calls[index]
- Anthropic：tool_use 内容块 + input_json_delta
- Gemini：functionCall parts
- Ollama：message.tool_calls

## 持久化

- 目录：data/requests/<job_id>.json，原子写入（临时文件 + os.replace，失败重试 3 次）；
- 每次创建、认领、提交都会写盘；增量写入每 2 秒节流一次；
- 默认不持久化图片 base64（queue.persist_media = false），只保留元信息与 sha256；开启后保留完整 data URL，重启仍可查看；
- 启动时按 mtime 载入最近 history_limit 个文件，过期未完成的请求标记 expired；
- 文件超过上限时删除最旧的，内存索引也做同步裁剪。

## 扩展一个新协议

1. 在 peoai/protocols/ 新建模块，实现：
   - parse_xxx(body, limits) -> Normalized
   - 非流式渲染函数（返回 dict）
   - 流式生成器（yield SSE/NDJSON 字符串，内部订阅 job.subscribe()）
2. 复用 common.py 的 flatten_parts、normalize_tools、enforce_limits、sse；
3. 在 api_v1.py 增加路由，调用 _prepare 后选择流式或非流式；
4. 在 app.py 的 family_for_path 增加错误体映射；
5. 补测试（解析 + 非流式 + 流式）。

## 测试策略

- tests/test_api.py 使用 werkzeug.serving.make_server 起真实线程服务，用 requests 发起真实 HTTP；
- 每个阻塞请求在后台线程发起，主线程通过操作台 API 作答，验证响应与落盘；
- 覆盖四种协议的流式与非流式、工具调用、多模态、拒绝、回退、限流、锁定、体积限制、模型白名单；
- ui/ 变更用 scripts/build_ui.py --check 保证产物与源码一致。
