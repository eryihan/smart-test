# smart_test 使用说明

smart_test 面向 Java / Spring Boot 仓库：读取仓库结构、业务依据、现有测试和当前变更，形成测试策略，补充测试，执行验证，生成 CI 候选方案，并区分已验证与待验证部分。

支持 Java 8+、Spring Boot 2/3、Maven 和 Gradle。数据库、Redis、消息队列和远程服务测试需要相应的隔离环境；环境不可用时标记阻塞，保留可执行部分。

本项目采用 [Apache License 2.0](LICENSE)。独立安装的 skill 包也随附同一份许可证。

## 1. 安装

普通用户不需要克隆仓库，也不需要运行 Python 安装脚本。

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

插件也提供可单独选择的模式命令：`/smart-test:help`、`/smart-test:init`、`/smart-test:scan`、`/smart-test:changes`、`/smart-test:check` 和 `/smart-test:pipeline`。原有 `/smart-test:smart-test <模式>` 仍可使用。

本仓库是第三方 Claude Code 市场，未收录到 Anthropic 官方市场。

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

## 3. 按任务开始

补当前改动可直接使用 `changes`，执行已有测试可直接使用 `check`，不需要先 init。普通任务说明风险与依据后直接补测试、运行并解释结果；实际执行保留运行证据，长期约定、计划与治理账本按复用、恢复或审计需要保存。已有项目约束仍然适用。

需要搭建测试体系时，在目标 Java 仓库根目录启动 Codex 或 Claude Code，执行 `init`：

```text
Codex:   $smart-test init
Claude:  /smart-test:smart-test init
```

smart_test 按以下顺序处理：

1. 识别语言、JDK、Maven/Gradle、模块和 Spring Boot 版本。
2. 检查数据库、缓存、消息队列、远程客户端、安全配置、迁移脚本和 CI。
3. 读取现有测试、业务文档、接口协议和 schema，建立可追溯的业务依据。
4. 形成项目画像、测试策略和缺失基础设施清单。
5. 对尚未授权的关键技术选择或未确定业务规则给出具体方案，合并必要的确认；已有授权直接复用。
6. 在已授权范围内补充测试设施和最小有效测试，并执行验证。

只查看分析结果，不创建状态文件、不修改代码、不执行构建时，使用：

```text
$smart-test init --dry-run
```

首次接入时建议同时给出边界，例如：

```text
允许修改测试代码、测试资源和测试相关构建配置；禁止修改生产代码。
数据库测试需要可用的同引擎隔离实例；环境信息不完整时先报告阻塞原因，不自动替换成其他数据库。
本次只处理 order 模块。
```

## 4. 六个工作模式

| 命令 | 用途 | 主要产物 |
|---|---|---|
| `help` | 查看使用方式、控制项、产物和边界 | 帮助说明，不写项目文件 |
| `init` | 建立项目画像和测试策略 | 项目画像、业务依据、测试策略、测试 policy |
| `scan` | 扫描存量代码和测试缺口 | 风险地图、测试债务、治理顺序 |
| `changes` | 分析当前变更并补充测试 | 影响分析、测试计划、测试代码、验证结果 |
| `check` | 执行测试并判断结果 | 执行记录、测试报告、失败归因 |
| `pipeline` | 生成并检查 CI 草稿或已验证候选 | CI candidate、分项验证记录、正式 CI 建议补丁 |

`help / init / scan / changes / check / pipeline` 是六种工作模式，不是系统终端命令。自然语言请求由 Agent 映射到相应模式：

```text
查看 smart-test 帮助
扫描这个项目的测试缺口
检查当前改动并补测试
执行必要验证并分析失败原因
生成已验证的 CI 候选方案
```

## 5. 日常流程

### 5.0 查看帮助

首次使用或需要确认参数时，先执行：

```text
$smart-test help
$smart-test help coverage
```

`help` 只读取随 skill 分发的帮助文档，不扫描目标仓库、不运行构建、不创建 `.smart-test/`。也可以直接描述问题，例如“如何判断增量覆盖率？”。

### 5.1 扫描存量测试缺口

```text
$smart-test scan
```

`scan` 默认分析整个仓库，输出风险排序和治理建议，不会一次性补完全部历史测试。需要限定范围时，直接说明模块、路径或风险类型：

```text
$smart-test scan
只扫描 payment 模块，优先分析权限、金额和事务风险。
```

### 5.2 分析当前变更

```text
$smart-test changes
```

默认读取当前工作树相对 HEAD 的变更，包括 staged、unstaged 和未被 Git 忽略的新文件。可以限定分析范围：

```text
$smart-test changes --staged
$smart-test changes --base origin/main
```

`--staged` 只分析暂存区；`--base` 从指定分支与当前 HEAD 的共同祖先分析到当前工作树。smart_test 将变更映射到模块、调用方、数据库、接口和业务风险，再形成测试计划。

只生成计划，不写测试、不执行构建：

```text
$smart-test changes --dry-run
```

