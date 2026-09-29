# Java / Spring 测试选择与实现

## 风险与最低充分层级

| 风险 | 优先层级 | 需要证明的内容 |
|---|---|---|
| 纯规则、金额边界、状态机、业务分支 | Unit | 输入、输出、错误和状态转换来自 Oracle |
| Controller 参数、序列化、错误码、权限映射 | MVC/WebFlux slice | 合法/非法输入、认证授权、响应契约 |
| Service 的外部调用编排 | Unit + 客户端边界测试 | 超时、重试策略、错误映射、幂等；只 mock 外部依赖 |
| SQL/MyBatis/JPA、约束、排序、JSON/timezone | 同引擎数据库 integration | 实际 SQL、mapping、flush/commit、约束 |
| Spring 事务、事件、代理和回滚 | Spring + DB integration | 多步写入后失败，实际数据库状态及事务边界 |
| Redis TTL/原子操作/Lua/序列化/锁 | Redis integration | 服务端语义、过期、竞争、隔离 key |
| MQ 序列化和 broker 行为 | Component / integration | 发布、消费、重投、去重、ack；独立验证消费者规则 |
| 独立部署服务的兼容性 | Contract（确有 consumer/provider 边界时） | 字段、错误、版本兼容；双方验证能力 |
| 关键跨组件完整路径 | 小量 API/E2E | 核心成功与最重要失败路径 |
| 已稳定且确定性的 HIGH/CRITICAL 规则 | 可选 PIT | 现有断言能发现有效变异，不针对 DTO/生成代码 |

SQL 不能用 `verify(mapper).update()` 验证；事务不能仅用 mock 验证。不要固定单测/集成/E2E 比例。Slice 是否适用取决于加载边界，不能以“更快”为理由把必须的依赖排除掉。

## 框架兼容

- 先读 parent/BOM、Java target、wrapper 和已有依赖，复用项目管理的版本。不要给未知 Spring Boot 项目硬插最新 JUnit、Mockito、Testcontainers。Boot 2 的 javax 与 Boot 3 的 jakarta、Java 版本要求不可混用。
- 已有 JUnit4/TestNG 优先扩展；迁移需明确理由。存在 junit-jupiter API 不代表 engine 或构建插件能发现测试，必须运行并看报告。
- Spring Boot test starter 通常已管理 JUnit/Mockito/AssertJ，先查实际依赖，不重复引入。使用框架对应版本支持的 mock bean API，不照搬不同代际注解。
- Unit 可用 Mockito 隔离外部依赖、Clock、Repository abstraction；不 mock SUT。既有断言库能表达行为就复用。
- `@WebMvcTest` / `@WebFluxTest` 用于对应 web 技术栈；安全过滤器和错误处理必须覆盖所需风险，不为通过测试禁用安全。
- `@DataJpaTest` 要核查数据库替换行为；用真实 DB 时配置禁止替换。MyBatis slice 依赖项目实际 starter 能力，否则采用受控 Spring integration。
- 仅在需要完整上下文时用 `@SpringBootTest`，API 测试使用随机端口。Boot 3.1+ 可考虑 `@ServiceConnection`，低版本用其支持的动态属性方式；以仓库版本为准。

## Maven

先读 Surefire/Failsafe、profiles、includes/excludes、skip 标志和 argLine。Surefire 常用 `*Test` 等默认模式；integration 常用 `*IT`，但现有约定优先。

Failsafe 必须绑定 integration-test 和 verify 两个 goal，`mvn verify` 才是最终集成验证命令，不能只跑 `integration-test`。确认 IT 不被 Surefire 和 Failsafe 重复运行，也未被两者同时排除。单独跑 test 不能证明 Failsafe 配置有效。

优先使用现有可信 `./mvnw`；无 wrapper 才使用已安装 mvn。多模块按实际 reactor 依赖使用 `-pl` / `-am`，核实消费者也被选中。`-Dtest=...` 在没有该类的依赖模块可能报错，不能全局关闭 no-tests 失败来掩盖错误选择。

