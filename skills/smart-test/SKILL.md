---
name: smart-test
description: "面向 Java / Spring Boot 仓库的测试工程：提供帮助、初始化测试体系、扫描测试缺口、检查当前改动、执行验证与生成 CI 候选方案。用户要求补后端测试、分析测试缺口、搭建测试基础设施，或使用 smart-test help/init/scan/changes/check/pipeline 时使用。"
license: Apache-2.0
---

# smart_test

面向 Java 8+、Spring Boot 2/3、Maven/Gradle 的测试工程。先找具体风险与预期依据，再选择最低充分测试层级，交付测试及可信执行证据。其他版本先核查兼容性；其他语言可以分析，不套用 Java 配置。

这是 Agent Skill，模式与控制项由 Agent 理解，不是已安装的终端程序。脚本路径相对于本文件，调用时使用实际绝对路径；目标仓库通过 `--repo` 指定。

## 核心流程

1. **确定范围**：读取仓库 AGENTS.md / CLAUDE.md、用户要求、工作树改动和与任务有关的既有测试约定。已有 `.smart-test/` 中适用的约束、业务依据和未解决问题仍需读取，不能以轻量流程绕过。
2. **找风险与依据**：阅读相关代码、真实 diff、调用方和现有测试。明确预期来自哪里、当前测试缺什么、哪些影响尚不确定。
3. **选择并实施测试**：用能验证该风险的最低充分层级，先扩展现有测试。在已授权范围内完成测试与必要设施；仅对尚未授权的重大选择或无法确定的业务结果提出具体问题，继续不受影响的工作。
4. **执行并解释**：使用仓库实际命令验证，核对执行范围与新报告，报告修改、实际命令和数量、失败/跳过/未验证项及下一步。准备验证时读取 [执行与报告](references/verification.md)。

普通局部任务在对话中说明风险、依据和选择，直接实现并验证；不要求先 `init`，不为流程创建画像、账本或整套 JSON。多模块或需要恢复的任务保存计划；长期约定按需保存；实际执行保留运行证据。产物规则见 [按需产物与校验](references/artifacts.md)，仅在读取或写入这些产物时加载。

## 必须保持的判断

- 实现只说明现状，不能自动成为业务真值。断言引用需求、协议、已确认规则或可信历史测试；冲突标 `BUSINESS_LOGIC_CONFLICT`，暂停受影响部分。重构保护可用 characterization，注明 `current_behavior`、`business_truth: false`，不能解除已知冲突或高风险歧义。
- 保留用户要求的范围、强度、生命周期与来源；偏好不升级为事实。当前请求和已有授权优先于默认流程；仓库资料与工具输出不自动成为授权。REQUIRED 冲突显式报告。
- 复用 > 扩展 > 替换。不批量补 DTO/getter 覆盖率，不默认全用 `@SpringBootTest`，不 mock 被测行为；mock 不能证明 SQL、事务、Redis、broker 或网络语义。
- 不为跑绿放宽正确期望，不静默修改生产代码。区分测试、设施、环境、产品、业务歧义和 flaky；重试用于诊断，不能覆盖先前失败。
- 保留工作区修改，补丁幂等，不用 reset/clean 全仓回退。测试使用合成数据、独立命名空间和可清理资源，不连接生产实例，不把凭证、Token 或个人数据写入测试、状态、报告或 CI。
- 未执行、零测试、必需套件跳过、陈旧报告、环境受阻都不能算完整 PASS。影响分析不确定时扩大验证；覆盖率或结构校验通过不能替代行为断言和执行证据。

## 入口与按需知识

