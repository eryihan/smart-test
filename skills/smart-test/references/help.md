# Smart-Test 帮助

本文件是 `help` 模式使用的用户帮助。调用 `help` 时读取本文件，根据用户的问题只返回相关部分；没有指定主题时先介绍入口和推荐流程。`help` 只读，不扫描项目、不运行构建、不修改文件。

## 调用方式

Codex：

```text
$smart-test help
$smart-test help coverage
```

Claude Code：

```text
/smart-test:smart-test help
/smart-test:smart-test help pipeline
```

也可以直接提问，例如“Smart-Test 如何判断增量覆盖率？”或“我只想查看当前改动，不执行测试”。Agent 会按同一帮助内容回答。

## 工作入口

| 入口 | 用途 | 默认行为 |
|---|---|---|
| `help` | 查看入口、参数、产物和边界 | 只读，不写文件，不执行构建 |
| `init` | 建立项目画像、业务依据、测试策略和质量门 | 首次接入；根据授权补测试基础设施 |
| `scan` | 扫描现有测试缺口并排序 | 默认分析全仓，不一次性补完历史债务 |
| `changes` | 分析当前变更并补充相关测试 | 读取工作树、staged 或指定基线的变更 |
| `check` | 执行测试、收集报告、判断验证结果 | 只执行已有构建配置能证明的测试 |
| `pipeline` | 从已验证命令生成、检查 CI 候选 | 默认输出候选和 patch，不直接改正式 CI |

正式入口仅为表中的六项，不提供命令别名。自然语言请求由 Agent 映射到相应入口；`pipeline verify` 和 `pipeline finalize` 是 pipeline 内的阶段。

推荐顺序是：首次接入使用 `init`，了解缺口使用 `scan`，提交前使用 `changes` 和 `check`，需要接入 CI 时使用 `pipeline`。只想了解规则或参数时使用 `help`。

## 常用控制项

- `--dry-run`：只分析并展示计划，不创建状态、不改代码、不执行构建或启动服务。
- `--staged`：只分析暂存区变更。
- `--base <ref>`：以指定分支或提交的共同祖先分析到当前工作树。
- `--fast`：执行当前风险所需的最小充分验证集；不能据此声称全量验证通过。
- `--full`：扩大到相关模块或完整验证集；不自动引入项目没有要求的工具。
- `--strict`：逐阶段展示新的画像、策略和计划，便于审阅。
- `--auto`：复用已经确认的策略处理普通变更；遇到新重大选择时暂停并说明原因。

这些控制项是 Agent 的工作范围，不是需要另行安装的系统 CLI 参数。若参数与用户明确要求冲突，以用户要求为准并说明影响。

## 覆盖率

覆盖率可以不指定。未指定时不新增 Smart-Test 工具、数字阈值或阻断条件，但仓库已有门禁仍然适用。用户可以在 `init`、`changes` 或 `check` 中说明：

- 只报告覆盖率，不设置阻断阈值；
- 指定某个模块或仓库的整体行覆盖率阈值；
- 以某个分支、提交或 merge-base 为基线，指定增量行覆盖率阈值；
- 同时要求整体和增量覆盖率。

整体覆盖率按可执行项总数汇总；增量覆盖率只计算新增或修改的可执行代码行。没有可执行变更行记为 `NOT_APPLICABLE`；基线、源码映射或报告不可靠记为 `UNKNOWN`。`--fast`、`--full` 只改变测试执行范围，不改变覆盖率模式。详细规则见 [coverage.md](coverage.md)。

## 结果和产物

Smart-Test 会区分 `PASS`、`PARTIAL`、`BLOCKED`、`NOT_VERIFIED`、`UNKNOWN` 和 `NOT_APPLICABLE`，不会把测试未执行、报告陈旧、环境不可用或业务依据不明确报告为完整通过。

关键产物的结构校验由 Smart-Test 在流程内部执行，不需要用户单独调用。校验失败时先修复并重验，再进入下一阶段；结构合法不代表测试通过。

项目状态和报告写入目标仓库的 `.smart-test/`，常见文件包括：

- `project-profile.json`：已核实的技术栈和项目结构；
- `business-oracle.json`：业务依据、冲突和未知项；
- `test-strategy.json`、`test-policy.json`：测试层级、覆盖率和质量门；
- `test-plan.json`、`test-debt.json`：测试计划与缺口；
- `runs/`、`reports/`：实际命令、JUnit/coverage 报告和失败归因；
- `ci-candidate/`：经过本地验证的 CI 候选和建议 patch。

状态文件不应写入密码、Token、生产连接信息或真实个人数据。测试代码放在目标项目已有的测试目录中。

## 测试边界

Smart-Test 先复用项目已有的框架、版本和构建命令。Unit 可以在没有外部服务时执行；数据库、Redis、消息队列和远程服务需要相应的隔离环境。环境不可用时保留阻塞原因，不用 mock、替代数据库或跳过测试伪造通过。

业务规则必须有可追溯依据。当前实现只能说明现状，不能自动成为正确答案；业务冲突、高风险歧义、生产代码修改和正式 CI 修改都需要明确说明证据与授权。

## 典型请求

```text
$smart-test init --dry-run
$smart-test scan
$smart-test changes --base origin/main
$smart-test check --fast
$smart-test pipeline
```

也可以用自然语言描述范围，例如“只检查 order 模块”“不要修改生产代码”“本轮只生成计划”“本次只报告覆盖率”。
