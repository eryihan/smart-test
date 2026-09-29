# Smart-Test 使用说明

Smart-Test 是一个面向 Java / Spring Boot 仓库的测试工程 skill。它会读取仓库结构、业务依据、现有测试和当前变更，形成测试策略，补充测试，执行验证，并生成经过验证的 CI 候选方案。

当前版本主要支持 Java 8+、Spring Boot 2/3、Maven 和 Gradle。数据库、Redis、消息队列和远程服务测试需要相应的隔离环境；环境不可用时，Smart-Test 会标记阻塞并保留可执行的部分。

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

本仓库提供的是第三方 Claude Code 市场，不代表已收录到 Anthropic 官方市场。

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

## 3. 第一次接入项目

在目标 Java 仓库根目录启动 Codex 或 Claude Code，然后执行 `init`：

```text
Codex:   $smart-test init
Claude:  /smart-test:smart-test init
```

Smart-Test 按以下顺序处理：

1. 识别语言、JDK、Maven/Gradle、模块和 Spring Boot 版本。
2. 检查数据库、缓存、消息队列、远程客户端、安全配置、迁移脚本和 CI。
3. 读取现有测试、业务文档、接口协议和 schema，建立可追溯的业务依据。
4. 形成项目画像、测试策略和缺失基础设施清单。
5. 对新的关键技术选择或高风险业务规则给出 proposal，等待必要的确认。
6. 在已授权范围内补充测试设施和最小有效测试，并执行验证。

只查看分析结果，不创建状态文件、不修改代码、不执行构建时，使用：

```text
$smart-test init --dry-run
```

首次接入时建议同时给出边界，例如：

```text
允许修改测试代码、测试资源和测试相关构建配置；禁止修改生产代码。
数据库测试禁止使用 Docker；没有隔离测试实例时报告阻塞原因。
本次只处理 order 模块。
```

## 4. 五个工作模式

| 命令 | 用途 | 主要产物 |
|---|---|---|
| `init` | 建立项目画像和测试策略 | 项目画像、业务依据、测试策略、测试 policy |
| `scan` | 扫描存量代码和测试缺口 | 风险地图、测试债务、治理顺序 |
| `changes` | 分析当前变更并补充测试 | 影响分析、测试计划、测试代码、验证结果 |
| `check` | 执行测试并判断结果 | 执行记录、测试报告、失败归因 |
| `pipeline` | 生成并检查 CI 候选方案 | CI candidate、验证记录、正式 CI 建议补丁 |

这些是 skill 的工作模式，由 Agent 根据请求执行，不是需要在系统终端安装的命令行程序。也可以直接描述任务，Agent 会选择对应模式：

```text
扫描这个项目的测试缺口
检查当前改动并补测试
执行必要验证并分析失败原因
生成已验证的 CI 候选方案
```

## 5. 日常流程

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

`--staged` 只分析暂存区；`--base` 从指定分支与当前 HEAD 的共同祖先分析到当前工作树。分析完成后，Smart-Test 会将变更映射到模块、调用方、数据库、接口和业务风险，再形成测试计划。

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

Smart-Test 会记录实际命令、退出码、测试数量、失败、跳过、耗时和报告路径。必需测试未执行、报告陈旧、环境阻塞或存在未解决业务歧义时，不会报告完整验证通过。

### 5.4 生成 CI 候选方案

完成所需本地验证后执行：

```text
$smart-test pipeline
```

Smart-Test 先生成 `.smart-test/ci-candidate/`，再检查：

1. CI 中的命令是否与本地已验证命令一致。
2. Unit、Integration、Contract 和关键流程是否被正确纳入。
3. 测试失败是否返回非零退出码。
4. 测试报告路径、Runner 能力、Docker/网络要求是否明确。
5. Secret 是否通过 CI Secret 或环境变量引用，是否存在硬编码凭证。

检查候选方案：

```text
$smart-test pipeline verify
```

验证通过后生成正式 CI 建议补丁：

```text
$smart-test pipeline finalize
```

`finalize` 默认输出可审阅的 patch，不直接覆盖正式 CI。正式修改需要明确授权。

## 6. 指定约束和业务依据

可以在任意阶段补充约束。建议明确写出范围、强度和生命周期：

