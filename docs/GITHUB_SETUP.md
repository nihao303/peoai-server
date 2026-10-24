# 开源仓库设置指南

这份文档把「把项目放到 GitHub 上」需要做的决定一次讲清楚：仓库名、About 文案、Topics、许可证选择、分支保护、发布流程，以及容易踩的坑。

---

## 1. 仓库命名

推荐 `peoai-server`（与目录、systemd 服务名一致）。备选：

| 名称 | 适用场景 |
| --- | --- |
| `peoai-server` | 推荐，直白且与包名一致 |
| `peoai` | 更短，但容易与前端/客户端项目混淆 |
| `human-as-a-service` | 概念更吸睛，但与代码标识不一致 |

如果同名仓库已存在，用 `peoai-human-bridge` 或 `human-api-bridge`。

## 2. About（仓库简介）

GitHub 的 About 有 350 字符上限，建议：

**English（推荐，受众更广）**

~~~text
Human-in-the-loop AI API bridge: a real human answers behind OpenAI, Anthropic, Gemini and Ollama compatible endpoints. Conversation-grouped operator console, configurable models, API keys, vision, tool calls and reasoning messages.
~~~

**中文**

~~~text
把真人接入任何 AI API 的桥接服务：兼容 OpenAI / Anthropic / Gemini / Ollama；操作台按会话聚合请求，支持自定义模型、API Key、多模态、工具调用与思考消息。
~~~

**Website** 一栏可以填演示站或文档站，例如 `https://your-domain/peoai/`；没有就留空。

## 3. Topics（仓库标签）

复制到 GitHub 的 Topics 输入框（每行一个）：

~~~text
openai-api
anthropic
gemini
ollama
human-in-the-loop
human-as-a-service
llm
flask
self-hosted
api-gateway
multimodal
tool-calling
~~~

建议保留 10 个左右，太多会稀释相关性。

## 4. 许可证怎么选

本项目默认使用 **MIT**。三种常见选择的权衡：

| 许可证 | 允许闭源商用 | 修改后必须开源 | 专利授权 | 适用场景 |
| --- | :---: | :---: | :---: | --- |
| MIT | 是 | 否 | 无明示 | 最大化采用率，工具/框架/示例项目 |
| Apache-2.0 | 是 | 否 | 有 | 企业采用、需要专利与商标条款 |
| AGPL-3.0 | 否（网络服务也触发） | 是 | 有 | 防止他人拿去做闭源 SaaS |
| BSL / 自定义 | 视条款 | 视条款 | - | 商业授权、限时开源 |

**建议**：

- 想让人随便用、快速传播 → **MIT**（当前选择）；
- 公司主导、需要专利保护与明确贡献条款 → **Apache-2.0**；
- 核心价值在服务端、担心被云厂商直接托管 → **AGPL-3.0**。

**切换到其他许可证的步骤**：

1. 用目标许可证全文替换根目录 `LICENSE`（保留版权行年份与作者）；
2. 更新 `README.md` 的徽章与「许可」章节；
3. 若切到 Apache-2.0，补一个 `NOTICE` 文件；
4. 若切到 AGPL-3.0，在 `README` 顶部加一句「网络使用亦需开源」的说明；
5. 在 `CHANGELOG.md` 里记录许可证变更（已发布的旧版本不会自动变更，如需彻底切换要考虑新仓库或明确的双许可）。

## 5. 创建仓库

~~~bash
cd peoai-server
git init -b main
git add .
git commit -m "feat: initial release of PeoAI Server"

# 用 GitHub CLI（推荐）
gh repo create peoai-server --public --source=. --remote=origin --push

# 或者手动
git remote add origin git@github.com:nihao303/peoai-server.git
git push -u origin main
~~~

推送前务必确认：

~~~bash
git status --short          # 不应出现 config.json / data/ / 日志
git ls-files | grep -E 'config\.json|data/|\.log$' || echo "干净"
~~~

`.gitignore` 已经忽略这些路径；如果你之前手动加过，用 `git rm --cached` 移除。

## 6. 仓库设置清单

在 **Settings** 里逐项确认：

| 项目 | 建议值 | 说明 |
| --- | --- | --- |
| Description | 第 2 节的 About 文案 | 影响搜索与卡片展示 |
| Website | 演示地址（可选） | 没有就留空 |
| Topics | 第 3 节 | 提升可发现性 |
| Features → Issues | 开启 | 用于缺陷与功能讨论（不提供模板，开发者自行描述） |
| Features → Discussions | 视情况开启 | 用于问答与想法 |
| Features → Wiki | 关闭 | 文档放仓库里更易维护 |
| Features → Sponsorships | 可选 | 需要先开通 GitHub Sponsors |
| Social preview | 上传 1280×640 的封面图 | 分享链接时的预览 |
| Releases | 至少一个 `v1.0.0` | 见第 7 节 |
| Security → Private vulnerability reporting | 开启 | 配合 `SECURITY.md` |
| Security → Dependabot alerts | 开启 | 依赖漏洞提醒 |
| Security → Code scanning | 可选 | CodeQL 对 Python 友好 |
| Actions → General | 允许仓库内 Action | CI 需要 |
| Branches → Branch protection | `main` 要求 PR + 通过 CI | 至少开启「Require status checks」 |
| Merge button | 允许 squash merge | 保持线性历史 |

分支保护最小配置：

~~~text
Settings → Branches → Add branch protection rule
  Branch name pattern: main
  [x] Require a pull request before merging
  [x] Require status checks to pass before merging
        → 选择 CI 的 test 任务
  [x] Require conversation resolution before merging
  [ ] Require approvals（单人项目可关闭）
~~~

