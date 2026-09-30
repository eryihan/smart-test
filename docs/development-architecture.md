# smart_test 开发架构

用户操作：[随包帮助](../skills/smart-test/references/help.md)。开发与分发：[development.md](development.md)。

## 产品任务与执行边界

smart_test 通过兼容 Agent Skills 的宿主完成后端测试接入、缺口分析、变更补测试、运行诊断和 CI 候选。当前专项实现为 Java/Spring。入口包括 help、init、scan、changes、check、pipeline 和 update，控制项由 Agent 解释执行。局部任务无需先 init；update 仅维护 skill。

| 执行方 | 职责 | 验证边界 |
|---|---|---|
| 宿主 Agent | 核对范围与业务规则，评估已有测试，选择边界，修改测试，执行命令并归因 | 核验依据与授权；源码、工具提示和结构校验不能作为业务真值 |
| 标准库 Python 工具 | 静态仓库证据、结构与引用检查、JUnit 执行窗口、可选账本、反馈摘要 | 不生成完整调用图，不执行 Java 测试；业务正确性与授权真实性由 Agent 核验 |
| 目标项目设施 | 编译、测试发现与执行，依赖行为验证，原生报告 | 结果限定于实际版本、配置、环境和断言范围 |

Agent 将需求或变更关联到业务行为，再评估现有输入、断言与真实边界，优先补强已有测试。数据库、事务和 broker 语义使用真实依赖；远程替身仅验证本服务客户端处理。

## 宿主与技术栈适配

共通流程负责业务测试方法与证据判定；技术栈专项负责运行时、构建、框架和真实依赖接入；宿主负责安装、调用、权限与更新。Java 为当前专项实现。

新增语言须用实际项目验证选型、测试发现、执行和报告，再补专项章节或 reference。优先复用已有配置，选型记录能力与代价；无 JUnit XML 时由 Agent 核对原生报告，禁止伪造结果。

各宿主共用 skill 目录；agents/openai.yaml 和 commands/ 提供宿主适配。其他 Agent 显式指定安装目录，反馈使用 host=other。目录兼容、技能发现和端到端执行分别验证。

## 知识组织

SKILL.md 保存共同原则与路由。详细规则按职责维护：

| 职责 | 维护位置 |
|---|---|
| 范围发现、init/scan/changes、只读行为 | workflows.md |
| 用例推导、已有测试评估、测试边界和断言 | test-design.md |
| Java/BOM、Maven/Gradle、Spring、SQL/事务与隔离 | java-testing.md |
| 基线、执行、阶段结果、失败定位与受阻动作 | verification.md |
| 覆盖率模式、分母、阈值和基线 | coverage.md |
| 产物位置、JSON 格式及校验范围 | artifacts.md |
| 指令作用域、决策依赖、授权记录与失效 | governance.md |
| CI 候选、分项验证及应用 | ci.md |
| 用户操作与 skill 更新 | help.md |
| 本地反馈导出 | feedback.md |

扫描读取工作流与设计；Java 实施读取技术章节与验证；执行已有测试先读取验证。覆盖率、CI、账本和反馈按任务加载。runtime reference 不得引用安装包外的维护者 docs。

算法、字段和状态判定由对应文档定义，入口保留必要边界。SQL、事务、HTTP、MQ 按 Java 场景章节组织；专项形成独立操作路径时再拆分。

## 辅助工具与兼容

- inspect_repo.py：读取 Git 变更、构建与源码候选、Mapper XML、迁移及指纹。模块影响为静态提示；不解析 Maven effective model、Gradle 动态代码、运行时 wiring 或符号图。Gradle 仅解析根 settings 的字面量 include 与 file projectDir 映射，未知部分需扩大验证。
- validate_artifacts.py：检查实际依赖的五类项目 JSON。可选文件缺失不阻断任务；允许合法 UNKNOWN/BLOCKED。增量策略须有基线；阈值支持数值或 overall/incremental 对象。真实 commit、源码映射及业务依据由 Agent 核验。
- collect_reports.py：检查 manifest 对应的 JUnit 文件、执行窗口、模块分组、必需测试身份、失败和跳过。Git HEAD、工作树指纹与版本匹配由 Agent 核验；EVIDENCE_PASS 仅为局部证据结果。
- state.py：原子 JSON 账本，保存指令、决策、事件、依赖与指纹。证据变化复核后可保留授权；语义变化按依赖重评。授权真实性由宿主核验。
- export_feedback.py：向用户指定的项目外新目录导出白名单摘要，不复制源码、原始业务文本或日志，不上传。

继承适用策略、计划和账本，保持状态 schema 与决策生命周期兼容。update 独立于业务阶段和治理产物。

## 运行数据与工作区

局部分析和计划可在对话中完成。长期 policy、可恢复 plan 与跨会话 ledger 按需保存；实际执行后保留 run 证据，status 从证据派生。

只读任务不创建文件、锁、fixture 或构建产物。实施时保留未提交修改；代码、依赖或测试配置变化后重验受影响范围。环境缺失仅阻断依赖动作；业务预期未知则暂停相关断言和修复。处理规则见 verification。

## 迭代与验证

围绕具体任务修改方法与工具；新增配置、脚本或文件须对应实际缺口。

分别验证辅助工具、真实 Java 测试和宿主行为。检查测试能否揭露目标错误、是否复用已有资产、实际执行范围及剩余缺口。错误变体仅用于隔离 fixture，禁止在用户业务仓库制造缺陷。

tests/ 保存工具回归，evals/evals.json 保存宿主场景，evals/fixtures 保存原始输入。运行记录包含命令、版本、diff 和结果；未执行项保持未验证。

## 安装与维护资料

各宿主共用 skills/smart-test 源码；Claude commands/ 转发入口。独立安装与 zip 包仅包含 skill 目录；架构和开发资料随 Git 维护。带日期的评审与验收仅记录历史证据。

update 复用宿主更新能力；独立目录采用候选校验、完整备份与替换。version.json 的 source 为默认候选渠道，用户指定来源与实际安装记录优先。操作见随包帮助。

版本、清单、安装、打包和发布见 development.md。发布与远端 CI 状态以实际执行记录为准。
