# 本地开发、离线安装与发布

宿主安装见 [README](../README.md)。

## 目录与分发方式

```text
.claude-plugin/
  marketplace.json          Claude Code 安装源，插件 source 指向仓库根目录
  plugin.json               插件名称、版本和描述
skills/smart-test/
  SKILL.md                  各兼容宿主共用的 skill
  agents/openai.yaml        Codex 界面元数据
  references/
  scripts/
  assets/
tools/                      本地安装与打包工具
tests/                      辅助脚本回归测试
```

兼容 Agent Skills 的宿主加载完整 `skills/smart-test`。Codex 的 skill-installer 下载该目录；Claude Code 从市场找到根目录插件，再发现共用 skill。其他 Agent 用原生安装功能或显式指定目录。只有一份核心源码，不需要 MCP 服务或安装钩子。

Claude 插件提供 `/smart-test:help|init|scan|changes|check|pipeline|update`，也兼容 `/smart-test:smart-test <模式>`；独立安装调用 `/smart-test <模式>`。两种形式同时安装会重复发现技能。

## 开发验证

```bash
git clone https://github.com/eryihan/smart_test.git
cd smart_test
python3 -m unittest discover -s tests -v
claude plugin validate --strict .claude-plugin/plugin.json
claude plugin validate --strict .claude-plugin/marketplace.json
```

在目标测试项目中，可以临时加载本地插件检查技能发现，无需加入个人市场：

```bash
claude --plugin-dir /absolute/path/to/smart_test
```

进入会话后调用 `/smart-test:smart-test init --dry-run`。行为场景见 [evals/evals.json](../evals/evals.json)，fixture 位于 evals/fixtures。记录输入、diff、命令与结果；清单校验、工具回归、fixture 测试和宿主行为分别验收。

使用 skill-creator 的 `scripts/quick_validate.py skills/smart-test` 校验 frontmatter，校验器依赖 PyYAML；skill 工具仅依赖 Python 标准库。检查本地链接和独立安装，runtime reference 不得引用包外 docs。

## 本地脚本安装

源码开发、自定义目录或离线安装：

```bash
python3 tools/install_skill.py --host codex
python3 tools/install_skill.py --host claude
python3 tools/install_skill.py --dest <Agent-skills-directory>
```

默认写入 `~/.codex/skills/smart-test` 或 `~/.claude/skills/smart-test`。可用 `--dest <skills-directory>` 指定实际安装父目录；项目级安装使用 `--scope project --project <absolute-project-path>`，分别写入 `.agents/skills` 和 `.claude/skills`。

`--host` 仅为 Codex/Claude 提供已知目录默认值；传入 `--dest` 后可以省略它。`--host generic` 必须给 `--dest`，不会猜其他宿主的用户或项目路径。

`--dry-run` 不写文件；相同内容重复安装返回 UNCHANGED；不同内容默认不覆盖。`--replace` 将旧目录备份到技能发现目录之外，并在输出中给出位置。恢复时移走新版本再放回备份，不覆盖备份中的本地修改。

## 离线分发

```bash
python3 tools/build_package.py
```

产物是 `dist/smart-test.zip` 及其 SHA-256 文件，压缩包中只包含独立 skill 的 `smart-test/` 目录。复制到宿主 skills 目录后，Codex 调用 `$smart-test`，Claude 的独立 skill 调用 `/smart-test`。Claude 插件通过市场分发。

其他宿主按原生方式调用。逐宿主验证技能发现、重载和执行。

`dist/` 不提交到 Git。Claude 原生插件分发直接使用仓库中的 `.claude-plugin/` 和 `skills/`，无需用户运行打包脚本。

## 发布更新

1. 修改共用 skill 源码，完成相关测试及清单验证。
2. 内容更新时同步增加 `.claude-plugin/plugin.json` 与 `skills/smart-test/version.json` 的版本，用于宿主缓存和反馈溯源；fork/自定义渠道同时维护 source，宿主安装记录仍优先。市场条目不重复声明版本，回归检查包版本与插件版本一致。
3. 提交并推送到市场跟踪的 `main`。已有 Claude 用户通过市场刷新与插件更新获取新版本；Codex 独立 skill 使用 README 中的更新请求。
4. 在隔离配置中验证实际安装、技能发现和卸载，确认安装文档对应的远端内容可用。核对实际安装内容与技能发现结果。

本仓库没有自动向 Anthropic 或 OpenAI 官方目录提交条目。使用的是官方支持的分发机制，安装源由本仓库维护。
