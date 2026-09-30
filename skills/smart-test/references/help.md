# smart_test 使用指南

`help` 按主题返回用法；未指定主题时展示入口与流程。仅读取帮助，不扫描项目、不构建、不写文件。

## 调用方式

Codex：

```text
$smart-test help
$smart-test help coverage
```

Claude Code：

```text
/smart-test:help
/smart-test:init
/smart-test:scan
/smart-test:changes
/smart-test:check
/smart-test:pipeline
/smart-test:update
/smart-test:smart-test help
/smart-test:smart-test help pipeline
```

Claude 插件提供模式命令，兼容 `/smart-test:smart-test <模式>`。其他兼容 Agent Skills 的宿主加载同一目录，使用原生调用方式和安装路径。也可直接请求“用 smart-test 分析这个后端项目”或“更新 smart-test”。

当前专项实现为 Java/Spring、Maven/Gradle。其他语言使用通用设计与选型方法，专项接入尚待验证。文件或命令能力受限时列出未完成范围。

也可以直接提问，例如“smart_test 如何判断增量覆盖率？”或“我只想查看当前改动，不执行测试”。

## 工作入口

| 入口 | 用途 | 默认行为 |
|---|---|---|
| `help` | 查看入口、参数、产物和边界 | 只读，不写文件，不执行构建 |
| `init` | 评估现有框架，建立测试策略并补必要设施 | 显式搭建时使用；复用兼容框架，以真实发现和执行验证接入 |
| `scan` | 将业务行为与已有输入、断言对应，找缺口并排序 | 默认分析全仓，不一次性补完历史债务 |
| `changes` | 分析当前变更并补充相关测试 | 读取工作树、staged 或指定基线的变更 |
| `check` | 执行测试、收集报告、判断验证结果 | 只执行已有构建配置能证明的测试 |
| `pipeline` | 生成并检查 CI 候选，区分草稿与已验证结果 | 默认输出候选和 patch，不直接改正式 CI |
| `update` | 更新已安装的 smart-test | 通过原安装渠道，保护本地定制；不扫描后端项目或运行测试 |

按任务直接选择：补当前改动用 `changes`，运行验证用 `check`，了解存量缺口用 `scan`，搭建测试体系用 `init`，接入 CI 用 `pipeline`。普通任务不要求先 init。`pipeline verify` 和 `pipeline finalize` 是 pipeline 内的阶段。

## 常用控制项

- `--dry-run`：只分析并展示计划，不创建状态、不改代码、不执行构建或启动服务。
- `--staged`：只分析暂存区变更。
- `--base <ref>`：以指定分支或提交的共同祖先分析到当前工作树。
- `--fast`：执行当前风险所需的最小充分验证集；不能据此声称全量验证通过。
- `--full`：扩大到相关模块或完整验证集；不自动引入项目没有要求的工具。
- `--strict`：逐阶段展示本次任务涉及的画像、策略和计划；不强制创建无关产物。
- `--auto`：复用既有约定和授权继续处理；新重大选择超出授权或出现业务歧义时，说明具体待定事项。

控制项由 Agent 解释执行，用户明确要求优先。

## 覆盖率

未指定覆盖率时沿用仓库门禁，不新增工具或阈值。在 `init`、`changes` 或 `check` 中可指定：

- 只报告覆盖率，不设置阻断阈值；
- 指定某个模块或仓库的整体行覆盖率阈值；
- 以某个分支、提交或 merge-base 为基线，指定增量行覆盖率阈值；
- 同时要求整体和增量覆盖率。

整体覆盖率按可执行项总数汇总；增量覆盖率只计算新增或修改的可执行代码行。没有可执行变更行记为 `NOT_APPLICABLE`；基线、源码映射或报告不可靠记为 `UNKNOWN`。`--fast`、`--full` 只改变测试执行范围，不改变覆盖率模式。详细规则见 [coverage.md](coverage.md)。

## 结果和产物

结果包括 `PASS`、`PARTIAL`、`BLOCKED`、`NOT_VERIFIED`、`UNKNOWN` 和 `NOT_APPLICABLE`。未执行、陈旧报告、环境不可用或业务依据不明均不满足完整通过条件。

