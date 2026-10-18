<div align="center">

# PeoAI Server

**把真人接入任何 AI API**

一个 OpenAI / Anthropic / Gemini / Ollama 四协议兼容的「人类即服务」桥接服务

[![license](https://img.shields.io/badge/license-MIT-2ea44f)](LICENSE)
[![python](https://img.shields.io/badge/python-3.9%2B-3776AB)](https://www.python.org/)
[![protocols](https://img.shields.io/badge/protocols-OpenAI%20%7C%20Anthropic%20%7C%20Gemini%20%7C%20Ollama-0d84ff)](#协议兼容)
[![deps](https://img.shields.io/badge/dependencies-Flask%20%2B%20Waitress-000000)](#安装)

[**简体中文**](README.md) | [English](README.en.md)

</div>

客户端以为自己在调用模型；实际上，请求会出现在一个简洁的操作台里，由一位真人阅读上下文、查看图片、解析工具，然后给出回答。

> 适合：模型对照评测、人工标注与打分、Agent 兜底、教学演示、内网审批流，以及任何「这件事需要一个人来判断」的地方。

---

## 目录

- [它解决什么问题](#它解决什么问题)
- [特性](#特性)
- [架构](#架构)
- [快速开始](#快速开始)
- [协议兼容](#协议兼容)
- [模型与能力配置](#模型与能力配置)
- [API Key 与限额](#api-key-与限额)
- [操作台](#操作台)
- [安全设计](#安全设计)
- [部署](#部署)
- [配置参考](#配置参考)
- [目录结构](#目录结构)
- [开源与仓库设置](#开源与仓库设置)
- [常见问题](#常见问题)
- [开发与测试](#开发与测试)

## 它解决什么问题

很多系统需要「一个能理解上下文、能看图、会做判断」的环节，但真正的模型往往不能直接用：

- 需要**人类标注**或**专家复核**，却又要让现有 Agent、IDE 插件、SDK 以为自己在调用模型；
- 需要一个**价格与延迟可控的兜底**：模型答不好时，交给真人；
- 需要**可审计**的人工作答记录：谁、什么时候、看了什么、答了什么；
- 需要一个**统一的接入层**：同一批「人类响应」，同时能被 OpenAI、Anthropic、Gemini、Ollama 四种客户端调用。

PeoAI Server 把「人」包装成一个标准 API：请求进队列，你在控制台作答，客户端按它熟悉的协议拿到结果。

## 特性

| 能力 | 说明 |
| --- | --- |
| 四协议兼容 | OpenAI Chat Completions / Completions / Responses，Anthropic Messages，Gemini generateContent，Ollama Chat |
| 流式输出 | OpenAI SSE、Anthropic 事件流、Gemini alt=sse、Ollama NDJSON；操作员可边打字边推送 |
| 工具调用 | 解析 OpenAI / Anthropic / Gemini 的工具定义，操作台按 JSON Schema 生成表单，产出标准 tool_calls |
| 多模态 | 自动解析 data URL 与各家图片字段，校验魔数与大小，控制台直接展示图片并支持大图预览 |
| 模型注册表 | 自定义模型 ID、别名、上下文、输出上限，以及 vision / tools / streaming / reasoning / json_mode 等能力开关 |
| 能力即约束 | 未开启图片的模型拒绝图片；未开启工具的模型拒绝 tools；请求阶段直接返回 400 |
| API Key 管理 | 每个 Key 独立设置每分钟额度、可用模型；服务端只保存 SHA-256 摘要 |
| 限流与队列 | 单 Key 并发上限、队列容量、等待超时、过期清理、重启恢复 |
| 安全默认值 | 默认强制 API Key、请求体与图片大小限制、登录失败锁定、无 Cookie 会话、无 SSRF |
| 审计 | 登录、密钥、模型、安全设置的变更全部落审计日志，不记录请求正文 |
| 前端 | 单文件控制台，Miuix 风格，深浅主题，零外部依赖，所有图标为手绘内联 SVG |
| 会话聚合 | 队列按 conversation 分组，一个会话展开后列出全部请求，可任选一条打开作答窗口；支持 `user` 字段或 `X-PeoAI-Conversation` 显式指定会话 |
| 思考消息 | 作答时可单独发送「思考」内容：OpenAI `reasoning_content`、Anthropic `thinking` 块、Gemini `thought`、Ollama `thinking`，支持思考片段流式推送 |

## 架构

~~~text
                   ┌────────────────────────────────────────────┐
   OpenAI SDK ────► │  /v1/chat/completions                      │
   Anthropic SDK ─► │  /v1/messages                              │  协议适配层
   Gemini 调用 ───► │  /v1beta/models/{model}:generateContent    │  protocols/
   Ollama CLI ────► │  /api/chat                                 │
                   └───────────────┬────────────────────────────┘
                                   │ 归一化：messages / tools / params / images
                                   ▼
                   ┌────────────────────────────────────────────┐
                   │  请求队列 JobStore                          │
                   │  pending → claimed → answered / rejected   │
                   │  落盘 data/requests/*.json，重启可恢复      │
                   └───────────────┬────────────────────────────┘
                     SSE 推送       │            等待终态（长轮询）
                                   ▼
                   ┌────────────────────────────────────────────┐
                   │  操作台（static/peoai.html）                │
                   │  队列 · 对话 · 图片 · 工具表单 · 流式作答    │
                   └────────────────────────────────────────────┘
~~~

## 快速开始

### 安装

~~~bash
git clone https://github.com/nihao303/peoai-server.git
cd peoai-server

python3 -m venv venv
./venv/bin/pip install -r requirements.txt
~~~

### 启动

~~~bash
PEOAI_HOME=. ./venv/bin/python peoai_server.py --port 5007
~~~

首次启动会自动生成：

- 操作员密码
- 管理员令牌
- 默认 API Key

并写入 `data/bootstrap.txt`（权限 0600），同时打印在日志里。**登录后请立即修改密码并删除该文件。**

### 登录

打开 <http://127.0.0.1:5007/>，输入 `data/bootstrap.txt` 里的操作员密码。

### 第一次调用

~~~bash
export PEOAI_BASE=http://127.0.0.1:5007
export PEOAI_KEY=pk_xxxxxxxxxxxxxxxx   # data/bootstrap.txt 里的 api key

curl -sS "$PEOAI_BASE/v1/chat/completions" \
  -H "Authorization: Bearer $PEOAI_KEY" \
  -H "Content-Type: application/json" \
  -d '{"model":"peo-human-1","messages":[{"role":"user","content":"你好，人类。"}]}'
~~~

命令会挂起（默认最长 600 秒）：请求出现在控制台队列里，你作答后客户端立刻收到标准响应：

~~~json
{
  "id": "chatcmpl-5b80023bcf400f4a4c",
  "object": "chat.completion",
  "created": 1792250159,
  "model": "peo-human-1",
  "choices": [{
    "index": 0,
    "message": {"role": "assistant", "content": "你好，我是真人。"},
    "finish_reason": "stop"
  }],
  "usage": {"prompt_tokens": 6, "completion_tokens": 8, "total_tokens": 14}
}
~~~

更多客户端示例见 [examples/](examples/) 与 [docs/API.md](docs/API.md)。

## 协议兼容

| 协议 | 端点 | 流式 | 工具 | 图片 | 备注 |
| --- | --- | :---: | :---: | :---: | --- |
| OpenAI Chat Completions | POST /v1/chat/completions | SSE | 是 | 是 | 主力协议 |
| OpenAI Completions | POST /v1/completions | SSE | - | - | 自动包装成对话 |
| OpenAI Responses | POST /v1/responses | SSE | 是 | 是 | 核心子集，见 [PROTOCOLS](docs/PROTOCOLS.md) |
| OpenAI Models | GET /v1/models | - | - | - | 含 x_peoai 能力字段 |
| Anthropic Messages | POST /v1/messages | 事件流 | 是 | 是 | message_start 等完整事件 |
| Anthropic Count Tokens | POST /v1/messages/count_tokens | - | - | - | 估算值 |
| Gemini | POST /v1beta/models/{model}:generateContent | alt=sse | 是 | 是 | 也支持 streamGenerateContent |
| Ollama Chat | POST /api/chat | NDJSON | 是 | 是 | 默认 stream=true，与官方一致 |
| Ollama 元信息 | GET /api/tags、/api/version、/api/show、/api/ps | - | - | - | 便于 Ollama 生态直接接入 |

认证方式全部支持：`Authorization: Bearer`、`x-api-key`、`x-goog-api-key`、`?key=`。

## 模型与能力配置

模型是配置项，不是代码。默认提供五个：

| 模型 ID | 定位 | 默认能力 |
| --- | --- | --- |
| `peo-human-1` | 通用旗舰 | vision / tools / streaming / reasoning / json_mode / code |
| `peo-human-fast` | 低延迟短问答 | tools / streaming |
| `peo-human-vision` | 截图、图表、试卷 | vision / tools / streaming / reasoning |
| `peo-human-code` | Agent 与代码 | tools / streaming / json_mode / code |
| `peo-human-mini` | 连通性测试 | streaming |

三种修改方式：

1. 控制台「设置 → 模型与能力」：图形化开关；
2. 直接编辑 `config.json` 的 `models` 数组（服务重启后生效）；
3. 管理 API：`POST /api/admin/models`（即时生效）。

能力会**直接约束请求**：向 `peo-human-fast` 传图片 → 400；向 `peo-human-mini` 传 `tools` → 400；未开启 streaming 的模型收到 `stream: true` → 400。

每个模型还可以配置 `default_params`（temperature / top_p / max_tokens / stop）：客户端没传时自动补齐，实际生效的参数会显示在控制台的「模型参数」里。

未知模型默认回退到 `server.default_model`（`server.allow_fallback_model`），因此把 `model` 写成 `gpt-4o` 之类的名字也能跑通，客户端不会因为模型名不匹配而失败。

## API Key 与限额

- 创建：控制台「设置 → API Key」或 `POST /api/admin/keys`；可以随机生成，也可以自己指定（16~128 位，仅字母、数字、`.`、`_`、`-`）。
- 明文只在创建后显示一次：服务端只保存 SHA-256 摘要，关闭提示后无法找回；忘记就删除重建，或用自定义值固定一个你记得的 Key。
- 额度：每个 Key 可设 `rpm`（每分钟请求数，0 为不限）与可用模型白名单。
- 并发：`queue.max_concurrent_per_key` 限制同一 Key 的并行请求数。
- 队列：`queue.max_pending` 满时返回 503，避免把服务器拖垮。

命令行走不了浏览器时，用 [scripts/peoai_admin.py](scripts/peoai_admin.py)：

~~~bash
PEOAI_HOME=/opt/peoai_server python3 scripts/peoai_admin.py add-key --name agent --rpm 60
PEOAI_HOME=/opt/peoai_server python3 scripts/peoai_admin.py set-password
~~~

## 操作台

单文件前端（[static/peoai.html](static/peoai.html)），源码在 [ui/](ui/)，用 `python scripts/build_ui.py` 组装。

前端默认请求**同源**的 `/peoai` 前缀；如果页面部署在别的域名（前后端不同源），在页面里设置 `window.PEOAI_SERVER_HOST = 'api.example.com'`，或修改 `ui/core.js` 顶部的 `SERVER_HOST`。首次加载会自动探测可用地址；登录页不再提供地址输入，设置页仍可手动覆盖。

后端默认 `security.allowed_origins = ["*"]`，允许任意前端域名跨域调用；若要收紧为白名单，把前端实际使用的每个 origin（例如 `https://frontend.example.com`）加入即可，预检请求会返回完整 CORS 头。

- **会话队列**：按会话聚合，一个会话展开后列出它的全部请求；点某一条请求即打开该请求的作答窗口，详情页顶部可在会话内切换请求。
- **筛选**：待处理 / 进行中 / 已完成，按模型、内容、请求 ID 搜索，实时通过 SSE 更新。
- **对话**：按角色渲染消息，保留 Markdown 代码块、行内代码与链接；不信任任何 HTML。
- **图片自动展示**：只要模型开启了 vision，请求里的图片会被解码并以网格展示，点击查看大图与尺寸信息；远端图片默认不加载，避免泄漏操作员出口 IP。
- **工具解析**：把 OpenAI `function.parameters`、Anthropic `input_schema`、Gemini `functionDeclarations` 统一成参数表，标出必填项、类型、枚举与说明，并给出原始 JSON Schema。
- **工具调用表单**：按 Schema 生成输入控件（枚举下拉、开关、数字、JSON 文本域 + 校验），填完加入回复，服务端产出标准 `tool_calls`。
- **思考消息**：作答区有独立的「思考内容」输入框与「发送思考片段」按钮，思考内容按协议写成 `reasoning_content` / `thinking` / `thought` / `thinking` 字段，不会混进正文。
- **流式作答**：`发送回答片段`、`发送思考片段` 实时推给流式客户端，`提交完成` 结束请求；支持 `Ctrl + Enter` / `Ctrl + Shift + Enter`。
- **风格**：Miuix 设计语言，深浅主题，全部图标为内联 SVG（无 emoji、无外部字体/图标库）。

## 安全设计

默认配置就按「可能暴露到公网」来设计：

- 默认强制 API Key；首次启动自动生成并只展示一次；
- 操作员会话使用随机 Bearer 令牌（进程内存储、可吊销、默认 12 小时过期），**不使用 Cookie**，因此没有 CSRF 面；
- 登录失败按 IP 计数并锁定，防在线爆破；
- 请求体、消息条数、单条长度、图片数量与单图大小全部有上限；
- 图片校验 MIME 白名单 + 文件魔数，data URL 解码前后都检查大小；
- 服务端**不抓取任何外部 URL**，因此不存在 SSRF 入口；
- 前端渲染全部通过 DOM 节点与 `textContent`，不使用 `innerHTML`，并附带 CSP；
- 审计日志只记录动作与元数据，不写请求正文与密钥；
- 响应头补齐 `nosniff`、`Referrer-Policy`、`X-Frame-Options`、`Permissions-Policy`，可按需开启 HSTS。

详细威胁模型与上线清单见 [docs/SECURITY_MODEL.md](docs/SECURITY_MODEL.md)。

## 部署

生产环境推荐「Nginx 反代 + systemd」：

~~~bash
# 1) 目录与用户
sudo useradd --system --create-home --home-dir /opt/peoai_server --shell /usr/sbin/nologin peoai
sudo rsync -a ./ /opt/peoai_server/
sudo chown -R peoai:peoai /opt/peoai_server

# 2) 虚拟环境
sudo -u peoai python3 -m venv /opt/peoai_server/venv
sudo -u peoai /opt/peoai_server/venv/bin/pip install -r /opt/peoai_server/requirements.txt

# 3) 服务
sudo cp /opt/peoai_server/peoai_server.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now peoai_server
sudo journalctl -u peoai_server -f

# 4) Nginx：把 deploy/peoai.nginx.conf 的内容加进站点配置
sudo nginx -t && sudo systemctl reload nginx
~~~

访问 `https://your-domain/peoai/` 即可打开控制台。SSE 必须关闭 `proxy_buffering`，片段里已经写好。

前端如果部署在别的域名（前后端不同源），用 `python scripts/inject_server_host.py api.example.com -o /path/home/peoai.html` 生成带服务器地址的页面。

完整步骤（HTTPS、端口、备份、升级、卸载）见 [docs/DEPLOY.md](docs/DEPLOY.md)。

## 配置参考

`config.json` 分区一览（完整字段见 [config.example.json](config.example.json)）：

| 分区 | 关键字段 | 作用 |
| --- | --- | --- |
| server | name / port / default_model / allow_fallback_model / console_enabled | 服务身份与默认模型 |
| security | require_api_key / max_body_bytes / max_images / max_image_bytes / allowed_origins / session_ttl_seconds / allow_remote_images | 准入、限额、CORS |
| queue | max_pending / request_ttl_seconds / max_concurrent_per_key / history_limit / persist_media | 队列与历史 |
| models | id / label / aliases / capabilities / context_window / max_output_tokens | 模型注册表 |
| api_keys | name / prefix / hash / rpm / models | 密钥（仅摘要） |
| operator | display_name / show_client_ip | 操作台行为 |
| logging | level / audit / max_bytes / backups | 日志与审计 |

环境变量优先于配置文件中的监听参数：`PEOAI_HOME`、`PEOAI_CONFIG`、`PEOAI_DATA`、`PEOAI_HOST`、`PEOAI_PORT`、`PEOAI_THREADS`、`PEOAI_LOG_LEVEL`。

## 目录结构

~~~text
peoai-server/
├── peoai_server.py            # 入口（--host/--port/--root/--no-waitress）
├── peoai/
│   ├── app.py                 # 应用工厂、安全响应头、错误处理
│   ├── config.py              # 配置、模型注册表、API Key
│   ├── store.py               # 请求状态机、队列、落盘、事件广播
│   ├── protocols/             # OpenAI / Anthropic / Gemini / Ollama 适配
│   ├── api_v1.py              # 对外协议路由
│   ├── api_operator.py        # 操作台接口与 SSE
│   ├── api_admin.py           # 管理接口
│   ├── auth.py                # 会话、登录锁定、Key 校验
│   ├── images.py              # 图片解码与安全校验
│   ├── ratelimit.py           # 滑动窗口限流
│   ├── tokens.py              # token 估算
│   └── audit.py               # 审计日志
├── ui/                        # 控制台源码片段
├── static/peoai.html          # 组装后的单文件控制台
├── scripts/build_ui.py        # 组装脚本（--check 校验产物）
├── scripts/inject_server_host.py  # 异源部署时把服务器地址注入页面
├── scripts/peoai_admin.py     # 命令行管理工具
├── tests/test_api.py          # 46 个端到端测试
├── deploy/peoai.nginx.conf    # 反向代理片段
├── peoai_server.service       # systemd 单元
├── examples/                  # 各协议调用示例
└── docs/                      # API / 部署 / 架构 / 安全 / 协议差异 / 开源指南
~~~

## 开源与仓库设置

本项目以 **MIT License** 开源（见 [LICENSE](LICENSE)）。选择理由与备选方案对比、仓库 About 文案、Topics、分支保护、发布流程，都整理在 [docs/GITHUB_SETUP.md](docs/GITHUB_SETUP.md)。

开仓库时的最小清单：

- **About**：`Human-in-the-loop AI API bridge — serve a real human behind OpenAI, Anthropic, Gemini and Ollama compatible endpoints.`（中文版见 GITHUB_SETUP）
- **Topics**：`openai-api`、`anthropic`、`gemini`、`ollama`、`human-in-the-loop`、`llm`、`flask`、`self-hosted`、`human-as-a-service`、`bridge`
- **License**：MIT（若你打算阻止他人闭源商用，改用 AGPL-3.0；迁移步骤见文档）
- **不要提交**：`config.json`、`data/`、任何日志与密钥（已在 `.gitignore` 中忽略）

## 常见问题

**Q：客户端一直挂起？**  
A：请求在等人作答。检查控制台队列、`request_ttl_seconds` 与 Nginx 的 `proxy_read_timeout`（SSE 需要关闭缓冲）。

**Q：`401 invalid_api_key`？**  
A：用 `Authorization: Bearer <key>`、`x-api-key` 或 `x-goog-api-key` 传 `data/bootstrap.txt` 里的 `pk_` 密钥。

**Q：能接入真实模型做兜底吗？**  
A：可以。人工作答与模型并不冲突：把本服务当作一个「模型」，在需要时由 Agent 或网关路由到它。

**Q：多人同时操作会冲突吗？**  
A：队列支持多人认领；同一请求由最后提交者结束。多控制台的最终状态通过 SSE 同步（键盘逐字同步不做，避免放大流量）。

**Q：token 数准确吗？**  
A：真人没有分词器，`usage` 为稳定估算（中日韩按字、其余按 4 字符 ≈ 1 token），仅保证量级与单调性。

**Q：可以关掉鉴权吗？**  
A：可以：`security.require_api_key = false`。仅建议在隔离内网使用，控制台会给出风险提示。

## 开发与测试

~~~bash
python -m venv venv
./venv/bin/pip install -r requirements.txt requests
./venv/bin/python -m unittest discover -s tests -v   # 46 个测试
./venv/bin/python scripts/build_ui.py --check        # 校验控制台产物
~~~

前端改动请修改 `ui/` 下的片段后重新组装，不要直接编辑 `static/peoai.html`。

## 维护者与治理

当前维护者、负责范围与联系方式见 [MAINTAINERS.md](MAINTAINERS.md)；决策方式、加入/退出流程与发布节奏见 [GOVERNANCE.md](GOVERNANCE.md)。重要改动需要 2 名维护者同意，日常修复 1 名即可合并。

## 贡献

欢迎 Issue 与 PR。请先阅读 [CONTRIBUTING.md](CONTRIBUTING.md) 与 [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md)；安全问题请按 [SECURITY.md](SECURITY.md) 私下报告。

## 许可

[MIT](LICENSE) © 2025 nihao303

> 使用者应自行确保人工作答内容与业务流程符合所在地区的法律法规、隐私要求与平台条款。
