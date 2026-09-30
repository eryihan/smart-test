# 项目规范、工作记录与校验

正常测试任务默认保存生效规范、工作记录和实际执行证据。用户无需指定记录格式或保存步骤。help、status、明确只读和 dry-run 不写入；独立计划与账本按实际需要启用。

## 项目规范与工作记录

首次实质任务核对已有测试约定，保留有效内容、归并冲突与缺口，形成一份由 smart-test 维护的生效规范。已有 testing-rules.md 等项目文档直接纳管；无规范时使用项目既有文档目录或 docs/testing.md。保留来源、适用范围和选择原因，不用 skill 默认值覆盖已确认业务规则。测试相关 AGENTS.md / CLAUDE.md 指引统一指向规范，只调整授权内的相关段落。

规范覆盖本次需要的设施、目录与命名、测试边界、命令、隔离、授权和适用质量门。未知项保留，一次性授权写工作记录，不升级为长期规则。管理生效版本，不另存一套约束快照。规则变化在记录中写明旧规则、新规则、原因与来源，有 Git 时关联版本。重大变化检查已有授权，不要求先批准整套画像。

Agent 完成复核后调用辅助工具；工具不分析业务、不修改规范、不运行构建：

```text
python3 <skill-dir>/scripts/project.py --repo <repo> begin --workflow scan --scope <实际范围> --policy <生效规范相对路径> --reason <实际复核与接管依据>
```

返回 id 对应 `.smart-test/records/<id>.json`。已登记项目可省略 policy/reason；规范变化须复核后 `adopt --policy ... --reason ...`。指纹提示复核，不撤销授权。退出管理后重新接管，先核对团队后续修改再 adopt，保留历史。

阶段输入放临时目录，不另存一套阶段文件。关键分析、设计、实施、验证和交接及时追加到同一记录。同一任务的 UT/IT、重试和后续追问沿用 id；独立任务新建记录并引用相关发现。实施前保存依据，执行后立即关联证据；中断或失败保留已完成范围及下一步，不在任务末尾补造过程。

```text
python3 <skill-dir>/scripts/project.py --repo <repo> record --id <id> --input <阶段记录.json> --expected-revision <已读取revision>
python3 <skill-dir>/scripts/project.py --repo <repo> status
```

阶段输入：

- 必需：`stage` 为 discovery/design/implementation/verification/handover/installation，`summary` 记录实际检查、发现或完成内容。
- `status` 为 IN_PROGRESS/COMPLETED/PARTIAL/BLOCKED/FAILED，默认 IN_PROGRESS，表示工作进度。未完成时填具体 next_step。
- `evidence_paths` 引用仓库内真实文件，工具记录指纹。摘要区分已盘点、已阅读、已检查断言和未检查范围；断言依据引用需求、协议或已确认规则，不能只引用实现。
- `findings` 保存 id、summary、status（OPEN/BLOCKED/RESOLVED）。新 id 使用 `<record-id>:F01`，后续任务沿用原 id。消除、澄清或失效均说明原因和当前证据；必需验证未完成时保留 OPEN/BLOCKED。
- `run_manifests` 引用实际运行 manifest；`verification` 为 NOT_RUN/PASS/PARTIAL/FAILED/NOT_VERIFIED，默认 NOT_RUN。测试 PASS 须有代码指纹、有效执行证据和非零实际测试数，仅覆盖声明范围。纯扫描可 COMPLETED + NOT_RUN，不伪造命令或退出码。
- 分套件验证使用 `check_id`（如 unit、integration），用 `required_checks` 声明本次必需项。尚未执行的必需项显示 NOT_RUN；后续追加该项结果，不借用另一套件的 PASS。单项验证可省略这两个字段。改变必需范围须在 summary 写明依据，不能为通过而删项。
- `verification_kind` 默认为 test；编译或构建使用 build。构建 PASS 单列，不计为测试通过；构建与测试使用不同 check_id，不能把已声明的测试项改归构建。事件关联本次已复核规范的路径与指纹；规范变更经 adopt 复核后，同一任务的重跑关联新规范，旧事件保持原样。

