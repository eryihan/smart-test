# 执行、报告与失败归因

## 执行前

读取已生效策略、test-plan、执行范围、doctor 结果和生产修改边界。先确认命令来自真实 POM/Gradle task/CI，不凭猜测添加参数。运行仓库 wrapper 或构建文件会执行仓库代码；先按宿主规则检查可信度、权限、网络和成本。

只计划/dry-run 不执行构建。网络/Docker 被禁止时不尝试绕过；集成环境不可用时继续可做的验证并保留 BLOCKED。只跑 Unit 时不要称 full verification PASS。

## 执行与证据

按需要编译 → Unit/Slice → 必需 Integration → 适用 Contract → Critical flow → 质量检查。Maven `verify` 已包含前面的阶段，无需为了形式重复跑一遍。

每次运行保存：实际 argv（脱敏）、工作目录、Git HEAD 与工作树指纹、开始/结束时刻（含时区）、退出码、执行环境、报告路径和必需测试集合。命令没有实际执行时必须记 NOT_RUN，不能填预计退出码或测试数量。

若多条命令会覆盖同一路径报告，在每次结束时立即复制 XML 到 `.smart-test/runs/<run-id>/...` 快照，再执行下一条。保留原始 mtime，以便判定其属于该次执行。不要删除用户已有报告；可在允许范围内清理本轮生成目录或选用全新报告路径。报告中的 stdout/stderr/properties 可能包含秘密，不复制到可共享报告；敏感 XML 只供本地检查，分享前脱敏。

使用 [run-manifest.example.json](../assets/run-manifest.example.json) 的结构记录真实执行。示例日期/命令不代表验证记录，必须替换；完成真实记录后移除 `example_only` 标志，脚本拒绝将示例作为执行证据。每个 reports group 使用尽量精确的 glob；不要用全仓 `**/*.xml` 混入旧报告。`required_run_ids` 列出计划要求的执行项；有 compile-only run 可不带 reports，但它失败仍会使收集结果失败。

必需套件的每个模块单独分组，否则 A 模块报告可能掩盖 B 模块没有执行。如果新计划要求特定测试，列 `expected_test_ids`（XML 中的 `classname#name`）。report group 的 `required: true`、`min_tests >= 1`，默认不允许 skip；确有已授权的无关 skip 才 `allow_skipped: true`，仍不得把被 skip 的测试算作 expected test。

```text
python3 <skill-dir>/scripts/collect_reports.py --repo <repo> --manifest <manifest.json>
```

退出码 0：`EVIDENCE_PASS`，只表示声明的执行证据通过；1：`NOT_VERIFIED`，报告缺失、陈旧、失败、skip、零测试或 blockers；2：输入错误。脚本不执行测试、不验证人填写的 manifest 是否真实，也不理解计划风险是否足够，由 Agent 核实。

报告只接收 JUnit XML（Surefire/Failsafe/Gradle 等常用格式）。Contract/PIT/coverage 的专用报告由 Agent 单独读取并关联命令；不可伪装成 JUnit 结果。没有 JUnit XML 的仓库可用框架原生报告，但明确证据来源，不能编 XML 让脚本通过。

脚本拒绝在运行时间窗口之外的报告、重复路径、只有 suite 声称测试数却没有 testcase 的不完整报告、非法 XML。它只输出计数和结构问题，不输出原始失败日志或命令参数。

## 项目质量门

覆盖率按 [coverage.md](coverage.md) 解析。未指定的新门禁不新增阈值，但仓库已有门禁仍然适用；`REPORT_ONLY` 只展示结果，不把报告转换为阻断条件。

只有以下全满足才将 verification 标 PASS：

- 必需命令实际执行且 exit 0，必需测试真实被发现并执行；未因 skip/profile/task 配错漏跑。
- 计划风险对应的断言经过复核，Oracle 无未解决歧义；无未解决 PRODUCT_DEFECT / ENVIRONMENT_DEFECT。
- 既有 coverage/changed coverage/critical module/mutation policy 按适用范围通过；未要求的项记 NOT_APPLICABLE，不捏造百分比。
- 本轮测试不把异步 timing、随机性、共享数据或顺序依赖当作确定行为；不存在未处理的 flaky。
- 记录实际验证版本；验证后又改了代码、依赖、环境或测试配置，受影响结果 STALE。

`--fast` 只在策略允许的范围缩小；必需 integration 未跑只能说 fast/unit scope 通过。`--full` 依据模块图和关键风险扩大，不自动引入 PIT、全量 E2E 或性能压测。

## Failure Triage

| 类别 | 证据与处理 |
|---|---|
| TEST_DEFECT | Oracle 清楚，测试数据/断言/调用方式错误；在授权范围内修测试 |
| TEST_INFRA_DEFECT | 测试 profile、插件、容器 wiring 错误；修测试设施并重跑相关层 |
| ENVIRONMENT_DEFECT | 缺 daemon/端口/镜像/网络/测试凭证；标 BLOCKED，不伪造 PASS |
| PRODUCT_DEFECT | 可信 Oracle + 正确测试证明实现违背规则；给生产修复建议，授权足够才改 |
| BUSINESS_AMBIGUITY | 业务结果不明确或互相冲突；暂停受影响断言调整，提出具体待确认事实 |
| FLAKY_TEST | 同一代码和环境下不稳定；查时间/随机/共享状态/并发/网络/顺序 |

无法归因时先记 UNCLASSIFIED 和当前假设，不把所有 AssertionError 都归产品缺陷。每条记录 failure、classification、evidence、likely cause、safe action、manual action、状态。

有限重试只用于定位，默认至多一次且在相同代码/环境；记录全部尝试，不用最后成功覆盖先前失败。继续失败或无法解释的间歇通过要停下归因；不无限重试、不增加 sleep 来掩盖问题。修复后再运行不是诊断重试，记录补丁和新验证版本。

verification-report.md 展示 Command、Result、Test Count、Failed、Errors、Skipped、Duration、Coverage/Mutation（若适用）、未验证范围与 blockers。failure-analysis.md 保留脱敏证据，不复制密码、Token、真实生产个人数据。
