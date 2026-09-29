# 本地反馈导出

用户要求记录 Smart-Test 的误判、越权、策略错误或漏测时，使用本说明。反馈属于当前工作入口的辅助操作，不新增用户命令；不要每次运行都自动导出。

## 导出步骤

1. 保留异常现场。确认当时使用的 Smart-Test、宿主和工作入口；尽量在升级 skill 前导出。
2. 为输出选择目标项目之外的新目录。目录必须显式指定，不接受 `..`、符号链接、已存在目录或项目内部路径。
3. 使用已安装 skill 中的脚本，例如：

```text
python3 <skill-dir>/scripts/export_feedback.py --repo <java-repo> --output /private/tmp/smart-test-feedback-001 --host codex --workflow changes --feedback-type WRONG_STRATEGY
```

`--host` 为 `codex / claude-code / unknown`，`--workflow` 为六个正式入口之一。可提供 `--host-version 1.2.3`；仅接受数字版本，不运行宿主探测命令，不读取环境变量。未知版本省略后为 null。`--feedback-type` 可选值见脚本 `--help`，默认 OTHER。

4. 查看摘要的缺失与省略标记。必要的语义信息另用合成场景描述；不要改脚本以复制原始资料。人工复核后由用户自行带回 `smart_test`，创建 case 并关联修复和回归。

脚本只写显式输出目录及其缺失的父目录。它不修改目标项目或 `.smart-test`，不运行测试、构建、Git 命令、Docker 或网络请求，不上传数据。成功退出 0，拒绝导出或输入错误退出 2；失败信息不回显输入路径或原始 JSON。

## 包格式

固定输出以下十个 JSON 文件，均为新生成的摘要，不是原始 artifacts 的副本，不可回填为 Smart-Test 状态或当作新的验证证据：

| 文件 | 内容 |
|---|---|
| metadata.json | schema、Smart-Test 版本、可获得的 commit、宿主、宿主版本、入口、UTC 导出时间和导出限制 |
| feedback.json | 生成的反馈 id、日期、类型、版本、入口；场景、实际/期望行为、修复和回归初始为 null，root_cause 为 UNKNOWN，status 为 OPEN |
| project-profile.json | 固定技术栈信号和模块数量 |
| effective-context.json | 指令/决策/冲突/未知项数量及允许导出的布尔约束 |
| business-oracle.json | 依据数量、business_truth/characterization 数量、source/claim 缺失数量 |
| test-policy.json | 已知测试套件、覆盖率枚举与数字阈值、生产修改布尔边界 |
| test-plan.json | 包内条目编号、风险/套件枚举、required、断言数量和 Oracle 是否存在 |
| status.json | 固定状态枚举及 blocker 数量 |
| execution-summary.json | 已有执行摘要和 runs 下 manifest 的状态、计数、运行类型、退出码及报告组数量 |
| sanitized-change-summary.json | repository-evidence 中的变更类型、固定风险信号、重新编号后的路径 |

直接读取 `.smart-test/` 下同名 artifacts。变更摘要只读取 `repository-evidence.json` 的既有记录，不运行 Git，不重新扫描源码。执行摘要读取 `execution-summary.json` 及 `runs/<run-id>/manifest.json`，不读取 XML 或日志，不因导出而重新判定 PASS。产物可能陈旧，必须结合合成复现确认根因。

输入缺失记 MISSING；非法 JSON 或根结构记 INVALID_JSON / INVALID_ROOT；单文件超过 2 MB 记 OMITTED_TOO_LARGE。这些标记描述读取结果，不是项目验证结果。列表最多导出 1000 项，run 目录最多读取 100 项，并保留总数量；超出部分不代表不存在。

版本来自随安装包提供的 `version.json`。commit 优先使用包内记录；在 Smart-Test 源码 checkout 中可读取自身 HEAD，绝不读取目标 Java 仓库的 commit 或 remote。独立安装无法获得 commit 时为 null。checkout HEAD 不证明工作区未修改，metadata 会注明这一限制。导出版本是当前 exporter 的版本，不推断旧 artifacts 当时使用的版本；若已升级，case 中必须说明原版本未知或另附可靠版本记录。

## 脱敏边界

采用按字段重建的白名单，不对整个 JSON 做关键词替换。未知字段、自由文本、业务声明、断言内容、原始 id、类名、包名、模块名、命令参数、报告路径、stdout/stderr、URL、主机地址和账号均不复制。只输出固定枚举、布尔值、受限数值、派生数量及生成的编号。原始文件名替换为 `src/main/resources/file-0001.xml` 等通用路径，不输出可逆映射或原始路径的哈希。

不读取 `.env`、源码、完整 diff、数据库内容、环境变量或 Git remote；变更清单里的凭证文件沿用现有 `safe_name` 排除规则。路径逃逸、artifact 或输出路径上的符号链接、非普通输入文件会拒绝导出。包目录权限为 0700，文件为 0600（系统支持时）。

这会省略部分定位线索，是有意的取舍。导出包只能帮助发现状态和策略上的差异，不能独立证明业务规则、用户授权或真实执行结果。补充业务说明时继续人工脱敏；禁止因为 Agent 做错而降低回归期望。
