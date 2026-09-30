# 真实项目反馈与回归

维护经人工复核的使用反馈。原始业务资料、导出包和运行日志不进入 Git；`cases/` 只保存脱敏后的问题记录，`templates/feedback-template.md` 提供统一模板。EXAMPLE 为合成示例，未发生真实反馈或修复。

## 1. 在问题现场导出

发现误判、越权、策略错误或漏测后，先保留现场，不为了获得 PASS 改写期望或删除 blocker。尽量在升级 smart_test 前导出。导出方法见随安装包提供的 [反馈导出说明](../skills/smart-test/references/feedback.md)。

导出包只保存固定枚举、计数和匿名文件编号。业务语义、原始断言和源码不会导出，定位时可能需要补充合成案例。不要为获得更多上下文取消字段白名单或将原始日志、源码粘贴进 case。

## 2. 创建 feedback case

1. 人工检查导出包，确认没有可识别企业、项目或人员的信息，再自行带回本仓库。需要本地暂存时使用被 Git 忽略的 `feedback/imports/`，不要提交整包。
2. 复制模板到 `feedback/cases/<id>.md`，沿用 `feedback.json` 中的 id，记录 metadata 中的版本、宿主、工作入口、导出时间及可获得的 commit。
3. 用合成模块、合成数据和中性名称描述 scenario、actual_behavior、expected_behavior。不要填真实人名、内部地址、账号或类名。导出包中为空的描述字段由人工补充，不能假定空值表示没有问题。
4. 为 expected_behavior 附上依据：已确认的 smart_test 规则、用户明确要求或可靠测试工程事实。当前 Agent 输出只作为 actual_behavior，不能反推为正确期望。

每个 case 至少包含：`id`、`date`、`smart_test_version`、`host`、`workflow`、`feedback_type`、`scenario`、`actual_behavior`、`expected_behavior`、`root_cause`、`fix`、`regression_case`、`status`。未知值显式记录 UNKNOWN 或 null，不能猜测。

`feedback_type` 只选以下一种，必要时在场景中说明次要问题：

| 类型 | 含义 |
|---|---|
| FALSE_PASS | 未满足验证条件却报告通过 |
| FALSE_BLOCKED | 已有充分条件却误报阻塞 |
| WRONG_STRATEGY | 测试层级、范围或方法选错 |
| WRONG_SCOPE | 超出或遗漏约定范围 |
| ORACLE_ERROR | 业务依据来源或正确性判断错误 |
| DIRECTIVE_IGNORED | 未遵守用户明确要求 |
| MISSING_CAPABILITY | 缺少完成任务所需能力 |
| UX_CONFUSION | 入口、解释或交互引起误解 |
| PERFORMANCE | 分析或执行成本不合理 |
| OTHER | 其他问题，需具体说明 |

## 3. 定位根因并修复

```text
真实项目使用 → 发现异常 → 本地脱敏导出 → 人工创建 case
→ 判断根因层级 → 修复 Skill / reference / helper / grader
→ 增加 regression test / behavioral eval → 重新验证 → 关闭 case
```

按证据定位根因与修改位置：

| root_cause | 优先检查的位置 |
|---|---|
| SKILL_RULE | SKILL.md 的入口、共用约束或路由 |
| REFERENCE_RULE | 对应 reference 的策略和流程规则 |
| HELPER_IMPLEMENTATION | Python helper 的确定性实现 |
| ARTIFACT_VALIDATION | 产物结构、缺失字段或 gate |
| GRADER | 评测判定逻辑；当前人工或宿主 grader 的检查依据 |
| HOST_VARIANCE | Codex / Claude Code 宿主执行或加载差异 |
| FIXTURE | 复现场景、环境或证据本身不正确 |
| UNKNOWN | 证据不足，列出还缺什么 |

记录具体规则、触发条件和失败证据。`fix` 写修改文件、修改原因和可追溯的 diff/commit（可获得时），不能只写“优化提示词”。判定错误须记录人工或宿主 grader 的检查方法。

## 4. 转为 regression case

- helper 或 artifact validator 的错误：优先增加可重复的单元测试，先证明修复前失败，再证明修复后通过。
- Agent 的策略、权限或判断错误：在 `evals/evals.json` 增加或扩展场景，记录合成 fixture、用户请求和可观察断言。已有场景能覆盖时复用 ID，避免重复。
- 检查实际工具调用、文件 diff、结构化产物和最终结论，核对行为与证据。每个 case 记录对应测试函数或 eval ID、修复前后结果、宿主与版本、结果记录位置。
- 无法可靠自动化时，在 `regression_case` 中记录原因、人工复核步骤、证据和局限，不制造恒绿测试。未运行的评测记 NOT_RUN；缺少证据记 UNKNOWN。

**禁止为了让错误 Agent 行为通过而放宽 expectation。** 只有设计原则或用户要求确实改变，或有证据证明原 expectation 错误时，才能单独审阅并修改期望，同时在 case 记录依据。修复 grader 也必须遵守这一要求。

## 5. 验证与关闭

状态只使用 `OPEN / FIXED / CLOSED`：OPEN 表示待定位或处理；FIXED 表示已有修复但验证未完成；CLOSED 表示修复和回归证据已复核。复发时重新置为 OPEN，不引入额外状态。

关闭前须记录根因、修复、regression 关联和实际验证结果。无法自动化的反馈只有在记录原因且完成人工复核后才能关闭；仅增加一个尚未执行的 eval 不足以关闭问题。记录格式见模板；[MyBatis 示例](cases/EXAMPLE-mybatis-xml.md) 关联现有 SQL 场景，状态为未验证。
