# CI 候选与分项验证

## pipeline

先从用户目标、仓库已有构建/CI、适用测试约定和实际运行记录确定命令、套件与环境要求。没有 policy/plan/Oracle 文件不妨碍生成候选；已有适用要求仍须继承。Java/build 版本、Runner/网络/容器条件和 secret 引用分别记录来源，未知项明确列出。

本地缺数据库但需要借助 CI 验证时，可先生成草稿并标 `command_verification: NOT_VERIFIED`、`provider_execution: NOT_RUN`，列出未执行套件与环境前提。没有可信命令来源或必要业务选择未定时，只生成可确定部分并标明缺口，不捏造有效完整流水线。草稿不宣称已验证，也不绕过 finalize 前提。

生成或更新本次实际消费的结构化产物时，按 [artifacts.md](artifacts.md) 选择校验文件，不固定要求五类产物。输入结构错误先修复并重验；真实 BLOCKED 状态可用于生成带明确限制的草稿，不能把它改成 PASS 或复用陈旧 candidate 冒充有效结果。

没有指明 provider 时复用仓库已有 provider；没有 CI 且用户未指定时，先给候选选择及理由，未获授权不改正式位置。支持 GitHub Actions、GitLab CI；其他 provider 依据其现有约定生成并说明验证边界，不伪造 provider 已验证。

候选文件写 `.smart-test/ci-candidate/github-actions.yml` 或 `gitlab-ci.yml`，验证说明另存同目录 Markdown。随附来源命令与已有 run IDs（未执行时明确无 run）、工作树指纹、每个 job 的命令和 suite、runner 要求、secrets 名称、报告路径、状态。分别记录 `command_verification`、`syntax_validation`、`provider_execution`，使用 VERIFIED / FAILED / UNKNOWN / NOT_RUN / NOT_VERIFIED；不能用候选已生成代表任何验证完成。避免维护一个看似通用但未经执行的硬编码模板。

按实际需求映射：

| Gate | 常见触发 | 内容 |
|---|---|---|
| Fast | PR/commit | compile、unit、slice、已存在的静态检查和 changed coverage |
| Verification | merge candidate | 所需 integration、contract、关键 API flow |
| Deep | 手动/nightly/release | 明确要求的全回归、选择性 mutation 等 |

项目不需要三层时可少建；不要为补齐表格加入无依据的命令；尚未执行的必要命令保留来源与待验证标记。Maven verify 本身包含快速测试，解释重复执行的代价或复用单 job。仅缓存依赖，不缓存结果来绕过测试。

## pipeline verify

逐项记录 VERIFIED / FAILED / UNKNOWN，并引用证据：

1. 候选中的每条测试命令在相同代码/兼容环境中实际执行过；若修改参数、working-directory、profile/task、Java 版本，需要重新验证受影响部分。
2. 必需 suite 有独立新报告和正测试数量；integration 真正接入 Maven verify / Gradle task graph，没有 skip、NO-SOURCE 或未解释的 cache 命中。
3. 命令失败会传播为 job 失败。检查 shell pipe（尤其 tee）、`|| true`、continue-on-error、allow_failure、吞掉 exit code 的 wrapper。可在隔离临时测试中模拟非零子命令验证包装行为；不在正式业务中制造失败。
4. upload artifact 路径与真实报告一致，失败时也上传脱敏报告。coverage 文件、JUnit XML、Failsafe 的结果不能互相冒用。
5. 容器权限、Docker socket/daemon、网络、镜像版本、测试数据库版本、secret 引用、超时/cleanup 与 Runner 匹配。Docker-in-Docker/privileged runner 不是默认假设。GitLab services 与 Testcontainers 不能混淆。
6. 无硬编码密码/Token/生产 endpoint。使用 provider secret/env 机制，不把未知 secret 名称写成已配置。
7. YAML/provider 语法经可用工具校验；使用项目认可的 action/version 固定方式。检查 fork PR 的 secret 可用性和触发权限，不扩大 token 权限。

本地命令验证、YAML 语法验证、provider Runner 实跑是不同证据。未能接入 provider 时记 `provider_execution: NOT_RUN`，不能说 pipeline 已运行通过。candidate 可作为已验证本地命令的建议供 review；缺失的必要 Runner 能力仍是 finalize 阻塞。触发远端 workflow 必须在用户授权范围内。

## pipeline finalize

重新核查当前约定、验证版本、完整所需验证结果和 candidate checks；启用账本时同时核查决策。只有完整所需命令已在本地或等价 CI 环境验证、结构/语法检查通过、必要 Runner 能力有证据时，生成应用到现有 CI 的最小 patch，保留其他 job/trigger/secrets/权限/缓存设置；不覆盖整个原文件。标注 provider 实跑状态和剩余环境条件。

未满足前提时交付草稿及明确缺口，不能将 finalize 报告为已完成。默认交付 patch 与建议，不直接覆盖正式 CI。已有用户明确授权安装该已验证变更时应用补丁，并做相应检查；否则只在具体 patch 就绪后请求批准。用户拒绝后停止该方案。CI 内容、测试命令或前提发生变化，按受影响范围重新验证；启用账本时同时更新失效记录。为获得首次远端执行而安装草稿，必须有用户针对未验证候选及其范围的明确授权，保持未验证标记，不冒充 finalize 成功。