### 5.3 执行验证

```text
$smart-test check --fast
$smart-test check --full
```

- `--fast`：执行当前变更所需的最小充分验证集。
- `--full`：扩大到相关模块或完整验证集。

smart_test 直接依据实际执行与质量门判断结果。使用持久计划或其他结构化产物时，只校验本次依赖的文件；没有计划或账本时不为 check 补造。结构错误阻断依赖它的工作，结构合法不等于测试通过。

smart_test 记录实际命令、退出码、测试数量、失败、跳过、耗时和报告路径。必需测试未执行、报告陈旧、环境阻塞或存在未解决业务歧义时，不报告完整验证通过。

### 5.4 生成 CI 候选方案

需要接入 CI 时执行；有本地验证记录则复用，没有完整环境也可先生成待验证草稿：

```text
$smart-test pipeline
```

smart_test 从仓库实际构建和测试约定选择命令，在 `.smart-test/ci-candidate/` 生成候选，并分别记录命令验证、语法检查、provider 实跑状态。候选检查包括：

1. 每条命令的来源、是否执行，以及对应代码版本。
2. Unit、Integration、Contract 和关键流程是否被正确纳入。
3. 测试失败是否返回非零退出码。
4. 测试报告路径、Runner 能力、容器和网络要求是否明确。
5. Secret 是否通过 CI Secret 或环境变量引用，是否存在硬编码凭证。

必需 Integration 在本地受阻时，可以生成草稿并标 NOT_VERIFIED/NOT_RUN，说明需要在 CI 验证的部分；不能声称完整通过。消费结构化输入时校验实际依赖，不固定要求五类治理文件。既有错误状态先修复，不能删 blocker 来保留 PASS。

以下 `verify` 和 `finalize` 仅表示 `pipeline` 内的阶段，不是独立入口或命令别名。检查候选方案：

```text
$smart-test pipeline verify
```

完整所需命令在本地或等价 CI 环境验证、候选检查通过后，生成正式 CI 建议补丁：

```text
$smart-test pipeline finalize
```

`finalize` 默认输出可审阅的 patch，不直接覆盖正式 CI；证据不完整时保持草稿并说明缺口。正式修改需要明确授权。若需先安装草稿以获得首次 CI 执行，必须有针对未验证候选的明确授权，不能将其称为 finalize 已验证成功。

## 6. 覆盖率策略

覆盖率可以由用户指定，也可以不参与本次 smart_test 判定。未指定时不添加新的覆盖率工具、数字阈值或阻断条件；仓库已有 coverage、changed coverage 或关键模块门禁的，仍按仓库规则检查。未指定且没有既有门禁时，覆盖率记为 `NOT_APPLICABLE`，不影响其他验证。

可在 `init`、`changes` 或 `check` 中直接说明要求：

```text
本次只报告覆盖率，不设置阻断阈值。
本次要求 order 模块整体行覆盖率至少 75%。
以 origin/main 为基线，本次要求增量行覆盖率至少 80%。
整体行覆盖率至少 75%，并且以 origin/main 为基线的增量行覆盖率至少 80%。
```

覆盖率要求记录为 `UNSPECIFIED`、`REPORT_ONLY`、`OVERALL`、`INCREMENTAL` 或 `BOTH`。整体覆盖率按可执行项总数加权汇总；增量覆盖率只计算基线到当前版本之间新增或修改的可执行代码行。没有可执行变更行是 `NOT_APPLICABLE`，无法解析基线、源码映射或报告与当前代码不匹配是 `UNKNOWN`，不用整体结果替代增量结果。阈值按原始百分比与 `>=` 比较，不先四舍五入。完整规则见 [覆盖率策略](skills/smart-test/references/coverage.md)。

`check --fast` 和 `check --full` 只控制执行范围，不改变覆盖率模式；快速验证不能证明整体门禁已通过。覆盖率通过也不能替代关键业务行为、接口契约或数据库语义的测试。

## 7. 指定约束和业务依据

可在任意阶段补充约束，建议明确写出范围、强度和生命周期：

```text
只处理 order 模块，本轮不治理历史测试债务。
数据库测试必须使用 PostgreSQL 16，不允许用 H2 替代。
审批拒绝后的状态必须是 REJECTED，业务依据是 docs/approval.md。
本轮不要运行集成测试，只列出未验证风险。
优先使用项目已有的 AssertJ 风格。
```

约束分为：

- **业务事实**：进入业务依据，用于决定正确结果和断言。
- **技术约束**：限制测试框架、数据库、容器和构建方式。
- **范围约束**：限制模块、路径、测试类型或本次变更。
- **执行约束**：限制是否写代码、是否运行测试、是否修改生产代码。
- **偏好**：在没有冲突时作为选择依据。

新约束改变技术前提时，只重评受影响的策略、计划或 CI candidate。单纯文件指纹变化先触发复核；确认语义和原授权仍适用后可继续使用，不自动要求重新授权。完整的作用域、生命周期、决策依赖和审计账本仍可按需启用。