## 6.5 邀请协作者（多人维护）

### 权限分配

| 角色 | GitHub 角色 | 适合 |
| --- | --- | --- |
| 项目负责人 | Admin | 只有你，负责仓库设置与最终裁决 |
| 共同维护者 | Maintain | 长期合并 PR、发布、处理安全报告 |
| 评审者 | Write | 审阅 PR、分类 Issue，不能直接推 `main` |

操作：Settings → Collaborators and teams → Add people。**个人账号（如 nihao303）既不能创建 Team，也没有 Maintain 角色**，只有 Read / Write / Admin：共同维护者给 **Write**，评审者给 **Read**（或 Write）。如果以后把仓库迁移到 GitHub Organization，再建 Team `peoai-maintainers`，把成员加进 Team 并授予 **Maintain**，之后加人只改 Team。

### CODEOWNERS

仓库已带 `.github/CODEOWNERS`。邀请维护者后有两种做法：

1. 个人仓库：逐个列出维护者，例如 `* @nihao303 @another-maintainer`；
2. 组织仓库：换成 Team，例如 `* @your-org/peoai-maintainers`；
3. 或按目录追加个人/团队，例如 `/ui/ @frontend-maintainer`。

然后在分支保护里勾选 **Require review from Code Owners**，关键路径就必须由对应 owner 审核。

### 团队版分支保护

~~~text
Branch name pattern: main
[x] Require a pull request before merging
    Required approvals: 1（重要项目可设 2）
[x] Dismiss stale pull request approvals when new commits are pushed
[x] Require review from Code Owners（CODEOWNERS 配好后）
[x] Require status checks to pass before merging
[x] Require conversation resolution before merging
[x] Do not allow force pushes
[x] Do not allow deletions
[ ] Include administrators（可选）
~~~

### 标签保护与环境

- Settings → Tags → Add rule：pattern `v*`，限制创建/删除标签为维护者；
- Settings → Environments → New environment `release`，添加 required reviewers（至少 1 名维护者），以后自动发布 workflow 使用该环境；
- Settings → Collaborators 里不要把 Admin 给普通维护者。

### 推荐标签

`bug`、`enhancement`、`security`、`docs`、`protocol`、`ui`、`good first issue`、`help wanted`、`dependencies`、`needs-triage`。

### 安全报告

Security → Private vulnerability reporting 开启后，维护者可以在 Advisory 中协作；建议至少两名维护者可见报告。邮件兜底见 `SECURITY.md`。

## 7. 发布流程

~~~bash
# 更新 CHANGELOG.md 后
git tag -a v1.0.0 -m "PeoAI Server v1.0.0"
git push origin v1.0.0
~~~

在 GitHub 的 **Releases → Draft a new release**：

- Tag：`v1.0.0`
- Title：`PeoAI Server v1.0.0`
- 说明：粘贴 `CHANGELOG.md` 对应段落，附上「快速开始」三条命令；
- 可选附件：打包的 `peoai-server-v1.0.0.tar.gz`（不要包含 `data/` 与 `config.json`）。

版本号遵循语义化版本：协议/配置不兼容变更升 major，功能升 minor，修复升 patch。

## 8. 容易踩的坑

1. **密钥泄漏**：`config.json` 里有密码、管理令牌与 API Key 的哈希（哈希本身不致命，但 `data/bootstrap.txt` 是明文）。首推方案：永不提交 `config.json`，仓库只提供 `config.example.json`。
2. **历史提交里带了密钥**：一旦推送过，改写历史也无法保证已被缓存。立即轮换密码、令牌与所有 API Key，再考虑 `git filter-repo`。
3. **data/ 目录**：包含请求正文与图片，属于用户数据，绝对不要入库；若已入库，先清理再轮换所有 Key。
4. **CI 里的密钥**：用 Repository secrets，不要写进 workflow 文件。
5. **许可证头**：不需要在每个文件加版权头；保留根目录 `LICENSE` 即可，避免噪音。
6. **依赖许可证**：Flask（BSD-3-Clause）、Flask-CORS（MIT）、Waitress（ZPL-2.1），均与 MIT 兼容。
7. **人工作答的合规**：如果对外开放，需在 README/页面说明「回答由真人提供」，并遵守内容审核、隐私与劳动相关法规。
8. **演示站限流**：公网演示务必限制 `rpm` 与 `max_pending`，并定期清理 `data/requests`。

## 9. README 与文档的分工

| 文件 | 职责 |
| --- | --- |
| `README.md` | 一分钟看懂：是什么、怎么跑、怎么调 |
| `docs/API.md` | 每个端点的请求/响应与错误码 |
| `docs/DEPLOY.md` | systemd、Nginx、HTTPS、备份、升级 |
| `docs/ARCHITECTURE.md` | 模块划分、请求生命周期、扩展点 |
| `docs/SECURITY_MODEL.md` | 威胁模型、控制项、残余风险 |
| `docs/PROTOCOLS.md` | 四家协议的兼容矩阵与已知差异 |

## 10. 上线前检查表

- [ ] `git ls-files` 中没有 `config.json`、`data/`、`*.log`
- [ ] `LICENSE` 与 README 徽章一致
- [ ] About / Topics 已填写
- [ ] `CHANGELOG.md` 有 `v1.0.0` 条目，并打了 tag
- [ ] CI 全部通过（`python -m unittest discover -s tests`）
- [ ] `scripts/build_ui.py --check` 通过（控制台产物与源码一致）
- [ ] 仓库已开启私有漏洞报告
- [ ] 演示实例已改默认密码、删除 `data/bootstrap.txt`
- [ ] Nginx 已关闭 `proxy_buffering`，SSE 实测可用