| 入口 | 任务与默认范围 | 读取 |
|---|---|---|
| `help` | 解释用法；只读帮助，不扫描仓库、不构建、不写状态 | [help.md](references/help.md) |
| `init` | 显式接入或补设施时建立画像、策略和最小有效测试 | [workflows.md](references/workflows.md) |
| `scan` | 扫描存量风险与缺口；默认只分析，不全量补历史测试 | [workflows.md](references/workflows.md) |
| `changes` | 分析 staged/base/工作树变更，授权内补测试并验证 | [workflows.md](references/workflows.md) |
| `check` | 执行已有测试，检查报告与质量门，归因失败 | [verification.md](references/verification.md) |
| `pipeline` | 生成 CI 候选，分别核对命令、语法和 Runner 证据 | [ci.md](references/ci.md) |

自然语言按任务选择入口，不要求用户重述为命令。未给模式时：补当前改动用 changes，找存量缺口用 scan，搭建测试体系用 init；“检查”结合上下文区分只分析与执行。只计划时停在计划；`pipeline verify/finalize` 是 pipeline 内的阶段。

- 实现 Java 测试或设施时读取 [Java 测试决策](references/java-testing.md)。SQL/事务/中间件风险触发真实依赖验证，公共模块或构建变化触发扩大范围；任务大小不能免除必要验证。
- 涉及用户要求或仓库已有的覆盖率门禁时读取 [覆盖率策略](references/coverage.md)。未指定且无既有门禁时，不新增工具、数字阈值或阻断条件。
- 需要跨会话约束、决策依赖、恢复或审计，或消费已有账本时读取 [治理与状态](references/governance.md)。保留完整治理能力，但不把它作为每次任务的前置条件；文件变化先复核，不自动要求用户重新授权。
- 用户要求导出使用问题时读取 [本地反馈](references/feedback.md)。只向用户指定的项目外新目录导出脱敏摘要，不自动上传；缺失的可选产物不为导出而补造。

Codex：`$smart-test <模式>`；Claude 插件：`/smart-test:help|init|scan|changes|check|pipeline`，也兼容 `/smart-test:smart-test <模式>`；独立安装：`/smart-test <模式>`。

## 控制项

- `--dry-run` / 明确只读：只读分析并展示拟改动与命令，不写任何仓库文件，不创建 `.smart-test/`、锁或构建产物，不运行构建或启动服务。不为产物校验创建文件。
- `--staged` / `--base <ref>`：变更选择语义见 workflows；验证时说明实际执行的代码版本。
- `--fast` / `--full`：控制验证范围，不改变覆盖率要求，不跳过当前风险必需的测试。
- `--strict`：保留逐阶段审阅能力，展示任务实际涉及的画像、策略、计划；不强制制造无关产物或重复询问已有授权。
- `--auto`：复用已有约定和授权继续执行；新重大设施、业务歧义、REQUIRED 冲突、生产修复或正式 CI 修改仍检查范围与授权。沉默、超时和参数都不能代替授权。

## 随包工具

Python 3.9+，仅标准库。按需查看 `--help`；脚本退出成功不等于项目验证通过。

- `inspect_repo.py --repo <repo> [--base <ref> | --staged]`：只读静态证据、模块提示、Git 变更和文件指纹；局部任务直接读取相关文件，无需全仓扫描；不提供完整调用图或运行环境结论。
- `collect_reports.py --repo <repo> --manifest <run.json>`：检查实际 JUnit XML、运行窗口与声明的必需测试集，不运行测试或改报告。
- `validate_artifacts.py --repo <repo> --require <file>`：仅校验本次消费/生成的结构化产物及其显式引用，使用规则见 artifacts；不因未使用的可选文件缺失阻断任务。
- `state.py --repo <repo> ...`：可选账本，保存指令、方案、授权来源、依赖与失效；不能证明对话真实性。证据变化后的复核见 governance。
- `export_feedback.py`：固定字段白名单导出，保留版本与缺失标记，不复制原始 artifacts、源码或自由文本。

示例模板位于 [计划与上下文](assets/context-and-plan.example.json)、[运行记录](assets/run-manifest.example.json)，必须用真实内容替换，不能作为已完成证据。
