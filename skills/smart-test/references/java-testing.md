# Java / Spring 测试实现

适用于 Java 框架接入、构建配置和测试实现。行为、用例与边界选择见 [test-design.md](test-design.md)。

## 框架选型与兼容

首次接入、缺少可用测试框架或用户要求评估选型时，先读项目约定、parent/BOM、Java 编译目标与测试运行时、构建工具版本、已有依赖和代表性测试。已有选型依据仍适用时直接复用。

| 项目现状 | 推荐方式 |
|---|---|
| 已有框架且能满足本次测试需要 | 保留并核对兼容性、测试发现、执行结果和可复用设施；JUnit4/TestNG 使用同一标准 |
| 已有部分设施，但缺少所需能力 | 指出具体缺口，只补 engine、构建插件配置或所需测试工具；集成环境缺失单独处理 |
| 没有测试框架 | Spring Boot 项目优先考虑该版本配套的 test starter 与依赖管理；非 Boot 项目可优先考虑兼容 Java 和构建工具的 JUnit Jupiter。按需补断言/Mock 工具，并明确测试发现配置与执行命令；纯 Java 测试不为接入框架引入 Spring |

在当前回复或已有策略中记录项目依据、推荐组合、待补设施和未验证项。用户未要求对比且现有方案能满足需求时，不另列替代框架；确需替换时说明具体限制与迁移、共存、维护代价。数据库等专项工具按 [测试边界](test-design.md#选择测试边界) 选择，不随基础框架一并安装。

版本优先复用项目管理；需要新增或覆盖时核对相应版本的官方文档，不直接使用最新大版本，也不为回归 BOM 默认值而撤销已有有效配置。Boot 2 的 javax 与 Boot 3 的 jakarta、Java 版本要求不可混用。Starter 已提供的依赖不重复声明；使用框架对应版本支持的 mock bean API，不照搬不同代际注解。

核对 engine 与运行配置；仅有 Jupiter API 无法证明测试可执行。接入后用有业务断言的代表性测试核对发现、执行和报告数量。只读或无法执行时交付方案、拟验证命令及未运行状态。

- Unit 可用 Mockito 隔离外部依赖、Clock、Repository abstraction；不 mock SUT。既有断言库能表达行为就复用。
- `@WebMvcTest` / `@WebFluxTest` 用于对应 web 技术栈；安全过滤器和错误处理必须覆盖所需风险，不为通过测试禁用安全。
- `@DataJpaTest` 要核查数据库替换行为；用真实 DB 时配置禁止替换。MyBatis slice 依赖项目实际 starter 能力，否则采用受控 Spring integration。
- 仅在需要完整上下文时用 `@SpringBootTest`，API 测试使用随机端口。Boot 3.1+ 可考虑 `@ServiceConnection`，低版本用其支持的动态属性方式；以仓库版本为准。

## Maven

先读 Surefire/Failsafe、profiles、includes/excludes、skip 标志和 argLine。Surefire 常用 `*Test` 等默认模式；integration 常用 `*IT`，但现有约定优先。

Failsafe 必须绑定 integration-test 和 verify 两个 goal，`mvn verify` 才是最终集成验证命令，不能只跑 `integration-test`。确认 IT 不被 Surefire 和 Failsafe 重复运行，也未被两者同时排除。Failsafe 配置需通过 verify 验证。

优先使用现有可信 `./mvnw`；无 wrapper 才使用已安装 mvn。多模块按实际 reactor 依赖使用 `-pl` / `-am`，核实消费者也被选中。`-Dtest=...` 在没有该类的依赖模块可能报错，不能全局关闭 no-tests 失败来掩盖错误选择。

JaCoCo 复用已管理版本和 argLine（含其他 agent）。测试 agent 与 report/check phase 分开核查。覆盖率范围、阈值和基线按 [coverage.md](coverage.md) 记录；只展示实际生成的 coverage，没有报告记 UNKNOWN，不写 0 或估计值。

## Gradle

复用 `test`、已有 custom SourceSet / JVM test suite / integrationTest task 及 dependency configuration，检查 test framework 和 `useJUnitPlatform()` 的适用性。Kotlin/Groovy DSL 分别处理。不要为了采用某个 DSL 重构已有成熟结构。

`check` 未必包含 integrationTest，显式核查 task dependency；测试执行以新报告为准。UP-TO-DATE、FROM-CACHE 或 NO-SOURCE 要辨明；需要新证据时在授权范围内选择 `--rerun-tasks`，不可拿旧 XML 证明本轮真实执行。

CI 的报告通常在 `build/test-results/<task>/TEST-*.xml`，多模块路径带模块前缀。失败结果不得由缓存命中覆盖。

## 环境与数据隔离

与生产同类且兼容版本的引擎；MySQL 特性不能以 H2 通过代替。Docker/Testcontainers 仅在策略允许、daemon/镜像/网络可用时使用。禁用 Docker 时可以提出专用测试实例方案；确认实例非生产、权限受限、schema/DB/namespace 独立、cleanup 可行。两种方案都不可用则报告 integration BLOCKED，继续不依赖它的工作。

测试不能硬编码生产连接串。通过 test profile 和环境变量引用测试凭证，不在命令参数或报告中输出其值。合成数据、小 fixture、每次唯一业务 key、固定时钟/种子、可清理资源；固定 sleep 换条件等待及有上限 timeout。

Redis 用独立 key prefix；不能 FLUSHALL 共享实例。MQ 用独立 topic/queue/group，处理最终一致和消费确认。不要对生产或共享企业环境做破坏性清理。

## 服务级组件边界

服务组件测试从实际 Spring bean 进入，保留所需事务代理、内部规则、Mapper/Repository 和真实数据库。外部系统在客户端边界使用可控替身；验证超时/响应解析时让真实客户端参与，不能只 mock 一个业务接口返回异常。需要 web 路由或过滤器证据时，再选 slice/API，避免默认加载全应用。

例如创建订单：写订单、扣库存，再调用外部支付。根据已确认协议，分别在库存不足、支付拒绝或支付结果未知处制造失败，观察订单/库存和后续通知。组件测试可证明本服务处理；跨系统补偿或支付方协议需要另外的边界证据，本地 DB 回滚不撤销远端已发生的副作用。

## SQL / MyBatis / JPA

先读真实 Mapper XML/注解、实体 mapping、schema 与迁移；查明返回的是订单还是明细、tenant/filter 条件、排序、分页和受影响行语义。复用项目同类数据库与现有迁移创建 schema，避免自建的简化表恰好避开实际约束。

使用能区分正确与错误查询的小 fixture：

| 查询风险 | 最小数据与断言 |
|---|---|
| JOIN 放大结果 | 一个目标订单有两条明细，另一个目标订单有一条；查询订单列表时按约定断言唯一订单 ID、总数与页面边界，不能只检查非空 |
| 过滤遗漏 | 放入另一租户和被排除状态的数据，断言它们不出现；租户/状态条件与业务约定核对 |
| 不稳定分页 | 使用相同排序时间、不同主键的数据；仅当接口约定稳定次序时核对排序键及跨页无重叠/遗漏，不自造排序契约 |
| 动态 SQL | 按实际可选过滤器验证无条件、单条件与关键组合；null/空集合的语义先确认 |
| 写入与约束 | 断言字段、受影响行和真实约束；拒绝后检查无残留写入，不能只 verify mapper 调用 |

例如已确认“租户 T1 的 PAID 订单按 created_at、id 排序”：fixture 包含 T1/PAID 的 O1、O2，T1/CANCELLED 的 O3 与 T2/PAID 的 O4；O1 两条明细、O2 一条。断言结果恰为 O1、O2，分页与计数一致；JOIN 漏去重、漏租户或漏状态条件都应被对应断言揭露。未知的空明细处理需单独确认。

JPA 写入在需要证明数据库约束或 SQL 已发出时 flush；读取持久化结果时 clear 或使用独立事务/连接，避免一级缓存只回显内存对象。MyBatis 则调用真实映射并从数据库读回字段。方言、时间精度、JSON、collation 等仅在相关变更出现时选取用例。

## 应用事务与失败回滚

先查实际事务入口、代理是否生效、事务管理器、传播行为及异常回滚规则。直接 new Service、自调用绕过代理、只测 mock 均不能证明 Spring 事务。构造第一步确已写入、第二步可控失败的路径，失败后从事务外检查持久状态，同时执行成功路径，确认写入确实发生。

| 场景 | 观察边界 |
|---|---|
| 同一事务内多步写入失败 | 从真实 bean 调用，外部读取订单/库存均符合约定的回滚结果 |
| 测试方法自带事务 | 避免它替代应用事务；用不包裹测试事务的用例或明确结束测试事务后观察，不以自动 rollback 证明应用回滚 |
| 新事务、异步或提交后事件 | 分别观察其独立提交与失败行为；不能预设跟随调用方回滚 |
| API 随机端口调用 | 请求线程的事务独立于测试线程；显式清理已提交数据，不指望测试方法回滚清理服务端写入 |

对线程超时机制检查是否在别的线程执行，防止测试事务失去作用；使用项目支持的 API。flush/clear 可帮助发现 ORM 假通过，但不能替代应用事务边界验证。[Spring 测试事务](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/tx.html)、[Spring Boot 应用测试](https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html)。

## 迁移与执行成本

Migration 变更按风险验证空库初始化、带代表性旧数据的 schema 升级、应用启动/关键 SQL、约束和索引；既有迁移可能不可变，不能改生产 migration 来修测试。新旧版本共存是否需要兼容由部署约定决定。

先复用相同测试配置、容器和小 fixture；只在确需修改上下文时使用相应重建机制，不给每个测试加 DirtiesContext。并行前确认数据/key/queue 和端口隔离，容器/线程/客户端按生命周期释放。慢测试先区分构建、上下文启动、数据准备、等待与实际测试耗时，再调整相应部分；不能以降低必需边界换取运行速度。

生产注入 Clock/IdGenerator 属于生产修改，遵守授权边界。断言与共通确定性方法见 [test-design.md](test-design.md#断言与维护成本)。

## 技术参考

- [Spring Boot testing](https://docs.spring.io/spring-boot/reference/testing/index.html)
- [JUnit](https://docs.junit.org/current/user-guide/)
- [Testcontainers](https://java.testcontainers.org/quickstart/junit_5_quickstart/)
- [Surefire](https://maven.apache.org/surefire/maven-surefire-plugin/) / [Failsafe](https://maven.apache.org/surefire/maven-failsafe-plugin/)
- [Gradle Java testing](https://docs.gradle.org/current/userguide/java_testing.html)
- [JaCoCo](https://www.jacoco.org/jacoco/trunk/doc/maven.html) / [Pact](https://docs.pact.io/) / [PIT](https://pitest.org/quickstart/maven/)

选择与仓库版本对应的文档；核对 API 与依赖兼容性。