常用控制项：

| 控制项 | 行为 |
|---|---|
| `--dry-run` | 只读分析，不写仓库文件、不执行构建、不启动服务 |
| `--strict` | 对新的关键策略和计划逐阶段展示 |
| `--auto` | 复用既有约定和授权继续执行；新选择超出授权或存在歧义时提出具体待定事项 |

## 8. 项目产物

smart_test 按需在 `.smart-test/` 保存信息。局部任务无需先创建画像、Oracle、context、strategy、plan 和 status；默认保留实际运行记录。以下格式全部兼容：

| 路径 | 内容 |
|---|---|
| `state.json` | 可选治理账本：跨会话约束、决策依赖、授权来源与失效记录 |
| `project-profile.json` | 已核实的项目画像和证据 |
| `business-oracle.json` | 业务依据、冲突和未知项 |
| `effective-context.json` | 当前阶段生效的范围和约束 |
| `test-strategy.json` / `test-policy.json` | 测试层级、技术选择和质量要求 |
| `test-plan.json` / `test-debt.json` | 测试计划和测试债务 |
| `status.json` | 按需生成的阶段状态与阻塞摘要，结果来自实际证据 |
| `runs/` / `reports/` | 执行记录、测试报告和失败分析 |
| `ci-candidate/` | CI 候选文件和建议补丁 |

新任务优先把长期约定放 test-policy、具体断言依据放计划条目；需要独立复用才拆分。已有文件不删除、不强制迁移。按需规则见 [产物与校验](skills/smart-test/references/artifacts.md)。测试代码写入项目现有测试目录。不要把凭证、生产连接信息或真实敏感数据写入 `.smart-test/`。

## 9. 更新和卸载

### 9.1 Claude Code

```bash
claude plugin marketplace update smart-test
claude plugin update smart-test@smart-test
```

更新后重新加载插件或开启新会话。卸载：

```bash
claude plugin uninstall smart-test@smart-test
```

项目级操作增加 `--scope project`。

### 9.2 Codex

在 Codex 中发送：

```text
请从 https://github.com/eryihan/smart_test/tree/main/skills/smart-test 更新已安装的 smart-test。
替换前检查本地版本和本地修改，有修改时先报告。
```

卸载时删除已安装的 `smart-test` skill 目录。卸载不会删除目标 Java 仓库中的测试代码和 `.smart-test/`。

## 10. 常见问题

### 找不到 skill

Codex：确认 `skill-installer` 报告安装成功，开启新会话后调用 `$smart-test`。

Claude Code：执行 `claude plugin list`，确认 `smart-test@smart-test` 为 enabled；必要时运行 `/reload-plugins`，然后使用 `/smart-test:smart-test`。

### 集成测试环境暂时不可用

可以继续执行不依赖外部服务的 Unit 和其他已具备环境的测试。需要真实数据库或中间件时，提供经过确认的隔离测试实例；环境不可用会报告阻塞，不会用 mock 或跳过测试代替通过。

### 是否会修改生产代码或正式 CI

生产代码和正式 CI 属于高影响修改，需要业务依据、测试证据和明确授权。默认输出建议或 patch，不为使测试通过而改变业务期望。

### 没有业务文档

对于需要保护现有行为的重构，可以生成 characterization test，并明确标记它不代表业务正确性。已知业务冲突或高风险歧义仍需人工确认。

### 如何验证项目状态

```text
$smart-test check
```

需要查看决策来源时，直接描述：

```text
查看当前 smart_test 状态。
解释这个测试决策的依据和失效原因。
列出当前待确认的方案。
```

## 11. 使用问题反馈

发现策略错误、误判、越权或漏测时，可在当前对话中请求导出脱敏反馈，并指定目标项目之外的新目录。smart_test 使用内部辅助脚本读取已有产物，只导出固定字段摘要，不修改项目、不执行测试、不访问网络、不上传数据。源码、完整 diff、原始路径、业务文本和凭证不会被复制到反馈包。

导出包记录 smart_test 版本、可获得的 commit、宿主、工作入口和导出时间。人工复核后，自行带回本仓库，按 [反馈处理流程](feedback/README.md) 创建 case，追踪根因、修复和 regression case。具体参数与省略规则见 [本地导出说明](skills/smart-test/references/feedback.md)。这些操作属于现有工作入口，不增加新的工作模式。

## 12. 许可证与维护者资料

本项目采用 [Apache License 2.0](LICENSE)。开发架构、验收记录和本地发布说明属于维护者资料，保留在源码工作区的 `docs/` 目录，不作为用户安装内容。

安装机制参考 [Claude Code 插件安装](https://code.claude.com/docs/en/plugins/install)、[Claude Code 插件市场](https://code.claude.com/docs/en/plugin-marketplaces) 和 [OpenAI 官方 skill-installer](https://github.com/openai/skills/tree/main/skills/.system/skill-installer)。
