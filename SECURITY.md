# 安全策略

## 支持的版本

| 版本 | 安全更新 |
| --- | --- |
| 1.x | 支持 |

## 报告漏洞

**请不要通过公开 Issue 报告安全问题。**

- 邮件：`hhhhhh1234560@163.com`（建议同时开启 GitHub 仓库的 Private vulnerability reporting，优先走私密报告）
- 或在 GitHub 仓库的 **Security → Report a vulnerability** 中私密提交（需在 Settings 中开启 Private vulnerability reporting）

请尽量包含：

1. 受影响版本与部署方式；
2. 复现步骤或最小 PoC；
3. 影响评估（读取数据 / 接管操作台 / 拒绝服务）；
4. 你希望的署名方式。

我们会在 **72 小时内**确认收到，并在修复发布后致谢（除非你希望匿名）。

## 安全响应团队

- 当前安全响应维护者：[@nihao303](https://github.com/nihao303)、[@xrc111](https://github.com/xrc111)（分工见 [MAINTAINERS.md](MAINTAINERS.md)）；
- 建议至少两名维护者可见私密报告，避免单点失联；新增维护者时同步更新本文件与 [MAINTAINERS.md](MAINTAINERS.md)；
- 修复发布前不公开细节，发布后通过 GitHub Security Advisory 与 CHANGELOG 披露。

## 范围

以下问题属于本项目责任范围：

- 认证/授权绕过（API Key、会话、管理员令牌）；
- 跨站脚本（控制台渲染）；
- SSRF（服务端抓取外部地址）；
- 路径穿越、任意文件读写；
- 拒绝服务（无上限的资源消耗）；
- 敏感信息泄漏（日志、响应、错误信息）。

以下通常不在范围内：

- 部署方自身的配置错误（弱密码、开放的 0.0.0.0、未启用 HTTPS）；
- 第三方依赖的已知问题（请同时报告给上游，我们会跟进升级）；
- 需要已获得服务器 shell 才能利用的问题；
- 社会工程与物理攻击。

## 加固建议

见 [docs/SECURITY_MODEL.md](docs/SECURITY_MODEL.md) 的上线检查清单，最低要求：

- 修改默认密码并删除 `data/bootstrap.txt`；
- 保持 `security.require_api_key = true`；
- 使用 HTTPS 反向代理，限制 `allowed_origins`；
- 定期轮换 API Key 与管理员令牌。

## 披露政策

- 修复发布前不公开细节；
- 修复版本会出现在 `CHANGELOG.md` 与 GitHub Security Advisory；
- 严重问题会在 7 天内发布补丁版本。