JaCoCo 复用已管理版本和 argLine（含其他 agent）。测试 agent 与 report/check phase 分开核查。只展示实际生成的 coverage；没有报告记 UNKNOWN，不写 0 或估计值。

## Gradle

复用 `test`、已有 custom SourceSet / JVM test suite / integrationTest task 及 dependency configuration，检查 test framework 和 `useJUnitPlatform()` 的适用性。Kotlin/Groovy DSL 分别处理。不要为了采用某个 DSL 重构已有成熟结构。

`check` 未必包含 integrationTest，显式核查 task dependency；存在 task 名不代表执行了测试。UP-TO-DATE、FROM-CACHE 或 NO-SOURCE 要辨明；需要新证据时在授权范围内选择 `--rerun-tasks`，不可拿旧 XML 证明本轮真实执行。

CI 的报告通常在 `build/test-results/<task>/TEST-*.xml`，多模块路径带模块前缀。测试缓存/构建缓存不能把失败变成功。

## 数据库、中间件与隔离

与生产同类且兼容版本的引擎；MySQL 特性不能以 H2 通过代替。Docker/Testcontainers 仅在策略允许、daemon/镜像/网络可用时使用。禁用 Docker 时可以提出专用测试实例方案；确认实例非生产、权限受限、schema/DB/namespace 独立、cleanup 可行。两种方案都不可用则报告 integration BLOCKED，继续不依赖它的工作。

测试不能硬编码生产连接串。通过 test profile 和环境变量引用测试凭证，不在命令参数或报告中输出其值。合成数据、小 fixture、每次唯一业务 key、固定时钟/种子、可清理资源；固定 sleep 换条件等待及有上限 timeout。

Migration 变更至少计划：空库初始化、代表性旧 schema 升级、应用启动/关键 SQL、约束/索引。既有迁移可能不可变，不能改生产 migration 来修测试。

事务回滚要在正确边界外读真实状态，避免测试框架自带 rollback 掩盖应用提交/回滚错误。JPA 在必要时 flush/clear；异步事件、新事务、自调用绕过代理均需专门推理。

Redis 用独立 key prefix；不能 FLUSHALL 共享实例。MQ 用独立 topic/queue/group，处理最终一致和消费确认。不要对生产或共享企业环境做破坏性清理。

## 测试质量

以行为命名，沿用项目风格；AAA 可读即可，不强塞注释。每测试聚焦一条主要行为，用强断言验证结果/错误/状态/必要副作用。不要只 assertNotNull，也不要用过度 verify 锁死实现细节。exception/assertThrows、契约工具断言等均可能有效，不能靠关键字判断“无断言”。

检查无断言、弱断言、mock SUT、重复风险、共享可变 fixture、时间/随机数、固定端口、执行顺序、并发和外部网络。这些是复核提示，不是自动判 bug 的 linter。生产注入 Clock/IdGenerator 属于生产修改，遵守授权边界。

Pact/PIT 都按风险与实际兼容性选用，不是 init 必装项。不得宣称模拟 HTTP 响应等同于 provider contract 验证。

## 技术参考

- [Spring Boot testing](https://docs.spring.io/spring-boot/reference/testing/index.html)
- [Testcontainers](https://java.testcontainers.org/quickstart/junit_5_quickstart/)
- [Surefire](https://maven.apache.org/surefire/maven-surefire-plugin/) / [Failsafe](https://maven.apache.org/surefire/maven-failsafe-plugin/)
- [Gradle Java testing](https://docs.gradle.org/current/userguide/java_testing.html)
- [JaCoCo](https://www.jacoco.org/jacoco/trunk/doc/maven.html) / [Pact](https://docs.pact.io/) / [PIT](https://pitest.org/quickstart/maven/)

选择与仓库版本对应的文档；这里的链接不替代版本兼容检查。
