# 按需产物与校验

持久化只服务于复用、恢复、审计或实际执行证据。小任务在对话中说明风险、依据和测试选择，不为流程创建空文件。业务依据、范围、授权、必需测试和质量门的判断不因是否落盘而改变。

## 保存什么

| 信息 | 何时保存 | 现有兼容格式 |
|---|---|---|
| 长期约定 | 用户要求记住或后续确有复用价值；先引用仓库已有配置 | test-policy.json；已有 strategy/profile/Oracle 继续使用 |
| 任务计划 | 多模块分批实施、跨会话恢复、用户要求保存 | test-plan.json；需要债务清单时 test-debt.json/md |
| 运行证据 | 实际执行后记录；未执行只报告 NOT_RUN/BLOCKED | runs/<run-id>/manifest.json、报告快照与报告摘要 |
| 治理记录 | 决策依赖、范围生命周期、解释或审计需求 | state.json、effective-context.json、status.json；见 governance |
| CI 候选 | 用户要求接入 CI | ci-candidate/；验证状态分开记录，见 ci |

新任务优先使用 test-policy 保存长期约定、test-plan 条目内保存断言依据。仅当业务依据或策略需要独立复用时拆成单独文件。不要把同一条事实复制到多个文件；引用原文件与版本。已有文件不删除、不强制迁移；冲突先查证，不因采用新流程忽略旧约束。

status 是证据的派生视图。需要持久化时引用实际 run ID 和计划范围，结果变化后重算相关状态；不能手工改 PASS 来替代运行或解除业务阻塞。

## 什么时候校验

- 本次准备消费已有结构化计划/约束，或交付新生成的已知 JSON 时，按实际文件调用 `validate_artifacts.py --repo <repo> --require <文件名>`；多个依赖重复 `--require`。只检查本次任务依赖的文件。
- 缺失已被明确引用的文件是错误；未使用的可选文件缺失不阻断任务。effective context 引用了 directive/decision ID 时需要 state.json；没有引用就不要求账本。
- 结构错误先修复并重验，不能据此实施依赖该产物的动作或声称其有效；不受影响的工作继续。缺业务依据时如实保存 BLOCKED/UNKNOWN，不能编造依据、删掉 required 项或移除真实 blocker 来通过校验。
- 校验通过只说明结构与显式引用一致，不证明业务正确、授权充分或测试通过。合法的 BLOCKED 计划可以交付，但不实施其受阻条目。
- 对话内计划不强制落盘校验。help/dry-run 不创建文件或锁；dry-run 可以只读校验已有输入。

退出码：0 为 VALID，1 为 INVALID，2 为输入错误。不带 `--require` 时仅检查已存在的已知文件，不能证明任务所需文件齐备。

## 最小结构

所有 JSON 顶层为对象。示例中的 `example_only: true` 会被拒绝；移除标志前必须用实际证据替换内容。

- **business-oracle.json**：支持单条依据，或 entries/items/claims/oracle 数组。已知依据必须有布尔 business_truth、非空 source 与 claim。characterization 使用 `business_truth: false`，source 引用当前版本/观察，claim 说明观察行为；Agent 仍需核对其适用风险。暂缺依据用 `{"status":"UNKNOWN","reason":"具体缺失事实"}` 表达，不能用空对象充当已知依据。
- **test-plan.json**：支持顶层 items 或 test_plan.items。每项 required 是布尔值；必需项包含非空 id、target、risk、suite、字符串断言列表和上述 oracle。未知依据只允许与该项 `status: BLOCKED`、非空 blocking_ids 同时使用，断言可为空；这允许交付真实阻塞计划，不能解除阻塞。省略 status 的既有有效计划仍兼容。
- **test-policy.json**：至少含 required_suites、verification、environment、coverage、production_change_boundary、production_code_modify 中一个字段。前者是非空字符串或带 suite 名称对象的数组；中间四项为对象，最后一项为布尔。coverage 的已提供字段按 [coverage.md](coverage.md) 校验，不补默认业务含义。
- **effective-context.json**：支持直接对象或 effective_context 包装；至少提供 scope、constraints、directive_ids、decision_ids、conflicts、unresolved 中一项。ID 列表必须为非空字符串，实际引用必须存在，directive 为 ACTIVE、decision 为 EFFECTIVE 且证据未失效；生命周期、scope 语义和最终授权仍由 Agent 核对。
- **status.json**：支持顶层 status、`stages: {阶段名: 状态对象}`，也兼容旧的顶层阶段对象。status 使用治理文档中的阶段状态及 NOT_VERIFIED/UNKNOWN/NOT_APPLICABLE/NOT_RUN。blocking_ids/blockers 必须为数组；任何阶段的 PASS 都不能带 blocker；汇总 PASS 不能掩盖子阶段未完成或受阻。实际 run、风险断言和质量门仍按 verification 检查。

未使用的可选字段不要求补齐，扩展字段可保留。业务预期、命令选择、环境隔离和风险是否充分，不能由这些字段是否存在决定。
