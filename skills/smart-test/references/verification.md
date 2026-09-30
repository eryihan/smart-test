# 执行、报告与失败归因

## 执行前

按 [项目规范与工作记录](artifacts.md#项目规范与工作记录) 接续或开始任务，读取本次执行范围、生效测试规范、环境证据和生产修改边界。已有适用 policy/plan 要继续遵守；没有持久产物时直接从用户任务、构建配置和风险确定必需套件，不要求先 init 或创建账本。使用实际构建配置、task 或 CI 中的命令，核对参数来源。运行仓库 wrapper 或构建文件会执行仓库代码；先按宿主规则检查可信度、权限、网络和成本。

只计划/dry-run 不执行构建。网络/Docker 被禁止时不尝试绕过；集成环境不可用时继续可做的验证并保留 BLOCKED。仅完成 Unit 时报告对应范围结果。

## 基线与本次回归

优先读取同范围、同构建配置的可信已有运行或 CI 结果；过期或不同环境的记录只作线索。基线不明时，在修改前运行相关已有测试，无需重复全仓验证。

遇到失败，分清“旧版本已有失败”“本次修改后才出现”“没有足够基线”。需要旧版本对比时使用经授权的隔离 checkout，保留原工作区修改，不自动 stash/reset。比较相同测试、配置、依赖与环境；只因测试名或异常文本相同，不能断定同一根因。

既有失败可以限定归因，但仍影响相应完整通过结论。新增失败也不自动是产品缺陷：先核对 Oracle、fixture、框架和真实路径。没有可比基线时记录 UNKNOWN，继续定位并验证独立部分。

## 执行与证据

按需执行编译 → Unit/Slice → 必需 Integration → 适用 Contract → Critical flow → 质量检查。Maven `verify` 包含前序阶段，避免重复执行。

每次实际运行按 [运行 manifest](artifacts.md#运行-manifest) 保存记录，命令、时间与退出码优先从工具返回直接获取。执行前后核对 Git HEAD、工作树和测试配置；报告与当前版本不一致时不能复用通过结论。运行证据关联本次工作记录，不要求同时生成独立 policy/plan/status。保存实际工作目录、完整参数及版本依据；脱敏不能省略影响测试选择的 profile、skip 或 no-tests 参数。

JUnit 原生命令优先调用内部执行工具，由 Agent 在项目外临时目录准备输入：

```json
{
  "argv": ["./mvnw", "test", "-Dtest=OrderServiceTest"],
  "summary": "订单金额边界单测",
  "check_id": "unit",
  "required_checks": ["unit", "integration"],
  "evidence_paths": ["pom.xml", "src/main/java/OrderService.java", "src/test/java/OrderServiceTest.java"],
  "reports": [{
    "pattern": "target/surefire-reports/TEST-*.xml",
    "required": true,
    "min_tests": 1,
    "expected_test_ids": ["com.example.OrderServiceTest#rejectsNegativeAmount"]
  }],
  "timeout_seconds": 600
}
```

示例路径、命令和必需项须替换为项目实际范围；仅需 Unit 时不添加 integration。多模块分别列出报告分组，每项均须有本轮实际执行的测试。`reports` 仍可使用字符串作为简写；需要最少数量、允许跳过或指定测试身份时使用对象形式。编译输入设置 `kind: "compile"`、`reports: []`。

```text
python3 <skill-dir>/scripts/execute.py --repo <repo> --id <工作记录id> --input <临时执行输入.json>
```

工具直接传递 argv，不经 shell 拼接；保存开始进度、实际退出码、时间、代码指纹及报告副本，随即关联同一工作记录。成功执行先记 NOT_VERIFIED，Agent 复核断言、范围和适用质量门后再追加 PASS；非零退出记 FAILED。超时、中断和启动失败保留 termination，124/130/127 是工具退出码，不能当作原生命令返回值。POSIX 超时或中断终止进程组；其他平台只终止直接子进程，须核查残留构建进程。硬终止或机器断电可能留下 IN_PROGRESS 和锁，恢复时核查进程与运行目录，不补造退出码。

工具只复制执行窗口内的指定 XML，保留 mtime，不删除项目报告。已有报告、零测试和执行期间引用文件变化不能产生 EVIDENCE_PASS。运行 manifest 同时保存生效测试规范的路径和指纹；规范复核后，旧运行只能保留为历史证据，不能直接登记为当前规范下的 PASS。追加 PASS 时再次核对 manifest 中的执行后指纹、规范指纹和测试身份，源码变化后不能重新标记旧运行；未提供自动指纹的原生或 CI 证据仍由 Agent 核对版本。同一工作目录的工具执行互斥，status 仍只读；不要另行并发运行会覆盖报告的命令。敏感参数通过既有环境或宿主管理能力提供，不能放进将被保存的 argv。输出不另存整份构建日志；报告副本限制为本地可读，分享前仍需脱敏。

输入或记录写入失败时，核查已生成的 runs 目录并补关联真实证据，不能直接重跑掩盖前次结果。工具适用于 JUnit 报告；框架原生报告、CI 远端任务和专用质量工具仍由 Agent 按下述方式留证，不编造 JUnit。

核对构建命令本身的退出码；tail、grep、tee 等管道末端成功不能代替构建成功。报告须证明目标测试实际被发现、执行，`-DfailIfNoTests=false` 等参数不能证明非零测试数。

若多条命令会覆盖同一路径报告，在每次结束时立即复制 XML 到 `.smart-test/runs/<run-id>/...` 快照，再执行下一条。保留原始 mtime，以便判定其属于该次执行。不要删除用户已有报告；可在允许范围内清理本轮生成目录或选用全新报告路径。报告中的 stdout/stderr/properties 可能包含秘密，不复制到可共享报告；敏感 XML 只供本地检查，分享前脱敏。

报告分组须覆盖每个必需模块和套件；有特定测试要求时检查其身份。不要用全仓 `**/*.xml` 混入旧报告。编译证据与测试证据分别解释；已授权的无关 skip 也不能算作执行了必需测试。

```text
python3 <skill-dir>/scripts/collect_reports.py --repo <repo> --manifest <manifest.json>
```

退出码 0：`EVIDENCE_PASS` 或 `VALID`，表示声明的执行/结构证据通过；1：`NOT_VERIFIED` 或 `INVALID`，报告缺失、陈旧、失败、skip、零测试、结构不完整或 blockers；2：输入错误。脚本检查报告，不运行测试；manifest 真实性与风险覆盖由 Agent 核验。

报告只接收 JUnit XML（Surefire/Failsafe/Gradle 等常用格式）。Contract/PIT/coverage 的专用报告由 Agent 单独读取并关联命令；不得转换为虚构的 JUnit 结果。没有 JUnit XML 的仓库可用框架原生报告，但明确证据来源，不能编 XML 让脚本通过。

脚本拒绝在运行时间窗口之外的报告、重复路径、只有 suite 声称测试数却没有 testcase 的不完整报告、非法 XML。它只输出计数和结构问题，不输出原始失败日志或命令参数。

## 项目质量门

覆盖率按 [coverage.md](coverage.md) 解析。未指定的新门禁不新增阈值，但仓库已有门禁仍然适用；`REPORT_ONLY` 只展示结果，不把报告转换为阻断条件。

按本次 run 与质量门生成结论，立即追加工作记录；独立 status.json 仅在旧流程实际消费或独立复用时保存。消费或生成已知 JSON 时按 [artifacts.md](artifacts.md) 校验实际依赖，不为 check 补齐整套治理文件。结构问题阻断依赖该产物的结论，不妨碍说明已观察到的执行结果和继续独立验证。

verification 标 PASS 须同时满足：

- 必需命令实际执行且 exit 0，必需测试真实被发现并执行；未因 skip/profile/task 配错漏跑。
- 计划风险对应的断言经过复核，Oracle 无未解决歧义；无未解决 PRODUCT_DEFECT / ENVIRONMENT_DEFECT。
- 既有 coverage/changed coverage/critical module/mutation policy 按适用范围通过；未要求的项记 NOT_APPLICABLE，不得填写估计百分比。
- 本轮测试不把异步 timing、随机性、共享数据或顺序依赖当作确定行为；不存在未处理的 flaky。
- 记录实际验证版本；验证后又改了代码、依赖、环境或测试配置，受影响结果 STALE。

`--fast` 只在策略允许的范围缩小；必需 integration 未跑只能说 fast/unit scope 通过。`--full` 依据模块图和关键风险扩大，不自动引入 PIT、全量 E2E 或性能压测。

## 阶段结果

按实际范围分别记录分析、实施进度和验证结果。工作进度可 COMPLETED，验证仍为 NOT_RUN；格式见 artifacts。

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

`EVIDENCE_PASS`、`VALID` 是辅助工具的局部结果，不能直接当项目 PASS。治理账本的 EFFECTIVE/INVALIDATED 表示决策可用性。

## 受阻工作

业务预期未知或冲突时，可以分析和交付缺口，暂停依赖该预期的断言与修复。仅缺运行环境时，若依据、代码、测试 API 与授权已足够，可实现测试并执行独立的编译/Unit；必需 integration 仍记 BLOCKED/NOT_RUN。缺实现所必需的 API 或版本信息时先补信息，不猜配置。

按阶段与风险记录阻塞，仅暂停依赖该前提的动作；保留阻塞项，继续独立工作。结构校验决定输入是否可用，Agent 判定受影响动作与解除条件。

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

工作记录中的验证摘要包含 Command、Result、Test Count、Failed、Errors、Skipped、Duration、Coverage/Mutation（若适用）、未验证范围与 blockers。对话交付与记录保持一致；独立复用时再保存 verification-report.md。复杂失败按需保存 failure-analysis.md，保留脱敏证据，不复制密码、Token、真实生产个人数据。
