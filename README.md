# smart_test

smart_test 帮助后端项目评估现有测试、为变更补测、诊断失败和接入 CI。Agent 根据业务风险、运行时和已有设施选择测试边界，优先补强现有用例，并报告实际验证结果与剩余缺口。

当前专项覆盖 Java 8+、Spring Boot 2/3、Maven/Gradle；其他后端技术栈按原生设施处理，专项能力尚未验证。数据库和中间件测试使用隔离环境。

采用 [Agent Skills 目录格式](https://agentskills.io/specification)，兼容宿主共用 `skills/smart-test`。项目中的测试、构建、fixture、脚本和正式 CI 独立于 skill 安装目录运行。

## 安装

### Codex

在 Codex 对话中发送：

```text
$skill-installer 请安装 https://github.com/eryihan/smart_test/tree/main/skills/smart-test
```

安装后开启新会话；技能列表仍未刷新时重启 Codex。在目标后端仓库中请求 `$smart-test help`，确认实际加载路径、版本和安装来源。

### Claude Code

在 Claude Code 会话中执行：

```text
/plugin marketplace add eryihan/smart_test
/plugin install smart-test@smart-test
```

终端也可使用 `claude plugin marketplace add eryihan/smart_test` 和 `claude plugin install smart-test@smart-test`。默认安装到用户范围；仅在当前项目启用时，在项目目录执行：

```bash
claude plugin install smart-test@smart-test --scope project
```

安装后重启会话或执行 `/reload-plugins`。使用 `claude plugin list` 查看启用状态，`claude plugin details smart-test` 查看组件；随后请求 `/smart-test:help`。

本仓库提供第三方插件市场。插件调用使用 `/smart-test:<入口>`，兼容 `/smart-test:smart-test <入口>`；独立 skill 与插件择一安装，避免重复发现。

### 其他 Agent 与离线安装

通过宿主安装功能，从 `https://github.com/eryihan/smart_test/tree/main/skills/smart-test` 安装完整目录，或把离线包中的 `smart-test/` 放入宿主指定的 skills 目录。按宿主方式调用和刷新，并确认实际加载路径与版本。

维护源码、自定义目录和离线安装见 [开发与分发](docs/development.md#本地脚本安装)。实施和验证需具备相应文件、命令与环境权限。

## 开始使用

在目标后端仓库中直接描述任务，例如：

```text
只补 order 模块的金额边界测试；拒绝后不能写订单或扣额度。
```

也可以使用明确入口：

```text
Codex:       $smart-test changes
Claude Code: /smart-test:changes
```

补当前改动或运行已有测试可直接开始，无需先 `init`。只分析时明确说“不修改、不执行”，或使用 `changes --dry-run`。搭建设施用 `init`，评估存量缺口用 `scan`，执行已有测试用 `check`，生成 CI 候选用 `pipeline`，查看待办与已有证据用 `status`。

Agent 先检查已有测试与业务依据，再补强或新增用例。Unit 与数据库集成分别报告；环境受阻时列出未执行范围。已有规范和待办直接复用，运行证据优先使用原生报告或 CI，需要接续或复核时才保存资料。

完整入口、控制项、结果解释和典型请求见 [使用指南](skills/smart-test/references/help.md)。安装后可请求 `$smart-test help` 或 `/smart-test:help`。

## 更新和卸载

直接说“更新 smart-test”，或使用：

```text
Codex:       $smart-test update
Claude Code: /smart-test:update
```

更新沿用原安装来源与范围，并保护本地定制。具体步骤、宿主原生命令和失败恢复见 [更新说明](skills/smart-test/references/help.md#更新-skill)。

卸载使用 `$smart-test uninstall` 或 `/smart-test:uninstall`，先交接当前项目，再移除安装包。只移除安装包时按指定范围操作，项目测试资产仍保留。宿主原生命令与交接边界见 [退出管理与卸载](skills/smart-test/references/help.md#退出管理与卸载)。

## 反馈

在使用现场说“刚才这个处理不对，帮我整理反馈”。Agent 整理脱敏的任务、实际/期望行为、依据、版本和最小复现，并按安装来源提供反馈入口；默认上游为 [GitHub Issues](https://github.com/eryihan/smart_test/issues)。提交需要明确授权，诊断附件按需提供。

操作方法见 [反馈说明](skills/smart-test/references/feedback.md)，维护者处理见 [反馈与回归](feedback/README.md)。

## 文档导航

| 想了解什么 | 阅读位置 |
|---|---|
| 调用入口、控制项、状态、更新和卸载 | [使用指南](skills/smart-test/references/help.md) |
| Agent 如何处理测试任务 | [SKILL.md](skills/smart-test/SKILL.md)，按任务读取其中链接的 references |
| 项目资料何时保存、更新和清理 | [资料与留存](skills/smart-test/references/artifacts.md) |
| 源码职责、文档归属和扩展方式 | [开发架构](docs/development-architecture.md) |
| 本地验证、离线安装、打包和发布 | [开发与分发](docs/development.md) |

维护资料和历史验证结果留在源码仓库或本地报告中；独立安装包只包含 `skills/smart-test/`，Claude 插件另使用 `.claude-plugin/` 和 `commands/`。项目专项报告、原始日志与运行证据保留在被 Git 忽略的 `reports/`。

许可证：[Apache License 2.0](LICENSE)，随独立 skill 包分发。

官方参考：[OpenAI skill 文档](https://learn.chatgpt.com/docs/build-skills)、[OpenAI 当前插件示例](https://github.com/openai/plugins)、[Anthropic skill 示例](https://github.com/anthropics/skills)、[Claude Code 插件安装](https://code.claude.com/docs/en/plugins/install)与[插件市场](https://code.claude.com/docs/en/plugin-marketplaces)。
