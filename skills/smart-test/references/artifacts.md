# 按需产物与校验

按复用、恢复、审计或运行证据需要保存产物。局部任务可在对话中记录风险、依据和测试边界；持久化方式不改变业务依据、授权及质量门要求。

## 保存什么

| 信息 | 何时保存 | 现有兼容格式 |
|---|---|---|
| 长期约定 | 用户要求记住或后续确有复用价值；先引用仓库已有配置 | test-policy.json；已有 strategy/profile/Oracle 继续使用 |
| 任务计划 | 多模块分批实施、跨会话恢复、用户要求保存 | test-plan.json；需要债务清单时 test-debt.json/md |
| 运行证据 | 实际执行后记录；未执行只报告 NOT_RUN/BLOCKED | runs/<run-id>/manifest.json、报告快照与报告摘要 |
| 阶段摘要 | 需要恢复或审计任务进度 | status.json；语义见 verification |
| 治理记录 | 决策依赖、范围生命周期、解释或审计需求 | state.json、effective-context.json；见 governance |
| CI 候选 | 用户要求接入 CI | ci-candidate/；验证状态分开记录，见 ci |

新任务优先使用 test-policy 保存长期约定、test-plan 条目内保存断言依据。仅当业务依据或策略需要独立复用时拆成单独文件。不要把同一条事实复制到多个文件；引用原文件与版本。已有文件不删除、不强制迁移；冲突先查证，不因采用新流程忽略旧约束。

status 是证据的派生视图。需要持久化时引用实际 run ID 和计划范围，结果变化后重算相关状态；不能手工改 PASS 来替代运行或解除业务阻塞。

## 存储位置

按需使用以下目录：

```text
.smart-test/
  repository-evidence.json     # 静态候选证据，尚需 Agent 复核
  project-profile.json         # 已核实画像
  business-oracle.json         # 独立复用的业务依据
  test-strategy.json           # 独立复用的策略；局部任务可用 policy/计划表达
  test-policy.json             # 长期测试约定
  test-debt.json               # 按需债务清单，也可用 Markdown
  test-plan.json               # 可恢复计划
  state.json                  # 可选指令、决策、授权事件账本
  effective-context.json       # 按需生效约束及来源
  status.json                  # 阶段进度与运行证据的派生摘要
  runs/<run-id>/manifest.json  # 实际运行记录及报告快照
  reports/                    # 可读报告
  ci-candidate/               # CI 候选与分项验证记录
```

JSON 使用 UTF-8。不要保存秘密和未经清洗的可共享日志；检查项目 ignore 约定，区分需要共享的 policy/计划与临时运行报告，不擅自改 Git 全局配置。证据引用路径、版本或用户陈述来源。模板字段须由实际证据替换。

## 什么时候校验

- 本次准备消费已有结构化计划/约束，或交付新生成的已知 JSON 时，按实际文件调用 `validate_artifacts.py --repo <repo> --require <文件名>`；多个依赖重复 `--require`。只检查本次任务依赖的文件。
- 缺失已被明确引用的文件是错误；未使用的可选文件缺失不阻断任务。effective context 引用了 directive/decision ID 时需要 state.json；没有引用就不要求账本。
- 结构错误先修复并重验，不能据此实施依赖该产物的动作或声称其有效；不受影响的工作继续。缺业务依据时如实保存 BLOCKED/UNKNOWN，不能编造依据、删掉 required 项或移除真实 blocker 来通过校验。
- 结构与引用校验、业务判断、授权核验和测试验证分别进行。合法的 BLOCKED 计划可以交付；阻塞影响设计、实施还是执行，按 [verification.md](verification.md#受阻工作) 区分，不由格式校验决定。
- 对话内计划不强制落盘校验。help/dry-run 不创建文件或锁；dry-run 可以只读校验已有输入。

退出码：0 为 VALID，1 为 INVALID，2 为输入错误。不带 `--require` 时仅检查已存在的已知文件，不能证明任务所需文件齐备。

## 最小结构

所有 JSON 顶层为对象。示例中的 `example_only: true` 会被拒绝；移除标志前必须用实际证据替换内容。

- **business-oracle.json**：支持单条依据，或 entries/items/claims/oracle 数组。已知依据必须有布尔 business_truth、非空 source 与 claim。characterization 使用 `business_truth: false`，source 引用当前版本/观察，claim 说明观察行为；Agent 仍需核对其适用风险。暂缺依据用 `{"status":"UNKNOWN","reason":"具体缺失事实"}` 表达，不能用空对象充当已知依据。
- **test-plan.json**：支持顶层 items 或 test_plan.items。每项 required 是布尔值；必需项包含非空 id、target、risk、suite、字符串断言列表和上述 oracle。未知依据只允许与该项 `status: BLOCKED`、非空 blocking_ids 同时使用，断言可为空；阻塞解除前不得执行依赖该预期的动作。省略 status 的既有有效计划仍兼容。
- **test-policy.json**：至少含 required_suites、verification、environment、coverage、production_change_boundary、production_code_modify 中一个字段。前者是非空字符串或带 suite 名称对象的数组；中间四项为对象，最后一项为布尔。coverage 的已提供字段按 [coverage.md](coverage.md) 校验，不补默认业务含义。
- **effective-context.json**：支持直接对象或 effective_context 包装；至少提供 scope、constraints、directive_ids、decision_ids、conflicts、unresolved 中一项。ID 列表必须为非空字符串，实际引用必须存在，directive 为 ACTIVE、decision 为 EFFECTIVE 且证据未失效；生命周期、scope 语义和最终授权仍由 Agent 核对。
- **status.json**：支持顶层 status、`stages: {阶段名: 状态对象}`，也兼容旧的顶层阶段对象。阶段对象可记录 artifact、blocking_ids、decision_ids、updated_at；只有实际引用决策时才需要账本。状态含义见 [verification.md](verification.md#阶段结果)，不要求创建 state.json 才能保存阶段结果。blocking_ids/blockers 必须为数组；任何阶段的 PASS 都不能带 blocker；汇总 PASS 不能掩盖子阶段未完成或受阻。

可选字段无需补齐，扩展字段可保留。Agent 核对业务预期、命令、环境隔离和风险覆盖。

## 运行 manifest

结构示例见 [run-manifest.example.json](../assets/run-manifest.example.json)。真实记录使用 `schema_version: 1`，移除 `example_only`；包含非空 `runs` 和 `required_run_ids`。Agent 还记录实际工作目录、Git HEAD、工作树指纹与执行环境，并核对它们对应本次代码。这些元数据由 Agent 核验。

- 每个 run：唯一 `id`、实际脱敏 `argv`、带时区的 `started_at`/`finished_at`、整数 `exit_code`、报告分组。`kind` 默认 test；compile/build 不需 JUnit 时设置 `requires_test_report: false`，编译成功仍不能替代必需测试。
- 每个 reports group：仓库内精确 `pattern`、`required`、正整数 `min_tests`（默认 1）、`allow_skipped`（默认 false）；需要特定测试时声明 XML 中的 `classname#name` 为 `expected_test_ids`。必需套件按模块分组，避免一个模块掩盖另一个未执行。
- `blockers` 记录尚未解决的事项；存在 blocker 时汇总结果不得为 PASS。未执行的命令只报告 NOT_RUN/BLOCKED，不填写预计退出码或伪造完成记录。

manifest 与 JUnit 执行窗口由 `collect_reports.py` 检查，不属于 `validate_artifacts.py` 的五类项目 JSON 校验。运行、快照与结果判断见 [verification.md](verification.md)。
