# 治理、项目记忆与决策复用

## 存储约定

V1 使用 UTF-8 JSON，避免在 Codex/Claude Code 所在环境额外安装 YAML 依赖。设计稿中的 YAML 文件名在本实现映射成同名 JSON；业务含义不变。指令、决策和确认事件合并在一个原子更新的 `state.json`，防止多文件只写入一半。

```text
.smart-test/
  state.json                   # state.py 管理：directives、decisions、events
  repository-evidence.json     # inspect_repo.py 输出，不是已确认事实
  project-profile.json         # Agent 核实后的画像与证据
  business-oracle.json          # 业务依据、冲突、characterization 边界
  effective-context.json       # 本次生效约束及其来源
  test-strategy.json
  test-policy.json
  test-debt.json
  test-plan.json
  status.json                  # 分析/实施/验证的阶段状态，不能替代决策账本
  runs/<run-id>/manifest.json  # 实际运行记录及报告快照
  reports/                    # 用户可读的 Markdown 报告
  ci-candidate/               # CI 文件、验证记录、建议 patch
```

仓库已使用设计稿 YAML 时，先复用其内容，不静默覆盖或合并两个互相冲突的账本。只有用户同意统一存储格式时，迁移并保留原文件。不要把初始模板的默认值视为仓库事实。

`.smart-test/` 不应存秘密和未经清洗的日志。检查现有 ignore 规则，向用户建议共享 policy/strategy/oracle，忽略运行日志和临时报告；不擅自改 Git 全局配置。所有证据附路径/行号/版本或用户陈述来源。

## Human Directive

每条至少包含下列字段：

```json
{
  "id": "DIR-NO-DOCKER",
  "category": "technical",
  "level": "REQUIRED",
  "statement": "禁止使用 Docker",
  "source": "当前用户消息：禁止使用 Docker",
  "scope": {"test_type": ["integration"]},
  "lifecycle": "PROJECT",
  "binding": {},
  "topics": ["database-environment", "integration-strategy"],
  "status": "ACTIVE"
}
```

分类：business / technical / scope / execution / preference。强度：REQUIRED / PREFERRED / ADVISORY。scope 可含 module、path、test_type、phase，值为数组；空对象代表整个适用生命周期，不代表自动授权全部修改。

生命周期与绑定：

| lifecycle | binding | 何时使用 |
|---|---|---|
| PROJECT | `{}` | 项目持续要求 |
| SESSION | `{"session":"实际会话标识"}` | 仅当前会话 |
| CHANGE | `{"change":"实际变更标识"}` | 本次变更；HEAD SHA 不足以识别脏工作树 |
| PHASE | `{"phase":"verify"}` | 指定阶段 |
| ONE_TIME | `{"session":"实际会话标识"}` | 使用后显式 consume，失败未执行时不消费 |

SESSION/CHANGE/ONE_TIME 必须绑定稳定的实际标识；跨会话不能自动沿用。`state.py context` 按 binding 筛选候选，Agent 还需判断 scope 的交集，生成真正的 Effective Context。不能直接把所有 ACTIVE 指令应用于全部模块。

用户业务陈述同时进入 Oracle；技术偏好不进入 Oracle。指令与已验证事实冲突时保留两边证据，标记 `DIRECTIVE_FACT_CONFLICT`，确认是否有环境差异；不能把 PostgreSQL 驱动的证据改成 MySQL。

优先级：宿主安全边界 → 当前明确 REQUIRED → 已确认 Oracle → 项目 REQUIRED → 仓库事实 → policy → recommendation → default。优先级决定行动约束，不能改变客观事实。两条无法同时满足的 REQUIRED、同优先级冲突、Oracle 冲突必须明确提出，暂停依赖该冲突的部分。

## Proposal 与 Approval

proposal 的固定输入字段：id、kind、summary、topics（非空）、evidence_paths、depends_on。细节放策略或计划文件，加入 evidence_paths；脚本记录文件指纹，确保批准的是具体内容。

```json
{
  "id": "DEC-INTEGRATION",
  "kind": "test_strategy",
  "summary": "数据库验证采用已授权的隔离 MySQL 8.0 测试实例；不使用 Docker",
  "topics": ["database-environment", "integration-strategy"],
  "evidence_paths": ["pom.xml", ".smart-test/test-strategy.json"],
  "depends_on": ["DEC-PROFILE"]
}
```

