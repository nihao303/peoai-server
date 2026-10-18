# 安全模型

## 资产

| 资产 | 位置 | 影响 |
| --- | --- | --- |
| 操作员密码哈希 | config.json | 被离线爆破可接管操作台 |
| 管理员令牌哈希 | config.json | 可改模型、建密钥 |
| API Key 哈希 | config.json | 泄漏前缀无害，明文仅创建时出现 |
| 请求正文与图片 | data/requests/ | 可能含用户隐私、凭证、内部数据 |
| 审计日志 | data/audit.log | 操作者、时间、IP 元数据 |
| 会话令牌 | 内存 | 有效期内可操作队列 |

## 威胁模型

| 威胁 | 缓解 | 残余风险 |
| --- | --- | --- |
| 未授权调用 API | 默认强制 API Key，SHA-256 摘要存储，恒定时间比较 | 密钥被客户端日志记录 |
| 在线爆破操作员密码 | 按 IP 的失败计数 + 锁定（默认 6 次 / 5 分钟） | 分布式 IP 轮换爆破；建议使用强密码 + 反代层限流 |
| 会话被窃取 | 随机 256 位令牌、可吊销、默认 12 小时过期、无 Cookie | 浏览器 localStorage 可被同源 XSS 读取（本项目无 innerHTML） |
| CSRF | 不使用 Cookie 认证，全部走 Authorization 头 | 若你自行改造为 Cookie，需补 CSRF 令牌 |
| XSS（请求内容注入页面） | 前端全部 textContent / DOM 构建；CSP；无字符串拼 HTML | 操作员浏览器扩展风险 |
| SSRF | 服务端不抓取任何外部 URL；远端图片只做格式校验 | 若开启「浏览器加载远端图片」，操作员 IP 会暴露给图片服务器 |
| 恶意图片（炸弹/伪装） | MIME 白名单 + 魔数校验 + 单图/总量上限 + base64 长度预检 | 超大解压炸弹（本项目不解析像素数据） |
| 请求体撑爆内存 | Flask MAX_CONTENT_LENGTH 硬上限 + 每次请求检查 max_body_bytes | 并发大请求仍占内存，可用 Nginx client_max_body_size 兜底 |
| 队列耗尽导致拒绝服务 | max_pending、单 Key 并发、请求 TTL、历史清理 | 多 Key 轮换仍可能占满队列 |
| 日志泄漏敏感信息 | 日志不写请求正文；审计只写动作与元数据 | 请求正文仍会落盘（见数据保留） |
| 依赖漏洞 | 最小依赖，Dependabot 提醒 | 需及时升级 |

## 已实现的控制项

- 认证：API Key（多种头）、操作员会话、管理员令牌，三条独立通道；
- 授权：Key 的模型白名单、单 Key rpm、单 Key 并发；
- 输入校验：消息数量与长度、工具数量与名字长度、参数范围（temperature/n）、图片数量与大小；
- 输出编码：SSE/JSON 序列化，前端 DOM 构建；
- 响应头：nosniff、Referrer-Policy、X-Frame-Options、Permissions-Policy、CSP、可选 HSTS；
- 资源限制：请求体、队列、线程数、历史文件数、日志滚动；
- 审计：登录成败、密钥增删改、模型变更、密码与令牌轮换、会话吊销；
- 加固：systemd 单元包含 NoNewPrivileges / PrivateTmp / ProtectSystem / ProtectHome。

## 数据保留与隐私

- 请求正文默认落盘到 data/requests/，保留最近 queue.history_limit 份（默认 300）；
- 图片默认不落盘 base64，只留 sha256 与大小；
- data/ 建议 0700、文件 0600（服务启动时会尝试设置目录权限）；
- 若涉及个人数据：配置较短的历史保留、定期清理、必要时对磁盘加密；
- 真人在作答时能看到完整上下文，请在使用条款中明确告知。

## 上线前检查清单

- [ ] 修改默认操作员密码，删除 data/bootstrap.txt
- [ ] API Key 逐个确认 rpm 与模型白名单
- [ ] security.require_api_key = true
- [ ] security.allowed_origins 收敛到实际域名（或保留 * 但确保只有自己的前端在用）
- [ ] queue.max_pending 与 PEOAI_THREADS 匹配服务器规格
- [ ] Nginx 关闭 proxy_buffering，client_max_body_size 与 max_body_bytes 对齐
- [ ] HTTPS 已启用，安全头未被子配置覆盖
- [ ] 日志与数据目录权限正确，已纳入备份
- [ ] 私有漏洞报告已开启，SECURITY.md 中的联系方式有效

## 事件响应

1. **怀疑密钥泄漏**：控制台停用/删除对应 Key，或用 scripts/peoai_admin.py revoke-key；
2. **怀疑会话泄漏**：设置 → 操作员 → 吊销所有会话；
3. **怀疑管理令牌泄漏**：轮换管理员令牌，更新脚本与 CI；
4. **怀疑密码泄漏**：修改密码（会吊销全部会话），检查审计日志中的异常登录；
5. **数据泄漏**：保留现场，评估 data/requests/ 的保留窗口，按所在地区法规通知。

## 已知局限

- 会话存储在内存在，重启即失效（这是有意的安全取舍）；
- 不做内容审核与敏感词过滤，需要时在外层网关追加；
- 单实例限流，多实例部署需要 Redis 等外部计数；
- 人工作答的合规、劳动与隐私义务由部署者承担。
