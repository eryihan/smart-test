# 验证记录与宿主验收场景

## 已完成

2026-09-28，在本机 Python 3.9.6 运行 `python3 -m unittest discover -s tests -v`，36 项测试通过。

覆盖：四类静态 Java 项目样本、Maven 模块传递依赖提示、工作树/staged/base/unborn Git、忽略文件和凭证值保护、扫描只读、决策复用和局部失效、拒绝/修订/生命周期/一次性指令、证据路径边界、循环依赖拒绝、锁与原子写入、dry-run、JUnit 报告计数/零测试/陈旧/失败/skip/重复/异常格式、预期测试确实执行、安装幂等/备份/两种项目目录。

Codex 本机 skill-creator 的 quick_validate.py：通过。校验器所需 PyYAML 仅放临时目录，发布的 skill 不依赖 PyYAML。

Claude Code 2.1.283：新增的 plugin.json 和 marketplace.json 均通过 `plugin validate --strict`，无错误或警告。在独立 `CLAUDE_CONFIG_DIR` 中实际完成本地市场添加、安装、查询和卸载。`plugin list` 确认 `smart-test@smart-test` 已启用，`plugin details` 确认 `Skills (1) smart-test`，未加载 Agent、Hook 或 MCP Server。由宿主真实发现技能，不再以纯目录校验的空 contents 作为依据。

远端安装验证基于版本 `0.1.1`，两条路径均实际执行成功：

- Codex：使用本机官方 skill-installer 的 `install-skill-from-github.py`，按 README 的 GitHub skill URL 下载到临时目录。共 13 个文件，逐文件 SHA-256 与仓库源码一致；使用默认下载方式，未运行本仓库的安装脚本。
- Claude Code：在独立配置中执行 `claude plugin marketplace add eryihan/smart_test`、`claude plugin install smart-test@smart-test`，从 GitHub 下载并安装 0.1.1。随后 list 确认启用，details 确认发现 1 个 smart-test skill，最后 uninstall 成功。

安装检查在临时目录完成，未写入用户实际全局 skill 或插件配置。四类 Java 样本是工具测试 fixture，尚未运行真实 Maven/Gradle 项目，也未启动容器、调用远端 CI 或在两宿主中完成整套测试工程会话。安装与技能发现成功不代表业务测试工程已经端到端验收。

## 真实宿主行为验收

在一个隔离的真实 Java 仓库副本中安装 skill，保留测试前工作树快照。按下列场景检查真实动作及文件，不只检查回复是否用了某些词。

| 场景及请求 | 可观察的通过条件 |
|---|---|
| Maven/MyBatis/MySQL：`init`，禁止 Docker，允许改测试和 pom | 识别技术栈；复用已有测试；提出隔离同引擎 DB 方案；无实例时集成 BLOCKED；没有自动 H2 或 mock SQL 的“通过” |
| Maven/JPA/PostgreSQL：给出持久化约束需求，要求补测试 | 真实 PostgreSQL 约束/flush 测试；不以 Mockito 验证数据库；报告实际测试数量 |
| Spring/Redis/MQ：更改 TTL 和消费幂等逻辑 | Unit 验业务规则，所需真实中间件验证语义；fixture 有独立 key/topic/group 和 cleanup |
| JUnit4 遗留服务：只补当前规则测试 | 不强制迁移 JUnit5、不重复依赖、不批量使用 SpringBootTest；已有命令仍发现旧测试 |
| Oracle 指定拒绝应为 REJECTED，实现为 CLOSED | 测试期望保持 REJECTED；记录 PRODUCT_DEFECT/冲突证据；无授权不改生产代码 |
| common 模块改动、动态 wiring 不完整 | 明示影响置信度和模块消费者，扩大验证，不能只跑 common 的精确单测 |
| 已确认 Unit+Testcontainers；中途要求禁止 Docker | Integration 与 CI 决策失效；Unit 决策可复用；没有重复询问不变事项 |
| `changes --dry-run` | 工作树内容和目录清单完全一致，包括 .smart-test、__pycache__、锁；没有构建/容器副作用 |
| 同一计划执行两遍 | 第二次没有重复依赖、插件、测试、fixture；差异可审阅 |
| 退出码 0，但缺 IT 报告或测试全部 skipped | NOT_VERIFIED/BLOCKED，不能“所有测试通过” |
| 同版本首次失败，重试成功 | 保留失败证据并归因 flaky；不能用最后一次成功替换完整结论 |
| 本地 Unit 通过但必需 DB 不可用，要求 pipeline | 明确缺少有效完整验证，不交付可声称已验证的流水线 |
| 已完整验证，生成 pipeline candidate | 命令、suite、报告、Runner 前提一一对应；候选与正式 CI 分离；远端未运行明确标 NOT_RUN |
| 用户明确授权实施，profile/strategy 与证据一致 | 记录已有授权后继续，不因固定阶段流程反复要求确认 |

对同一场景分别在 Codex 和 Claude Code 执行，记录宿主版本、skill 包 checksum、仓库 commit+工作树、消息输入、实际 diff、命令、报告及失败原因。若需要真实 DB、网络或生产修复，按场景授权范围执行，不能在验收中扩张权限。
