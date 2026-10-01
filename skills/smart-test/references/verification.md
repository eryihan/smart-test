# 执行、报告与失败归因

## 执行前

读取本次执行范围、已有测试规范、相关未完成事项、环境证据和生产修改边界。直接从任务、构建配置与风险确定必需套件，不要求 init、项目登记或账本。使用实际构建配置、task 或 CI 中的命令，核对参数来源。运行仓库 wrapper 或构建文件会执行仓库代码；先按宿主规则检查可信度、权限、网络和成本。

只计划/dry-run 不执行构建。网络/Docker 被禁止时不尝试绕过；集成环境不可用时继续可做的验证并保留 BLOCKED。仅完成 Unit 时报告对应范围结果。

## 基线与本次回归

优先读取同范围、同构建配置的可信已有运行或 CI 结果；过期或不同环境的记录只作线索。基线不明时，在修改前运行相关已有测试，无需重复全仓验证。

遇到失败，分清“旧版本已有失败”“本次修改后才出现”“没有足够基线”。需要旧版本对比时使用经授权的隔离 checkout，保留原工作区修改，不自动 stash/reset。比较相同测试、配置、依赖与环境；只因测试名或异常文本相同，不能断定同一根因。

既有失败可以限定归因，但仍影响相应完整通过结论。新增失败也不自动是产品缺陷：先核对 Oracle、fixture、框架和真实路径。没有可比基线时记录 UNKNOWN，继续定位并验证独立部分。

## 执行与证据

使用宿主直接运行项目原生命令即可；核对真实退出码、执行版本、测试身份、计数与新报告。Python 不可用时读框架原生报告，不编造 JUnit 或手写管理协议。执行产生的命令、时间和退出码以工具返回为准。

需要自动采集 JUnit 时，可独立调用：

```text
python3 <skill-dir>/scripts/execute.py --repo <repo> --report 'target/surefire-reports/TEST-*.xml' -- ./mvnw test -Dtest=OrderServiceTest
python3 <skill-dir>/scripts/execute.py --repo <repo> --kind compile -- ./mvnw test-compile
```

报告分组用重复 `--report`，代码/配置变化检查用重复 `--evidence <仓库相对路径>`，超时用 `--timeout <秒>`。默认不保存管理文件；`--save-evidence` 保存 `.smart-test/runs/` 下真实 manifest 与报告副本，使用条件和留存见 [资料规则](artifacts.md)。运行时会使用互斥锁，正常退出清理；异常遗留锁先核查进程，不删除他人锁。原生命令自身仍可能生成构建产物，禁止在只读任务中调用。

需要分组最少数量、跳过政策或特定测试身份时，Agent 可在项目外临时目录准备高级输入，通过 `--input <文件>` 调用，无需工作记录 ID：

```json
{
  "argv": ["./mvnw", "test", "-Dtest=OrderServiceTest"],
  "summary": "订单金额边界单测",
  "evidence_paths": ["pom.xml", "src/main/java/OrderService.java", "src/test/java/OrderServiceTest.java"],
  "reports": [{"pattern": "target/surefire-reports/TEST-*.xml", "required": true,
               "min_tests": 1, "expected_test_ids": ["com.example.OrderServiceTest#rejectsNegativeAmount"]}]
}
```

示例必须替换成实际范围。多模块必需 suite 分组，不让一个模块掩盖另一个未执行。敏感参数通过既有环境或宿主能力提供，不能写入保存的 argv。JUnit XML 可能含敏感属性和输出，快照本地受限，分享前脱敏；不保存整份构建日志。

单次执行的必需套件由报告分组声明；多个命令分别核对，需机器汇总时使用真实多 run manifest。格式见 [运行示例](../assets/run-manifest.example.json)，示例不能当作执行证据。

工具返回真实命令结果、运行时间、报告计数及问题；EVIDENCE_PASS 仅代表声明的执行证据。超时/中断/启动失败返回 termination，124/130/127 来自工具，不能当原生命令退出码。POSIX 终止进程组；其他平台核查残留子进程。成功执行仍由 Agent 复核业务断言、范围与质量门后判定任务结果。

默认只检查声明的证据文件，不证明未引用源码或外部环境不变。构建前后、交付前核对相关代码、配置和环境；变化时按实际影响补验。文字调整不自动要求重跑；实际要求变化后旧执行只作历史依据。硬终止后核查实际进程和证据，不补造退出码，也不直接重跑掩盖前次失败。

仅阅读报告时：

```text
python3 <skill-dir>/scripts/collect_reports.py --repo <repo> --report 'target/surefire-reports/TEST-*.xml'
```

返回报告事实、测试身份与问题，freshness 为 UNKNOWN，任务仍为 NOT_VERIFIED。退出 0 只表示解析的报告结构无异常，不能证明本轮执行、零漏跑或业务通过。已有真实 manifest 可用 `--manifest <路径>` 检查执行窗口、分组、skip、最少数量与预期测试身份；两种方式均不写项目。

