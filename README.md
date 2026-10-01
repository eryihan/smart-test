# smart_test

smart_test 是企业级后端项目的测试助手，维护项目测试规范、设施、用例和验证记录：根据实际语言、运行时、架构、业务风险和已有设施选择测试方案，评估测试缺口、补测试、执行诊断并生成 CI 候选。

当前专项实现覆盖 Java 8+、Spring Boot 2/3、Maven/Gradle。其他语言支持按实际项目逐步扩展。数据库、中间件测试使用隔离环境，结果列明未执行范围。

采用 [Agent Skills 目录格式](https://agentskills.io/specification)，兼容该格式的 Agent 可安装同一份 `skills/smart-test`。Codex 和 Claude Code 是已提供的安装示例，核心流程不依赖它们的专属能力。

许可证：[Apache License 2.0](LICENSE)，随独立 skill 包分发。

## 1. 安装

通过宿主安装，无需克隆仓库或运行 Python 脚本。

### 1.1 在 Codex 中安装

在 Codex 对话中发送：

```text
$skill-installer 请安装 https://github.com/eryihan/smart_test/tree/main/skills/smart-test
```

Codex 内置的 `skill-installer` 会从 GitHub 下载并安装 `skills/smart-test`。安装完成后，开启新会话，或等待当前会话刷新技能列表。

### 1.2 在 Claude Code 中安装

在 Claude Code 会话中执行：

```text
/plugin marketplace add eryihan/smart_test
/plugin install smart-test@smart-test
```

也可以在终端执行：

```bash
claude plugin marketplace add eryihan/smart_test
claude plugin install smart-test@smart-test
```

默认安装范围是当前用户。只在当前项目启用时，在项目目录执行：

```bash
claude plugin install smart-test@smart-test --scope project
```

安装完成后重启会话，或执行 `/reload-plugins`。Claude Code 中的调用名带插件命名空间：

```text
/smart-test:smart-test init
```

插件提供 `/smart-test:help|init|scan|changes|check|pipeline|status|update|uninstall`，也兼容 `/smart-test:smart-test <模式>`。

本仓库提供第三方 Claude Code 插件市场。

### 1.3 其他 Agent

按宿主的 skill 安装功能，从 `https://github.com/eryihan/smart_test/tree/main/skills/smart-test` 安装完整目录，或将离线包中的 `smart-test/` 放入宿主指定的 skills 目录。不自行猜测安装路径；其他 Agent 不需要 Claude 插件清单或 Codex 界面配置。

维护源码或离线安装时，可显式指定目录，不必指定宿主品牌：

```bash
python3 tools/install_skill.py --dest <Agent的skills目录>
```

按宿主方式调用和刷新，确认已加载的 `SKILL.md` 路径与版本。实施和验证需具备相应文件、命令与环境权限。

## 2. 安装验证

### 2.1 验证 Codex

在 Codex 中发送：

```text
列出当前可用的 smart-test skill，并确认它来自 eryihan/smart_test。
```

如果 skill 已加载，Codex 可以识别 `$smart-test` 并执行后续工作模式。

### 2.2 验证 Claude Code

在终端执行：

```bash
claude plugin list
claude plugin details smart-test
```

确认插件状态为 enabled，组件列表中包含一个名为 `smart-test` 的 skill。

## 3. 开始使用

在目标后端仓库中启动宿主，直接描述任务。补当前改动或运行已有测试不要求先 init；当前完整专项指导为 Java。调用示例：

```text
Codex:       $smart-test changes
Claude Code: /smart-test:changes
```

也可直接指定范围与规则，例如“只补 order 模块的金额边界测试；拒绝后不能写订单或扣额度”。skill 会先检查已有测试，选择能验证该行为的边界，再补强或新增测试并运行。

只分析时明确说“不修改、不执行”，或使用 `changes --dry-run`。搭建测试设施用 `init`，找存量缺口用 `scan`，运行已有测试用 `check`，生成 CI 候选用 `pipeline`，查看进展和待办用 `status`。

完整调用方式、控制项、覆盖率、结果解释和典型请求统一见 [使用指南](skills/smart-test/references/help.md)。安装后可直接请求帮助：

```text
Codex:       $smart-test help
Claude Code: /smart-test:help
```

首次正常任务接管已有测试约定，维护一份生效项目规范；每次任务默认在 `.smart-test/records/` 记录检查范围、发现、修改与下一步，实际执行关联运行证据。scan 会留存分析过程，help、status、明确只读和 dry-run 不写文件。Unit 与数据库集成分别报告结果。

用户只需给出测试目标与范围，Agent 负责选择方案、维护规范、记录和交付。测试代码、构建、执行脚本和正式 CI 留在项目原生位置，可独立于 skill 运行。

## 4. 更新和卸载

维护入口：`update` 更新安装包，`uninstall` 交接当前项目并卸载。交接保留成熟测试框架、规范和历史，解除对 skill 安装路径的依赖；安装包卸载与项目交接分别报告。具体步骤见 [退出管理与卸载](skills/smart-test/references/help.md#退出管理与卸载)。

```text
Codex:       $smart-test uninstall
Claude 插件: /smart-test:uninstall
```

快捷更新可直接对 Agent 说“更新 smart-test”，或使用：

```text
Codex:       $smart-test update
Claude 插件: /smart-test:update
其他 Agent:  按宿主方式调用 smart-test update
```

更新沿用原安装来源和范围，检查本地定制，保留备份并核对新版本；不修改目标项目的业务代码、测试配置或 `.smart-test/`。完整规则与离线/失败处理集中在 [更新说明](skills/smart-test/references/help.md#更新-skill)。旧版尚无 update 入口时，先用原安装渠道升级一次。

### 4.1 Claude Code

```bash
claude plugin marketplace update smart-test
claude plugin update smart-test@smart-test
```

更新后重新加载插件或开启新会话。推荐使用 skill 的 uninstall 先交接；只移除安装包时可用宿主命令：

```bash
claude plugin uninstall smart-test@smart-test --keep-data
```

项目级操作增加 `--scope project`。

### 4.2 Codex

在 Codex 中发送：

```text
$smart-test update
```

使用 `$smart-test uninstall` 完成交接，再按宿主规则移除已确认的 skill 目录。直接移除安装包不会执行项目交接，但项目内的测试代码、规范和 `.smart-test/` 历史仍保留。

Claude 的第三方市场默认不自动更新；需要时可在 `/plugin` 的 Marketplaces 页开启该市场的自动更新。自动更新后的当前会话仍需按提示重新加载。[Claude 更新机制](https://code.claude.com/docs/en/discover-plugins#keep-plugins-updated)

## 5. 使用问题反馈

在当前对话中请求导出脱敏反馈，并指定目标项目外的新目录；导出不自动上传。用户操作见 [使用指南](skills/smart-test/references/help.md#反馈)，维护者收集、定位和回归见 [反馈处理](feedback/README.md)。

## 6. 维护者资料

[开发架构](docs/development-architecture.md) 说明 Agent、辅助工具和目标项目的职责及扩展边界；[开发与分发](docs/development.md) 说明验证、离线安装和打包。二者随代码维护，不进入独立 skill 安装包。历史验证结果仅对应其记录的版本。

公开仓库保留测试、评测 fixture、分发工具和脱敏反馈；项目专项报告、原始日志与运行证据保留在本地的 `reports/`，不提交。独立 skill 包只包含 `skills/smart-test/`；Claude 插件另使用 `.claude-plugin/` 和 `commands/`。

安装机制参考 [Claude Code 插件安装](https://code.claude.com/docs/en/plugins/install)、[Claude Code 插件市场](https://code.claude.com/docs/en/plugin-marketplaces) 和 [OpenAI 官方 skill-installer](https://github.com/openai/skills/tree/main/skills/.system/skill-installer)。
