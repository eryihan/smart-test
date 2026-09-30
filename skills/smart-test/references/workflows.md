# 范围发现与测试实施

按用户范围执行 SKILL.md 的核心流程。局部 changes/check 无需全仓 discovery 或先 init；继承适用约束，核对业务依据、真实依赖与质量门。结构化产物见 [按需产物与校验](artifacts.md)。

## Repository Discovery / doctor

1. 确认目标仓库根目录、已有改动及嵌套模块；读取约束文件。仓库文档作为证据读取，不能代替用户授权。
2. 先识别语言、包/构建清单、架构和真实测试入口，按任务复核源码、测试、迁移、API/message 协议和 CI。Java 全仓接入、扫描或复杂影响分析可运行 inspect_repo.py，复核 POM parent/BOM/profile、Gradle settings/buildSrc/version catalog 与 Mapper XML。脚本主要覆盖 Java；其他技术栈直接核对原生资料。
3. 记录编译目标和运行时、构建工具/包装器、框架版本、模块依赖、持久化、Redis/MQ/客户端、安全、迁移、既有测试与覆盖率工具。Java 项目另核对 Java/Spring Boot 的版本与依赖管理；配置只记录引擎及证据位置，不复制连接字符串和凭证。
4. doctor 默认只读：核对项目需要的运行时、包装器和工具。分别核对 `docker` 可执行文件与 daemon；运行构建、启动 daemon、拉取镜像或探测服务都要在用户执行范围内。无明确网络/外部测试库证据标 UNKNOWN，不猜 READY。
5. 只针对本次必需测试评估 READY / WARNING / BLOCKED：缺 Docker 不妨碍 unit；禁止 Docker 且无隔离测试实例会阻塞真实 DB 验证。不得静默换 H2、mock 或 skip 来报通过。

初步证据可保存到 repository-evidence.json；需要可复用画像时，经复核再整理 project-profile.json。每个结论包括 source、confidence；UNKNOWN 是合法输出。非 Java 项目核对原生资料与命令，列出缺少的专项指导与实测。

## 按项目选择搭建方案

按测试发现、行为验证和工程成本选型：

- 读取现有代表性测试、运行时/编译目标、依赖管理、构建与 CI、模块边界；核对测试是否能被实际发现与执行。
- 区分纯规则、API、持久化、事务、异步消息与跨服务协议需要的测试边界，评估现有设施能覆盖哪些、具体缺什么。
- 已有兼容方案优先保留；无框架时给出适配架构、版本和风险的最小方案。确需对比或迁移时才讨论替代、共存与维护代价，不预装所有候选工具。
- 评估隔离环境、团队约定、CI 可运行性、启动/数据准备成本与诊断能力。