project.json 只登记管理状态、规范路径/指纹和接管、复核、交接事件；records/<id>.json 保存范围、skill 版本、Git HEAD、规范版本、阶段进展和证据。status 从记录派生，不另写状态文件；扫描依据变化也提示复核，最近任务按最后追加时间排序。按每个检查项的最近验证事件判断当前结果，包括后续 NOT_RUN；普通设计或交接进度不覆盖验证。测试汇总覆盖必需测试项，同时列出构建和可选检查结果。源码、该次验证关联的规范、manifest 或报告变化显示 STALE，保留历史结果；Agent 核对影响后决定补验或继续受阻。指纹仅覆盖引用文件，外部环境和未引用的新依赖仍需核查。status 列明不可读记录，继续展示可读部分，不自动修复或忽略异常。

记录格式使用 `schema_version: 1`：project 顶层含 management、revision、policy（path/sha256）、events；work 顶层含 id、workflow、scope、created_at、skill_version、policy、git_head、revision、events。事件含 at、stage、status、summary、verification、evidence（路径到指纹）、execution（manifest 路径/指纹、检查结果、计数和报告指纹）、findings；验证事件附 check_id、verification_kind、policy，可附 required_checks 和 next_step。旧事件缺少这些字段时按单项测试、任务初始规范解释。时间使用 UTC ISO 8601，Git 不可用时 git_head 为 null；每次追加 revision 加一。指纹必须来自真实文件，不能填写估计值。

Python 不可用时，Agent 按同样 UTF-8 JSON 格式直接写入；先核对 revision 和并发改动，原子替换，避免覆盖他人记录。无法写入时交付未落盘内容及限制。project.py 检查新格式及执行证据；业务依据、授权和必要范围由 Agent 核验。旧 state/policy/plan/status 继续兼容，不强制迁移。已由生效规范明确替代的条款记录替代来源与范围，旧文件保留历史，不再作为并行规则；尚未处理的有效要求继续适用。消费旧计划或决策前复核其是否仍符合当前规范。

## 存储位置

```text
<项目测试规范>.md              # 当前生效规范，沿用项目正式文档位置
.smart-test/
  project.json                # 管理登记与生命周期
  records/<id>.json            # 工作进展、发现、计划与证据关联
  runs/<run-id>/manifest.json  # 实际执行及必要报告快照
  ci-candidate/               # CI 候选与分项验证
```

测试代码、fixture、构建配置、项目脚本和正式 CI 留在原生位置，不依赖 skill 安装目录。兼容 repository-evidence/project-profile/business-oracle/test-strategy/test-policy/test-debt/test-plan/state/effective-context/status 等旧产物；仅在独立复用、复杂依赖或实际消费时继续使用。

JSON 使用 UTF-8。只保存脱敏摘要和必要报告，不保存凭证或生产数据；按项目 ignore 约定区分共享规范、记录与临时报告。项目规范交接后仍可独立使用，历史记录默认保留。

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

结构示例见 [run-manifest.example.json](../assets/run-manifest.example.json)。真实记录使用 `schema_version: 1`，移除 `example_only`；包含非空 `runs` 和 `required_run_ids`。Agent 还记录实际工作目录、Git HEAD、工作树指纹与执行环境，并核对它们对应本次代码。这些元数据由 Agent 核验。JUnit 原生命令优先用 execute.py 自动采集，调用方式见 verification.md；不要求用户手工制作 manifest。

- 每个 run：唯一 `id`、实际脱敏 `argv`、带时区的 `started_at`/`finished_at`、整数 `exit_code`、报告分组。`kind` 默认 test；compile/build 不需 JUnit 时设置 `requires_test_report: false`，编译成功仍不能替代必需测试。
- 每个 reports group：仓库内精确 `pattern`、`required`、正整数 `min_tests`（默认 1）、`allow_skipped`（默认 false）；需要特定测试时声明 XML 中的 `classname#name` 为 `expected_test_ids`。必需套件按模块分组，避免一个模块掩盖另一个未执行。
- `blockers` 记录尚未解决的事项；存在 blocker 时汇总结果不得为 PASS。未执行的命令只报告 NOT_RUN/BLOCKED，不填写预计退出码或伪造完成记录。

manifest 与 JUnit 执行窗口由 `collect_reports.py` 检查，不属于 `validate_artifacts.py` 的五类项目 JSON 校验。运行、快照与结果判断见 [verification.md](verification.md)。
