# 本地开发、离线安装与发布

日常使用按 [README](../README.md) 通过宿主安装。本页用于维护源码、调试和无法联网时的手动分发。

## 目录与分发方式

```text
.claude-plugin/
  marketplace.json          Claude Code 安装源，插件 source 指向仓库根目录
  plugin.json               插件名称、版本和描述
skills/smart-test/
  SKILL.md                  Codex 与 Claude Code 共用的 skill
  agents/openai.yaml        Codex 界面元数据
  references/
  scripts/
  assets/
tools/                      本地安装与打包工具
tests/                      辅助脚本回归测试
```

Codex 的 skill-installer 下载 `skills/smart-test`。Claude Code 从市场找到仓库根目录的插件，再自动发现 `skills/smart-test/SKILL.md`。只有一份技能源码，不复制、不用符号链接，也不需要 MCP 服务或安装钩子。

Claude 的插件调用是 `/smart-test:smart-test`；独立安装到 `.claude/skills` 时调用是 `/smart-test`。这两个名字来自宿主的命名规则。避免两种形式同时安装，导致同一技能出现两份。

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

进入会话后调用 `/smart-test:smart-test init --dry-run`。完整行为验收见 [acceptance.md](acceptance.md)。`plugin validate` 验证清单，不能替代实际安装和 skill 加载检查。

## 本地脚本安装

安装器保留用于源码开发、显式自定义目录和离线环境，不作为普通用户的推荐入口：

```bash
python3 tools/install_skill.py --host codex
python3 tools/install_skill.py --host claude
```

默认写入 `~/.codex/skills/smart-test` 或 `~/.claude/skills/smart-test`。可用 `--dest <skills-directory>` 指定实际安装父目录；项目级安装使用 `--scope project --project <absolute-project-path>`，分别写入 `.agents/skills` 和 `.claude/skills`。

`--dry-run` 不写文件；相同内容重复安装返回 UNCHANGED；不同内容默认不覆盖。`--replace` 将旧目录备份到技能发现目录之外，并在输出中给出位置。恢复时移走新版本再放回备份，不覆盖备份中的本地修改。

## 离线分发

```bash
python3 tools/build_package.py
```

产物是 `dist/smart-test.zip` 及其 SHA-256 文件，压缩包中只包含独立 skill 的 `smart-test/` 目录。复制到宿主 skills 目录后，Codex 调用 `$smart-test`，Claude 的独立 skill 调用 `/smart-test`。该压缩包不是 Claude 插件市场包。

`dist/` 不提交到 Git。Claude 原生插件分发直接使用仓库中的 `.claude-plugin/` 和 `skills/`，无需用户运行打包脚本。

## 发布更新

1. 修改共用 skill 源码，完成相关测试及清单验证。
2. Claude 插件内容更新时，增加 `.claude-plugin/plugin.json` 的 `version`；市场条目不重复声明版本，避免两处不一致。版本未变可能导致宿主继续使用缓存。
3. 提交并推送到市场跟踪的 `main`。已有 Claude 用户通过市场刷新与插件更新获取新版本；Codex 独立 skill 使用 README 中的更新请求。
4. 在隔离配置中验证实际安装、技能发现和卸载，确认安装文档对应的远端内容可用。不要只凭清单格式正确就报告安装成功。

本仓库没有自动向 Anthropic 或 OpenAI 官方目录提交条目。使用的是官方支持的分发机制，安装源由本仓库维护。
