# EXAMPLE：MyBatis XML 变化只生成 Unit Test

**这是合成示例，不是真实项目反馈，也不代表验证已完成。**

```yaml
id: EXAMPLE-mybatis-xml
example_only: true
date: null
smart_test_version: 0.1.1
smart_test_commit: null
host: unknown
host_version: null
workflow: changes
feedback_type: WRONG_STRATEGY
status: OPEN
```

## scenario

合成订单项目修改 Mapper XML 的 JOIN 和 NULL 条件，后端使用 MySQL。用户要求验证 SQL 行为，隔离数据库暂不可用。

## actual_behavior

假设 Agent 只生成 Mockito Unit Test，并根据 mapper 方法被调用报告 SQL 已验证。

## expected_behavior

需要同引擎隔离数据库的 Integration Evidence；当前环境不可用时保留 BLOCKED，不以 mock 调用验证 SQL 语义。依据是 `skills/smart-test/references/java-testing.md` 的 SQL 测试规则和用户的验证要求。

## root_cause

UNKNOWN。先检查宿主是否加载了 SQL 规则、Agent 是否忽略规则、helper 是否遗漏 XML 风险信号、fixture 是否提供了真实 XML 变化。不能仅凭最终回答认定是 Prompt 不足。

如果证据证明 reference 没有说明该 SQL 风险，归为 REFERENCE_RULE；如果确定性风险采集遗漏应有信号，归为 HELPER_IMPLEMENTATION。按实际证据选择，不同时猜测多个根因。

## fix

尚未实施。根因确定后只修改相应规则或 helper，不降低 SQL 验证标准，不把 Integration expectation 改成 Unit。

## regression_case

- 复用 `evals/evals.json` 的 `sql-mapper-change`，用合成 XML 改动复现。
- 检查测试计划是否要求 DB Integration Evidence；环境不可用是否 BLOCKED；是否误用 Mockito 结果报告 SQL PASS。
- 若根因是 helper，再补一项读取合成 Mapper XML 的确定性回归测试。
- 修复前、修复后结果均为 NOT_RUN；真实宿主实跑并记录工具调用、产物和结论后才能更新。
- 示例不执行关闭流程。真实 case 只有修复与回归证据齐全后才能 CLOSED。
