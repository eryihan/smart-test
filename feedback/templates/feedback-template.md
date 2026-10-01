# <id>：<中性问题标题>

```yaml
id: <附件 id 或维护者分配 id>
date: <发现日期 YYYY-MM-DD>
smart_test_version: <问题发生时版本；未知写 UNKNOWN>
smart_test_commit: null # 不可获得时保留 null
host: <codex / claude-code / other / unknown>
host_version: null
workflow: <help / init / scan / changes / check / pipeline / update>
feedback_type: <feedback/README.md 中的类型>
status: OPEN
```

## scenario

合成场景、范围、前置条件、用户明确要求和复现步骤。metadata.timestamp 记录导出时间；发现时间或当时版本未知时标记 UNKNOWN。不要粘贴业务原文、源码、完整 diff、内部地址或个人信息。

## actual_behavior

实际工具调用、文件改动类别和结论；只保留脱敏事实。关联本地反馈包 id，不提交反馈包。

## expected_behavior

应有行为及来源（smart_test 规则位置、脱敏后的用户要求、可靠测试工程事实）。不要以模型当前输出作为期望依据。

## root_cause

UNKNOWN。定位后改为 SKILL_RULE / REFERENCE_RULE / HELPER_IMPLEMENTATION / GRADER / HOST_VARIANCE / FIXTURE 中的一项，并写明证据。

## fix

待定位。记录修改文件、原因和可追溯的修复引用；未实现时标记待处理。

## regression_case

- 测试函数或 eval ID：待建立。
- 合成 fixture 与判定依据：待补充。
- 修复前结果：NOT_RUN。
- 修复后结果：NOT_RUN。
- 验证版本、宿主、日期与结果记录：待补充。
- 无法自动化时的原因及人工复核步骤：不适用或具体原因。
- 关闭依据：待验证。
