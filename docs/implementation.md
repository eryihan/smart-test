# v1.3 设计与本次实现

本次交付是可安装的 Agent Skill。业务分析、测试代码和 CI 内容由加载 skill 的 Codex / Claude Code 根据目标仓库生成；Python 工具只负责有明确输入输出的重复操作。

| 设计能力 | 实现位置 | 执行边界 |
|---|---|---|
| 五个主入口与高级入口 | SKILL.md、workflows.md、verification.md、ci.md | 使用 init/scan/changes/check/pipeline；不提供同名系统 CLI |
| Repository Analyzer / Profile / doctor | inspect_repo.py + workflows.md | 静态证据、构建文件、依赖提示、环境工具存在性；Agent 复核 effective model、运行能力 |
| Business Oracle / Characterization | SKILL.md、workflows.md、governance.md | 必须溯源，不把当前行为当业务真值 |
| Directive / Scope / Lifecycle | state.py + governance.md | 结构化存储，binding 筛选；语义冲突和 scope 交集由 Agent 判断 |
| Approval / Decision Registry | state.py | proposal、真实授权来源、版本和事件；不代替宿主授权系统 |
| Effective Context | governance.md + context-and-plan.example.json | Agent 合并事实、Oracle、指令和 policy，不能只汇总 ACTIVE |
| Invalidation | state.py | 文件指纹、显式 topic、传递依赖；新文件/外部环境需 Agent 补充触发 |
| Risk / 最低充分层级 | java-testing.md | 按具体风险分配层级，无固定测试比例 |
| Baseline / Test Debt | workflows.md | 风险排序，默认不全量补历史债务 |
| Change / Module Impact | inspect_repo.py + workflows.md | staged / HEAD+工作树 / merge-base+工作树；模块依赖是保守提示，非完整调用图 |
| Bootstrap / Builder | java-testing.md + workflows.md | 读取真实构建与版本后局部修改，不提供未经验证的通用依赖大模板 |
| Runner / Verification | verification.md + collect_reports.py | Agent 执行真实命令；脚本检查报告与执行窗口，不替代执行 |
| Failure Triage / Flaky | verification.md | 六类归因、有限诊断重试、未归因不宣称产品缺陷 |
| Quality / Coverage / PIT | java-testing.md、verification.md | 语义审查和实际报告；不靠关键词或覆盖率证明正确 |
| CI Candidate / Verify / Finalize | ci.md | 来自有效验证命令；本地验证和 provider 实跑分开记录；默认交付 patch |
| 安装、更新与分发 | .claude-plugin/、skills/smart-test、README.md | Codex 内置 skill-installer 从 GitHub 安装；Claude Code 使用插件市场；两宿主共用一份 skill |

与设计稿的两处结构调整：

1. 项目状态使用 JSON，避免安装额外运行依赖。directives、decisions、approval events 合并到单一原子更新账本，其余产物保留独立文件。
2. 合并相关 reference，主入口仅按模式加载。没有把设计稿全文塞入 SKILL.md，也没有给每个逻辑入口创建一个假 CLI。

设计稿举出的框架、版本和场景作为选择依据及例子，不能当目标仓库事实。首次接入不会因“推荐用 Testcontainers”自动安装 Docker，已有用户授权也不会被额外确认流程覆盖。

辅助工具退出码：扫描/状态操作成功 0、输入或环境错误 2；报告检查证据通过 0、不足或失败 1、输入错误 2。脚本成功不等于目标工程验证通过。

`tools/install_skill.py` 和 `tools/build_package.py` 仅用于本地开发、自定义目录和离线分发，见 [开发说明](development.md)。用户安装主流程不要求克隆源码或运行这些脚本。