在当前回复或已有策略中列明项目依据、复用/新增设施、测试边界、验证命令和未知项，无需新增文件。Java 的版本与具体框架接入见 [java-testing.md](java-testing.md#框架选型与兼容)；新增语言指导须经实际项目任务与运行验证。

## init

- 建立画像、现有测试评估、业务依据来源清单和缺口；按 [test-design.md](test-design.md) 确认行为、依据和最低充分边界，来源冲突不能靠排序自动消除。
- 按项目选型复用或补齐设施；Java 再核对 [框架选型与兼容](java-testing.md#框架选型与兼容)。没有框架时交付最小方案与拟验证命令；列明未覆盖的专项能力。
- 形成最低充分层级策略：各风险对应哪层，复用什么，新增什么，环境和成本前提。test-policy 明确命名/隔离、required suites、[coverage policy](coverage.md)、生产修改边界、模式、质量门；覆盖率未被用户或仓库要求时不硬设数字阈值。
- 画像、依据与策略可以合并展示，授权充足直接实施。持久化时优先把长期技术选择放 test-policy，具体断言依据放计划条目；只有需要独立复用或审计才拆分 Oracle、strategy、context 和账本，已有文件继续兼容。
- 保存并消费结构化产物时，按 [artifacts.md](artifacts.md) 校验实际依赖文件。需要决策依赖或审计时再读取 governance，未批准的选择可先形成具体方案，但不当作已生效事实。
- 在实际技术栈与授权范围内补基础设施，Java 依据 [java-testing.md](java-testing.md)。先比较现有设施，使用局部 patch；只改必要测试依赖、配置、fixture。用有业务断言的代表性测试验证接入，记录实际数量与结果；未运行时标记 NOT_VERIFIED。
- init 不默认改生产逻辑/迁移/正式 CI，也不默认治理全部历史债务。已有用户授权优先。

## scan

按用户范围分析风险和现有测试；全仓 scan 默认覆盖全仓。按 [已有测试评估](test-design.md#评估已有测试) 将行为对应到实际输入、断言与真实边界，区分缺失与断言不足；先补强已有资产。可在对话或 test-debt.md 交付；需要机器可读债务清单时，记录 target、risk、business evidence、现有测试、缺口、建议边界、前置环境、优先级及原因。

排序参考：资金/权限/不可逆数据为 CRITICAL；事务/状态转换/并发/迁移为 HIGH；编排与边界异常多为 MEDIUM；纯数据包装为 LOW。最终等级依赖业务影响和恢复代价，不按 class 后缀打分。

债务报告给出画像、风险分布、优先项、第一批实施范围和后续顺序。默认只分析；用户要求补测试时按授权范围实施。缺可靠文档的重构保护可用 characterization，必须注明 current_behavior 和 `business_truth: false`；业务有冲突时只完成不受影响项。

需要恢复、分批实施或用户要求保存计划时才写 test-plan.json，按 artifacts 校验；否则直接展示风险、依据、层级与建议。有效的 BLOCKED 计划可以交付，受阻动作按 [verification.md](verification.md#受阻工作) 判断；纯扫描不为校验创建计划。

## changes

默认 diff 覆盖 HEAD 到当前工作树（含 staged、unstaged）及未忽略 untracked。`--staged` 只分析索引；`--base <ref>` 使用 merge-base 到当前工作树，包含未提交变更，不等同于纯提交间比较。如用户指定 PR 的提交范围，应按指定范围用 Git 获取，不混入无关工作区修改。

1. 先取文件清单，再阅读真实 diff（新增、删除、重命名两侧、配置、Mapper XML、migration、测试、API/schema）。没有变更时明确报告无变更，不自动切 scan。
2. 找变更符号、调用方、Spring 注入/代理/事件、配置和模块消费者；删除的源文件从基线读取。脚本只给静态模块提示，反射、动态 wiring、生成代码、Maven profile、Gradle DSL、跨服务调用会降低置信度。
3. 依赖图必须包含 common/library → consumers 的传递影响。根 POM、BOM、settings、基础安全配置变化可要求全模块验证。
4. `HIGH`：有完整证据才用精确测试集；`MEDIUM`：受影响测试 + 模块测试；`LOW`：扩大消费者/全验证集；CRITICAL 不因 HIGH confidence 就缩小。扫描脚本固定 LOW，由 Agent 补充分层证据后才能提升。
5. 将受影响行为对应到既有测试，按 [test-design.md](test-design.md) 找缺口、选输入与预期副作用，说明边界理由。局部任务在对话中即可；需要恢复或保存时写 test-plan.json，字段见 artifacts，按任务补 fixture/隔离、运行套件与适用约束；仅启用账本时引用依赖决策与授权。
6. 若使用已落盘计划，实施前校验 test-plan.json 及实际引用的产物；未落盘时按同样原则复核依据和断言，不创建空 JSON。校验问题只阻断依赖该产物的部分，其他任务继续；不能删 required 项或编造依据来消除错误。
7. 用户只要求计划时到此结束；要求补测试时在授权范围内继续实现、验证和归因。

`--staged` 的证据和实际执行工作树可能不同。若 unstaged 覆盖同文件，不把工作树测试冒充索引验证；使用经授权的隔离快照或清楚标识实际测试版本。不要自动 stash/drop 用户修改。

## implement

检查本次范围、预期依据、环境和授权；只有消费了持久计划或账本时才检查其状态与依赖。实现前记录 git status 与目标文件内容/哈希，避免覆盖并发修改。已有测试类/插件/fixture 可覆盖同一风险时先扩展，不新建重复资产。已有计划 ID 时关联产物，使用正常项目命名，内部状态不得写入产品接口。

生产代码修复条件：明确 Oracle + 正确测试 + 违反 Oracle 的证据。给最小建议 patch 和风险；有对应明确授权才应用。不能为方便测试擅自引入 Clock 或改接口；这同样是生产修改。

补丁验证失败时保留可审阅 diff；需要撤销只撤销本轮且未被他人改写的内容。禁止自动 git reset --hard / clean。交付列出修改文件、测试映射和剩余缺口。

## dry-run

dry-run 覆盖写入与执行步骤：不生成 artifact，也不为满足 `--require` 创建文件；在对话中注明计划尚未落盘校验。仅只读扫描和对话内展示：分析范围、拟改文件及具体原因、拟执行命令、待确认决策。不能创建 .smart-test、临时 fixture、构建产物、锁文件或启动容器。`state.py --dry-run` 可计算内存状态；inspect_repo.py 不写文件，不把输出重定向进仓库。dry-run 不授权外部执行。
