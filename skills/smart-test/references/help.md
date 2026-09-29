# smart_test 帮助

`help` 模式读取本文件，按用户问题返回相关部分；没有指定主题时先介绍入口和推荐流程。`help` 只读：不扫描项目、不运行构建、不修改文件。

## 调用方式

Codex：

```text
$smart-test help
$smart-test help coverage
```

Claude Code：

```text
/smart-test:help
/smart-test:init
/smart-test:scan
/smart-test:changes
/smart-test:check
/smart-test:pipeline
/smart-test:smart-test help
/smart-test:smart-test help pipeline
```

Claude Code 插件将六种模式注册为 slash command；原有 `/smart-test:smart-test <模式>` 仍兼容。Codex 和独立安装使用单一 skill 入口，在入口后指定模式或直接描述任务。

也可以直接提问，例如“smart_test 如何判断增量覆盖率？”或“我只想查看当前改动，不执行测试”。

## 工作入口

| 入口 | 用途 | 默认行为 |
|---|---|---|
| `help` | 查看入口、参数、产物和边界 | 只读，不写文件，不执行构建 |
| `init` | 建立项目画像、业务依据、测试策略和质量门 | 显式搭建测试体系时使用；按授权补设施 |
| `scan` | 扫描现有测试缺口并排序 | 默认分析全仓，不一次性补完历史债务 |
| `changes` | 分析当前变更并补充相关测试 | 读取工作树、staged 或指定基线的变更 |
| `check` | 执行测试、收集报告、判断验证结果 | 只执行已有构建配置能证明的测试 |
| `pipeline` | 生成并检查 CI 候选，区分草稿与已验证结果 | 默认输出候选和 patch，不直接改正式 CI |

按任务直接选择：补当前改动用 `changes`，运行验证用 `check`，了解存量缺口用 `scan`，搭建测试体系用 `init`，接入 CI 用 `pipeline`。普通任务不要求先 init。`pipeline verify` 和 `pipeline finalize` 是 pipeline 内的阶段。

## 常用控制项

- `--dry-run`：只分析并展示计划，不创建状态、不改代码、不执行构建或启动服务。
- `--staged`：只分析暂存区变更。
- `--base <ref>`：以指定分支或提交的共同祖先分析到当前工作树。
- `--fast`：执行当前风险所需的最小充分验证集；不能据此声称全量验证通过。
- `--full`：扩大到相关模块或完整验证集；不自动引入项目没有要求的工具。
- `--strict`：逐阶段展示本次任务涉及的画像、策略和计划；不强制创建无关产物。
- `--auto`：复用既有约定和授权继续处理；新重大选择超出授权或出现业务歧义时，说明具体待定事项。

控制项由 Agent 解释执行，不是系统 CLI 参数；与用户明确要求冲突时以用户要求为准并说明影响。

## 覆盖率

覆盖率可不指定。未指定时不新增工具、数字阈值或阻断条件，仓库已有门禁仍然适用。在 `init`、`changes` 或 `check` 中说明：

- 只报告覆盖率，不设置阻断阈值；
- 指定某个模块或仓库的整体行覆盖率阈值；
- 以某个分支、提交或 merge-base 为基线，指定增量行覆盖率阈值；
- 同时要求整体和增量覆盖率。

整体覆盖率按可执行项总数汇总；增量覆盖率只计算新增或修改的可执行代码行。没有可执行变更行记为 `NOT_APPLICABLE`；基线、源码映射或报告不可靠记为 `UNKNOWN`。`--fast`、`--full` 只改变测试执行范围，不改变覆盖率模式。详细规则见 [coverage.md](coverage.md)。

## 结果和产物

结果区分 `PASS`、`PARTIAL`、`BLOCKED`、`NOT_VERIFIED`、`UNKNOWN` 和 `NOT_APPLICABLE`：测试未执行、报告陈旧、环境不可用或业务依据不明确的，不报告完整通过。

局部任务直接说明风险与依据、补测试并验证，不创建治理账本或计划 JSON。实际执行保留运行证据；复用约定、跨会话恢复或审计时才增加持久产物。既有适用约束仍须遵守。

消费或生成已知结构化产物时，按实际依赖校验，不要求补齐整套文件。结构问题只阻断依赖它的工作；合法的 BLOCKED 计划可以交付，但不执行受阻项。规则见 [按需产物与校验](artifacts.md)。

持久化信息写入 `.smart-test/`，原有格式继续支持，不强制迁移。常见文件：

- `project-profile.json`：已核实的技术栈和项目结构；
- `business-oracle.json`：业务依据、冲突和未知项；
- `test-policy.json`：长期测试约定、覆盖率和质量门；独立复用时也可保存 test-strategy.json；
- `test-plan.json`、`test-debt.json`：测试计划与缺口；
- `runs/`、`reports/`：实际命令、JUnit/coverage 报告和失败归因；
- `ci-candidate/`：CI 草稿或已验证候选、验证说明和建议 patch。

没有本地集成环境时可生成待验证 CI 草稿，保留未运行套件、Runner 前提和 NOT_RUN/NOT_VERIFIED 标记。finalize 仍要求本地或等价 CI 环境的完整执行证据和候选检查。

长期约束、决策依赖或审计使用可选的 state.json 账本。文件变化先复核；决策和原授权仍适用的保留授权，技术选择或用户要求变化则重评相关部分。

状态文件不应写入密码、Token、生产连接信息或真实个人数据。测试代码放在目标项目已有的测试目录中。

## 测试边界

先复用项目已有的框架、版本和构建命令。Unit 可在没有外部服务时执行；数据库、Redis、消息队列和远程服务需要隔离环境。环境不可用时保留阻塞原因，不用 mock、替代数据库或跳过测试伪造通过。

业务规则必须有可追溯依据。当前实现只说明现状，不自动成为正确答案；业务冲突、高风险歧义、生产代码修改和正式 CI 修改需要明确证据与授权。

## 典型请求

```text
$smart-test init --dry-run
$smart-test scan
$smart-test changes --base origin/main
$smart-test check --fast
$smart-test pipeline
```

也可以用自然语言描述范围，例如“只检查 order 模块”“不要修改生产代码”“本轮只生成计划”“本次只报告覆盖率”。

## 反馈

发现策略错误、误判或范围问题时，在当前对话中要求导出本地脱敏反馈，并指定项目外的新目录。按 [本地反馈导出](feedback.md) 处理，不自动上传；反馈包不含源码和原始业务描述，人工复核后带回 smart_test 仓库追踪修复与回归。仅查看帮助不执行导出。