报告列出保护的行为、补强或新增的测试、实际命令、失败原因及未验证范围。判定见 [verification.md](verification.md#阶段结果)；VALID/EVIDENCE_PASS 仅为辅助工具结果。

局部任务直接分析风险、补测试并验证。计划、约定和账本按用户要求、复用、恢复或审计需要保存；实际执行保留运行证据，继承适用约束。

结构化产物按实际依赖校验。BLOCKED 计划可交付；业务预期未知时暂停相关断言，环境缺失时继续有依据的测试实现。规则见 [按需产物与校验](artifacts.md) 和 [受阻工作](verification.md#受阻工作)。

产物写入 `.smart-test/`，兼容原有格式。长期约定使用 policy，可恢复任务使用 plan，运行证据使用 runs；目录与字段见 [artifacts.md](artifacts.md)。

没有本地集成环境时可生成待验证 CI 草稿，保留未运行套件、Runner 前提和 NOT_RUN/NOT_VERIFIED 标记。finalize 仍要求本地或等价 CI 环境的完整执行证据和候选检查。

长期约束、决策依赖或审计使用可选的 state.json 账本。文件变化先复核；决策和原授权仍适用的保留授权，技术选择或用户要求变化则重评相关部分。

状态文件不应写入密码、Token、生产连接信息或真实个人数据。测试代码放在目标项目已有的测试目录中。

## 测试边界

先复用项目已有的框架、版本和构建命令。纯 Unit 通常可独立执行；SQL、Redis 或 broker 语义使用相应隔离服务。远程客户端可连接可控替身验证本服务的解析、超时和错误处理，但不能据此证明真实 provider 的实现。环境不可用时保留未验证范围。

业务预期须有可追溯依据，源码仅用于定位当前行为。业务冲突与高风险歧义需先查证；生产代码和正式 CI 修改需明确授权。

## 典型请求

```text
$smart-test init --dry-run
$smart-test scan
$smart-test changes --base origin/main
$smart-test check --fast
$smart-test pipeline
```

也可以用自然语言描述范围，例如“只检查 order 模块”“不要修改生产代码”“本轮只生成计划”“本次只报告覆盖率”。

可直接给出业务规则：“金额不能超过额度，拒绝后不能新增申请”“分页必须隔离租户，不能因 JOIN 重复订单”“第二步写入失败时，第一步也必须回滚”。规则缺失时列出具体未知项。

## 反馈

发现策略错误、误判或范围问题时，在当前对话中要求导出本地脱敏反馈，并指定项目外的新目录。按 [本地反馈导出](feedback.md) 处理，不自动上传；反馈包不含源码和原始业务描述，人工复核后带回 smart_test 仓库追踪修复与回归。仅查看帮助不执行导出。

## 更新 skill

用户可直接说“更新 smart-test”，也可按宿主调用：

```text
Codex:       $smart-test update
Claude 插件: /smart-test:update
独立 skill:  按宿主的调用方式请求 smart-test update
```

update 仅更新 skill，不改目标项目的测试框架、依赖、源码或 `.smart-test/`。`help update` 返回用法；`update --dry-run` 读取本地版本与来源并列出动作，不下载、不刷新缓存、不写文件。

执行 update 时：

1. 确认实际加载路径、version.json 和安装范围。用户指定来源与宿主管理记录优先，包内 source 仅作默认候选。保留 fork、私有源、分支和固定版本；来源冲突时列出差异并确认渠道。
2. 从原来源获取候选到临时目录，核对名称、版本、必要文件和引用。不自动降级；版本与文件均一致才判定无需更新，同版本内容变化仍须核对。
3. 用可靠旧基线识别本地定制；无基线时标明未知并完整备份。已知定制先给保留或合并方案，覆盖需授权。更新范围明确且无待定选择时直接继续。
4. 使用原宿主管理器，保留范围与 ID，禁止手工修改管理器缓存。独立目录先校验候选，再将旧目录备份到技能发现目录之外并替换；失败恢复旧目录。
5. 核对磁盘版本与文件，记录更新前后版本、来源、备份和重载状态。离线、权限受限或管理器失败时保留旧版本，报告已完成步骤。重载或新会话后确认宿主实际加载版本。

Claude 默认市场安装示例：

```bash
claude plugin marketplace update smart-test
claude plugin update smart-test@smart-test
```

Codex 的 skill-installer 拒绝覆盖已有目录。先校验候选并备份旧目录，再按原来源安装，失败恢复；其他独立安装采用目录替换。源码/离线安装器的 `--replace` 会备份旧目录，执行前仍须检查定制。

旧版缺少 update 时，直接请求 Agent 更新或使用原管理器升级。用户获取的是已发布内容。参考：[Agent Skills](https://agentskills.io/specification)、[Claude 插件更新](https://code.claude.com/docs/en/discover-plugins#keep-plugins-updated)。