JUnit 收集拒绝陈旧、重复、缺失/非法 XML 和不完整 testcase 证据。命令退出 0、零测试或跳过必需测试不能完整通过；tail/grep/tee 成功不能代替构建退出码。Gradle cache/NO-SOURCE、profile/skip 和测试发现需核对。Contract/PIT/coverage 的原生专用报告单独读取，不转换成虚构 JUnit。

多次命令覆盖报告时，在下一次执行前保存需要复查的快照；不删除用户原生报告。原生或远端 CI 证据缺少时间/版本依据时明确未知，不能补造 manifest。

## 项目质量门

覆盖率按 [coverage.md](coverage.md) 解析。未指定的新门禁不新增阈值，但仓库已有门禁仍然适用；`REPORT_ONLY` 只展示结果，不把报告转换为阻断条件。

按真实执行与质量门生成结论。只有需要接续的未完成范围或证据留存才维护长期资料；不为 check 创建阶段记录或独立 status。问题只阻断相关部分。

verification 标 PASS 须同时满足：

- 必需命令实际执行且 exit 0，必需测试真实被发现并执行；未因 skip/profile/task 配错漏跑。
- 计划风险对应的断言经过复核，Oracle 无未解决歧义；无未解决 PRODUCT_DEFECT / ENVIRONMENT_DEFECT。
- 既有 coverage/changed coverage/critical module/mutation policy 按适用范围通过；未要求的项记 NOT_APPLICABLE，不得填写估计百分比。
- 本轮测试不把异步 timing、随机性、共享数据或顺序依赖当作确定行为；不存在未处理的 flaky。
- 记录实际验证版本；验证后又改了代码、依赖、环境或测试配置，受影响结果 STALE。

`--fast` 只在策略允许的范围缩小；必需 integration 未跑只能说 fast/unit scope 通过。`--full` 依据模块图和关键风险扩大，不自动引入 PIT、全量 E2E 或性能压测。

## 阶段结果

按实际范围分别说明分析、实施进度和验证结果。工作进度可 COMPLETED，验证仍为 NOT_RUN；不要求落盘状态文件。

| 状态 | 含义 |
|---|---|
| COMPLETED | 本次声明的工作范围已完成；另列测试验证结果 |
| NOT_STARTED / NOT_RUN | 工作未开始 / 命令或测试未实际执行 |
| PROPOSED / READY | 方案待处理 / 该阶段输入齐备；验证结果与执行授权另行核对 |
| PARTIAL | 已完成明确子范围，仍有必需部分未完成；列出各部分结果 |
| BLOCKED | 某阶段受具体前提限制，标明受影响动作与解除条件 |
| FAILED | 实际动作失败；失败类别需进一步归因 |
| PASS | 相应范围的必需验证与质量门均有有效证据 |
| STALE / NOT_VERIFIED | 原证据受变化影响 / 现有证据不足以判断通过 |
| UNKNOWN / NOT_APPLICABLE | 事实无法确认 / 按规则不适用；后者必须说明原因 |

`EVIDENCE_PASS` 和报告结构结果是辅助工具的局部结果，不能直接当项目 PASS。

## 受阻工作

`BUSINESS_AMBIGUITY` 只阻断依赖未知预期的断言与修复；明确规则与实现不符仍可补测、复现产品缺陷。仅缺运行环境时，若依据、代码、测试 API 与授权已足够，可实现测试并执行独立的编译/Unit；必需 integration 仍记 BLOCKED/NOT_RUN。缺实现所必需的 API 或版本信息时先补信息，不猜配置。

按阶段与风险记录阻塞，仅暂停依赖该前提的动作；保留阻塞项，继续独立工作。Agent 核对实际依据、受影响动作与解除条件。

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

从首个有因果意义的错误定位，区分根因与级联失败：

1. 测试未发现/报告缺失：核对 engine、命名、includes/excludes、profile/task 依赖、skip、Gradle cache 和实际执行模块；不靠关闭 no-tests 检查修复。
2. 上下文或连接失败：检查配置来源、bean/版本冲突、隔离服务 readiness 与连接权限；先确认实例安全和可用，不把凭证值写入报告。
3. SQL/数据断言失败：核对迁移、fixture、时间精度、租户/过滤条件、真实查询和 flush/缓存；不先修改期望值。
4. 行为断言失败：按输入、规则、实际路径和副作用定位到差异；需要生产修复时保留失败测试并核对授权。
5. 单独通过而一起失败：检查共享数据、static 状态、顺序、Clock/随机源、异步任务和资源泄漏。按证据缩小复现，不把“重试后通过”当修复。

有限重试只用于定位，默认至多一次且在相同代码/环境；记录全部尝试，不用最后成功覆盖先前失败。继续失败或无法解释的间歇通过要停下归因；不无限重试、不增加 sleep 来掩盖问题。补丁后的验证另行记录修改与新版本。

交付中的验证摘要包含 Command、Result、Test Count、Failed、Errors、Skipped、Duration、Coverage/Mutation（若适用）、未验证范围与 blockers。对话交付与实际证据保持一致；有独立消费者时才保存 verification-report.md。复杂失败按需保存 failure-analysis.md，保留脱敏证据，不复制密码、Token、真实生产个人数据。