只有 depends_on 指向 EFFECTIVE 决策时才可提出下游方案。没有依赖时用 `[]`。不要让每个决策依赖整个 state.json、整个项目目录或每次都会更新的报告，否则会造成无关失效。按 unit/integration/CI 等实际边界拆分策略，依赖尽量细。

```text
python3 <skill-dir>/scripts/state.py --repo <repo> init
python3 <skill-dir>/scripts/state.py --repo <repo> directive --input <directive.json>
python3 <skill-dir>/scripts/state.py --repo <repo> propose --input <proposal.json>
python3 <skill-dir>/scripts/state.py --repo <repo> resolve --id DEC-PROFILE --action confirm --source user --evidence <实际用户授权来源>
python3 <skill-dir>/scripts/state.py --repo <repo> reconcile
python3 <skill-dir>/scripts/state.py --repo <repo> context --session <session-id> --change <change-id> --phase verify
python3 <skill-dir>/scripts/state.py --repo <repo> context --module order --path src/main/java/order --test-type integration --phase verify
```

`context` 提供 module/path/test_type/phase 时，脚本对 directive scope 做确定性匹配：同一字段内为 OR，不同字段之间为 AND；path 使用仓库相对路径和 glob。缺少 scope 所需上下文时返回 `unresolved_directives`，不默认套用。自然语言到模块、路径和测试类型的映射，以及多个 directive 的语义冲突，仍由 Agent 判断。

`--source human-directive` 用于用户已经明确指定的选择；`--source policy` 仅用于已生效 policy 覆盖的普通决策。不得编造来源或自称“用户已确认”。脚本不能验证对话真实性，来源核验由宿主 Agent 承担。

首次画像和策略、重大技术变化、高风险且业务依据待确认的计划、新增高影响基础设施、生产修复和正式 CI 修改，先检查是否已有足够授权。没有时先完成只读分析、生成具体 proposal / patch，再一次性询问需要用户决定的事项。用户明确要求实施、且涵盖相关选择时，记录授权并继续，不额外设置一轮仪式性确认。

`confirm`：PROPOSED → EFFECTIVE，保存授权及当时文件指纹。`modify`：PROPOSED → REVISED，按用户修改重写具体文件再 propose。`reject`：PROPOSED → REJECTED，不继续该方案。拒绝不是运行失败，不能通过重试绕过。

## Invalidation

- `reconcile` 检测每个决策 evidence_paths 的新增、删除、内容变化，使对应决策及传递依赖变为 INVALIDATED。
- 新/改/禁用 directive 按 topics 使相交决策及下游失效。topic 必须语义一致，例如 `database-environment`、`integration-strategy`、`unit-strategy`、`oracle:approval-status`。脚本对 topic 只做精确匹配，Agent 负责选对 topic 和遗漏检查。
- 新文件、外部环境变化、Oracle 补充等不一定在已记录路径中：重新检查扫描差异，显式执行 `invalidate --topics ... --reason ...`。不能把“指纹没变”当成所有前提未变。
- directive scope 更精确时脚本可能保守地多失效同 topic 决策；Agent 可以拆细 topic。不可为了减少重算而漏掉真实依赖。
- 不覆盖旧授权：重新 propose 产生版本，events 保留前一版本。重新获得有效授权后才可复用。用户同意旧方案不代表同意改变后的新方案。

只读 `status` 会在返回值中计算失效但不写磁盘；实际实施前调用 `reconcile` 持久化。`--dry-run` 必须放在子命令之前，连 `.smart-test/` 和锁文件都不创建。并发写入遇锁立即失败，不删除他人的锁；异常退出后先核实进程再清理遗留锁。

## 阶段状态与解释

`status.json` 为每阶段保存 status、artifact、blocking_ids、decision_ids、updated_at。可用：NOT_STARTED / PROPOSED / READY / PARTIAL / BLOCKED / FAILED / PASS / STALE。READY 只表示该阶段输入齐备，不能代替验证 PASS。

`explain` 追踪：风险 → Oracle → directives → 选择层级的原因 → 决策版本及授权 → 测试/命令 → 结果与未覆盖项。`approval list` 读取 PROPOSED/REVISED；无须虚构单独 CLI。最终允许多阶段并行处于不同状态，不用一个 READY 掩盖 integration 阻塞。
