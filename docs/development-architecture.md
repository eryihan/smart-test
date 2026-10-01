# smart_test 开发架构

本文件供维护者定位职责和修改位置。安装与使用见 [README](../README.md)，验证和分发见 [development.md](development.md)。

## 目标与默认路径

共用 skill 根据项目事实处理范围、行为与现有保护、测试选择/实施、原生执行和交付。搭建或全仓优化深入评估，局部任务只处理相关部分；用户与项目已有约束继续适用。具体运行规则由 [SKILL.md](../skills/smart-test/SKILL.md) 及其 references 维护。

## 职责边界

| 执行方 | 职责 | 限制 |
|---|---|---|
| Agent/提示词 | 业务依据、风险、测试边界、授权核对、失败归因、资料维护 | 源码不自动等于正确预期，自述不能证明授权 |
| 可选 Python 工具 | 静态事实查询、进程与报告采集、XML 计数/身份检查、白名单导出 | 不判业务充分性，工具通过不等于项目 PASS |
| 项目原生设施 | 编译、测试发现、真实依赖验证、CI | 结果限定于实际版本、范围、配置与环境 |
| 项目长期资料 | 生效约定、当前未完成事项、必要验证依据 | 按需生成、有限留存，历史不承担日常状态计算 |

测试、fixture、构建、项目脚本与正式 CI 从交付起脱离安装目录运行。辅助工具独立于项目登记；记录需求不改变执行授权。

## 工具

- `inspect_repo.py` 查询范围内的静态事实；Maven effective model、Gradle 动态逻辑和业务含义由 Agent 核查。调用见 [范围发现](../skills/smart-test/references/workflows.md#repository-discovery--doctor)。
- `execute.py` 采集原生命令、时间、退出码/终止原因、声明的报告与证据变化。互斥防报告覆盖，POSIX 终止进程组，快照按需保存。调用见 [执行与证据](../skills/smart-test/references/verification.md#执行与证据)。
- `collect_reports.py` 读取报告；有真实 manifest 才检查执行窗口、分组与身份，直接读报告时 freshness 为 UNKNOWN。调用同见执行与证据。
- `export_feedback.py` 导出白名单版本与运行摘要；现场文本反馈无需附件。调用见 [诊断附件](../skills/smart-test/references/feedback.md#可选诊断附件)。
- `common.py` / `catalog.py` 提供路径边界、原子写入、Git 和枚举，没有独立流程。
- `tools/` 提供本地安装与可复现打包，不进入业务项目的测试执行路径。

## 文档归属

| 内容 | 修改位置 | 读取时机 |
|---|---|---|
| 安装与首次使用 | [README.md](../README.md) | 用户初次接触项目 |
| 触发描述、共用判断、按需路由 | [SKILL.md](../skills/smart-test/SKILL.md) | 宿主发现和调用 skill |
| 入口用法与结果解释 | [help.md](../skills/smart-test/references/help.md) | 用户询问帮助 |
| 用例设计、Java 实施、执行、覆盖率、CI | [专项导航](../skills/smart-test/SKILL.md#入口与按需知识) | 任务涉及相应能力 |
| 项目资料的保存、更新与清理 | [artifacts.md](../skills/smart-test/references/artifacts.md) | 资料发生变化或需要接续 |
| 工具职责与扩展边界 | 本文件 | 修改实现或组织文档 |
| 本地验证、安装、打包与发布 | [development.md](development.md) | 开发和分发 |
| 现场反馈与维护者回归处理 | [现场反馈](../skills/smart-test/references/feedback.md)、[维护者回归](../feedback/README.md) | 整理反馈或修复实际问题 |

安装包内的资料不得依赖包外 docs；所有专项从 SKILL.md 可直接找到。commands/ 只转发入口，不复制工作流程。跨文档需要同一规则时，用短说明和链接定位详细规则，避免各自维护一套。

项目约定、当前事项与必要证据的机制由 [artifacts.md](../skills/smart-test/references/artifacts.md) 维护；本文件不再重复具体留存与状态规则。新增文件或工具应有实际消费者，不为凑齐目录结构添加空文件。

## 验证和分发

工具回归验证确定性实现；宿主验收观察实际调用、diff、产物与最终结论。evals 是场景清单，未执行不能当作通过证据。验证范围与 fixture 用法见 [开发验证](development.md#开发验证)。

各宿主共用源码。内容版本同步 skill/plugin，安装更新保护来源与定制；分发方式见 [目录与分发方式](development.md#目录与分发方式)。

组织方式参考 [OpenAI skill 文档](https://learn.chatgpt.com/docs/build-skills)和 [Anthropic 编写指南](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices)：入口保留共用判断，条件细节按需读取，脚本承担确定性操作。
