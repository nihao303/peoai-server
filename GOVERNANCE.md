# 治理与协作

这份文档说明项目如何做决定、如何合并代码、如何发布，以及如何邀请新的维护者。目标是：**多人协作时仍然可预期、可追溯、不依赖某一个人在线**。

## 角色

| 角色 | GitHub 权限 | 职责 |
| --- | --- | --- |
| 贡献者（Contributor） | 无（通过 Fork / PR） | 提交 Issue 与 PR，参与讨论 |
| 评审者（Reviewer） | Write | 审阅 PR、复现问题、管理 Issue 标签，不能直接推 `main` |
| 维护者（Maintainer） | Maintain | 合并 PR、管理 Issue/Release、处理安全报告、轮值发布 |
| 项目负责人（Lead） | Admin | 仓库设置、团队与权限、最终裁决、任命维护者 |

权限原则：**Admin 只给负责人；日常维护用 Maintain；外部贡献者一律 Fork + PR。**

## 决策方式

- **日常改动**（文档、示例、小修复、UI 调整）：任意一名维护者 review 通过即可合并；
- **重要改动**（协议行为、安全、配置格式、公开 API、破坏性变更）：至少 **2 名维护者** 同意；如果只有 1 名活跃维护者，则需在 PR 中公示 **7 天** 无反对后合并；
- **有分歧时**：先在 Issue/PR 里列出方案与取舍，由维护者讨论；仍无法达成一致时由项目负责人裁决，并把结论记录在 Issue 中；
- 所有决定都留在 Issue / PR / CHANGELOG 中，避免只在私聊里做决定。

## 维护者

### 加入

1. 由现有维护者提名，附上贡献记录（合并的 PR、Issue 分类、文档、社区支持等）；
2. 在 Issue 中公示 7 天，现有维护者无反对即可通过；
3. 通过后：加入 [MAINTAINERS.md](MAINTAINERS.md)、CODEOWNERS；个人仓库通过 Settings → Collaborators 授予 **Maintain** 权限，组织仓库则加入维护者 Team；
4. 新维护者先从 review 和 issue 分类开始，熟悉发布流程后再独立合并。

### 退出 / 移除

- 连续 6 个月不活跃，可转为荣誉维护者（Emeritus）并移出团队；
- 违反 [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md) 或泄露安全报告，经维护者共识可立即移除；
- 退出不影响已贡献代码的版权与署名。

## 发布

- 版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)：不兼容变更升 major，功能升 minor，修复升 patch；
- 发布前更新 `CHANGELOG.md`，确认 CI 全绿、`scripts/build_ui.py --check` 通过；
- 打标签 `vX.Y.Z` 并推送，在 GitHub Releases 写说明；
- 维护者轮流担任 release manager；安全修复可以由任意维护者加急发布，事后补记录。

## 安全

- 漏洞优先走私密渠道，见 [SECURITY.md](SECURITY.md)；
- 至少两名维护者可见私密报告，避免单点失联；
- 修复发布前不公开细节；发布后在 CHANGELOG 与 Security Advisory 中致谢。

## 修改治理文档

修改本文件需要 PR + 7 天评论期 + 维护者共识；涉及权限或安全流程的改动需要项目负责人确认。
