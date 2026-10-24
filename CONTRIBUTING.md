# 贡献指南

感谢你愿意改进 PeoAI Server。以下约定能让 PR 更快被合并。

## 开发环境

~~~bash
git clone https://github.com/nihao303/peoai-server.git
cd peoai-server

python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt requests
~~~

运行测试：

~~~bash
python -m unittest discover -s tests -v
~~~

本地启动：

~~~bash
PEOAI_HOME=. python peoai_server.py --port 5007 --no-waitress
~~~

首次启动的凭据在 `data/bootstrap.txt`。

## 代码风格

- Python 3.9+，4 空格缩进，行宽约 110；
- 标准库 → 第三方 → 项目内导入，分组空行；
- 公开函数写简短中文 docstring，说明「为什么」而不是「做了什么」；
- 错误统一抛 `PeoaiError`，不要直接 `abort()` 或返回裸字符串；
- 新增配置项时必须同时更新：`config.py` 默认值、`config.example.json`、`docs/API.md` 或 README 配置表、`api_admin.py` 白名单（如果允许控制台修改）；
- 不要在服务端抓取外部 URL；
- 前端不得使用 `innerHTML` 渲染任何来自请求的内容。

## 修改控制台

前端源码在 `ui/`：

| 文件 | 内容 |
| --- | --- |
| `head.html` | HTML 骨架与全部 CSS |
| `core.js` | 状态、图标、API、SSE、登录 |
| `workbench.js` | 队列、详情、图片、工具展示 |
| `composer.js` | 作答、流式片段、工具表单 |
| `settings.js` | 设置 |
| `docs.js` | 接入文档 |
| `init.js` | 初始化与事件绑定 |

修改后必须重新组装并提交产物：

~~~bash
python scripts/build_ui.py
python scripts/build_ui.py --check   # CI 会执行
~~~

约定：不使用 emoji，新图标请用内联 SVG 加入 `ICONS`；不使用模板字符串（保持可读的字符串拼接）。

## 提交信息

采用 Conventional Commits：

~~~text
feat: 支持 Gemini 流式 functionCall
fix: 修复 SSE 在客户端断开后未退订
docs: 补充 Nginx SSE 配置说明
refactor: 拆分 store 的持久化逻辑
test: 覆盖工具调用参数校验
chore: 升级 waitress
~~~

## 分支与 PR

- 从最新的 `main` 切分支：`feat/xxx`、`fix/xxx`、`docs/xxx`；
- 一个 PR 只做一件事，避免顺手重构无关文件；
- 描述里写清楚：做了什么、为什么、怎么验证、关联 Issue（如 `Closes #12`）；
- 前端改动附深色/浅色截图；
- 不要直接向 `main` push，分支保护会拦截。

## 评审与合并

- 至少 **1 名维护者** 审核通过；协议、安全、配置格式、破坏性变更需要 **2 名**（见 [GOVERNANCE.md](GOVERNANCE.md)）；
- 评审意见解决后再合并，使用 **Squash merge** 保持线性历史；
- 合并后删除分支；
- 维护者可以要求拆分过大的 PR，或先开 Issue 对齐设计。

## 发布

- 维护者按 [GOVERNANCE.md](GOVERNANCE.md) 轮值发布；
- 发布前更新 [CHANGELOG.md](CHANGELOG.md)，确认 CI 与 `scripts/build_ui.py --check` 通过；
- 打标签 `vX.Y.Z` 并在 GitHub Releases 写说明；
- 安全修复可以加急，事后补 CHANGELOG。

## 成为维护者

持续提交高质量 PR、参与 review、帮助分类 Issue，就有机会被提名为评审者或维护者。流程见 [GOVERNANCE.md](GOVERNANCE.md#维护者)。

## PR 检查表

- [ ] 测试通过（`python -m unittest discover -s tests`）
- [ ] 前端改动已重新运行 `scripts/build_ui.py` 并提交产物
- [ ] 新增配置项已同步文档与示例
- [ ] 不包含密钥、`config.json`、`data/`、日志
- [ ] 安全相关改动在描述里说明威胁与缓解
- [ ] 面向用户的文案使用中文（代码注释可中英混排）

## 新增协议

参考 [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) 的「扩展一个新协议」，并至少提供：

1. 解析单测（含非法输入）；
2. 非流式集成测试；
3. 流式集成测试；
4. 错误体格式测试。

## 报告问题

- 功能与缺陷：直接开 Issue 描述现象、复现步骤与环境即可（不强制模板）；
- 安全漏洞：见 [SECURITY.md](SECURITY.md)，不要开公开 Issue；
- 大改动请先开 Issue 对齐设计，避免白做。

## 许可

提交即表示你同意以 [MIT](LICENSE) 许可证发布你的贡献。