```text
只处理 order 模块，本轮不治理历史测试债务。
数据库测试必须使用 PostgreSQL 16，不允许用 H2 替代。
审批拒绝后的状态必须是 REJECTED，业务依据是 docs/approval.md。
本轮不要运行集成测试，只列出未验证风险。
优先使用项目已有的 AssertJ 风格。
```

Smart-Test 会区分：

- **业务事实**：进入业务依据，用于决定正确结果和断言。
- **技术约束**：限制测试框架、数据库、容器和构建方式。
- **范围约束**：限制模块、路径、测试类型或本次变更。
- **执行约束**：限制是否写代码、是否运行测试、是否修改生产代码。
- **偏好**：在没有冲突时作为选择依据。

新的约束如果改变已有决策的前提，Smart-Test 会使受影响的策略、计划或 CI candidate 失效，并重新计算相关部分。

常用控制项：

| 控制项 | 行为 |
|---|---|
| `--dry-run` | 只读分析，不写仓库文件、不执行构建、不启动服务 |
| `--strict` | 对新的关键策略和计划逐阶段展示 |
| `--auto` | 复用已确认的策略和授权，自动处理普通变更；遇到新高风险选择时暂停 |

## 7. 项目产物

Smart-Test 将项目记忆和报告写入目标仓库的 `.smart-test/`：

| 路径 | 内容 |
|---|---|
| `state.json` | 用户约束、决策、授权来源和失效记录 |
| `project-profile.json` | 已核实的项目画像和证据 |
| `business-oracle.json` | 业务依据、冲突和未知项 |
| `effective-context.json` | 当前阶段生效的范围和约束 |
| `test-strategy.json` / `test-policy.json` | 测试层级、技术选择和质量要求 |
| `test-plan.json` / `test-debt.json` | 测试计划和测试债务 |
| `status.json` | 各阶段状态和阻塞项 |
| `runs/` / `reports/` | 执行记录、测试报告和失败分析 |
| `ci-candidate/` | CI 候选文件和建议补丁 |

文件按流程逐步生成，不会一次创建全部产物。测试代码写入项目现有测试目录。不要把凭证、生产连接信息或真实敏感数据写入 `.smart-test/`。

## 8. 更新和卸载

### 8.1 Claude Code

```bash
claude plugin marketplace update smart-test
claude plugin update smart-test@smart-test
```

更新后重新加载插件或开启新会话。卸载：

```bash
claude plugin uninstall smart-test@smart-test
```

项目级操作增加 `--scope project`。

### 8.2 Codex

在 Codex 中发送：

```text
请从 https://github.com/eryihan/smart_test/tree/main/skills/smart-test 更新已安装的 smart-test。
替换前检查本地版本和本地修改，有修改时先报告。
```

卸载时删除已安装的 `smart-test` skill 目录。卸载不会删除目标 Java 仓库中的测试代码和 `.smart-test/`。

## 9. 常见问题

### 找不到 skill

Codex：确认 `skill-installer` 报告安装成功，开启新会话后调用 `$smart-test`。

Claude Code：执行 `claude plugin list`，确认 `smart-test@smart-test` 为 enabled；必要时运行 `/reload-plugins`，然后使用 `/smart-test:smart-test`。

### 没有 Docker

可以继续执行 Unit 和不依赖容器的测试。需要真实数据库或中间件时，提供经过确认的隔离测试实例；没有可用环境时会报告阻塞，不会使用 mock 或跳过测试代替通过。

### 是否会修改生产代码或正式 CI

生产代码和正式 CI 属于高影响修改，需要业务依据、测试证据和明确授权。默认输出建议或 patch，不为使测试通过而改变业务期望。

### 没有业务文档

对于需要保护现有行为的重构，可以生成 characterization test，并明确标记它不代表业务正确性。已知业务冲突或高风险歧义仍需人工确认。

### 如何验证项目状态

```text
$smart-test check
```

查看决策来源：

```text
$smart-test status
$smart-test explain
$smart-test approval list
```

## 10. 维护者资料

开发架构、验收记录和本地发布说明属于维护者资料，保留在源码工作区的 `docs/` 目录，不作为用户安装内容。

安装机制参考 [Claude Code 插件安装](https://code.claude.com/docs/en/plugins/install)、[Claude Code 插件市场](https://code.claude.com/docs/en/plugin-marketplaces) 和 [OpenAI 官方 skill-installer](https://github.com/openai/skills/tree/main/skills/.system/skill-installer)。
