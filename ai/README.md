# AI 公共配置真源

本目录是三套 code agent（**codex / claude / opencode**）配置的唯一真源，解决"每个 agent 各维护一份 skill/mcp/plugin"的问题。

## 结构

```
ai/
  skills/                    # ★ 共享：自有 skill 单一真源（三套软链复用）
    git-commit/SKILL.md
  mcp/                       # ★ 共享：MCP 公共规范（单一真源）
    mcp-servers.json         #   所有 server 定义
    generate.mjs             #   生成器 → codex/claude/opencode 三套片段
    out/                     #   生成产物（gitignored）
  plugins/                   # ★ 共享：跨 agent 通用 plugin
    hindsight-hooks.ts
  codex/                     # codex 专属配置
    config.toml              #   codex 全量配置（含运行时字段，install 时手动 merge）
    hooks/                   #   codex 生命周期 hooks
    rules/                   #   codex 命令规则
    AGENTS.md                #   软链 → ../claude/CLAUDE.md（与 claude 共用指令）
  claude/                    # claude 专属配置
    CLAUDE.md                #   claude 通用指令
  opencode/                  # opencode 专属配置
    opencode.json            #   骨架（permission，无凭据）
    agents/                  #   opencode 通用 subagent
    commands/                #   opencode 自定义命令
  install.sh                 #   一键安装
  install-thirdparty.sh      #   第三方 skill/plugin 安装说明
```

## 设计原则

1. **单一真源**：skill 和 MCP 只维护一份；各 agent 专属配置收在同一 `ai/` 下按目录分区，不再散在仓库顶层。
2. **凭证不进仓**：`mcp-servers.json` 用 `{home}`（生成时替换为 `$HOME`）和 `{env:VAR}`（留给 opencode 展开）占位；opencode 凭据留在本机 `opencode.jsonc`（gitignored）。
3. **第三方不进仓**：lark-*、caveman 等第三方 skill 用 `npx skills` 从上游安装，避免仓库同步上游改动的负担。
4. **可迁移**：拉下来 `bash ai/install.sh` 即可用，不依赖某台机器的绝对路径。

## 安装

```bash
bash ai/install.sh            # skill 软链三套 + MCP 生成 + 各 agent 专属软链
bash ai/install-thirdparty.sh # 按需装第三方 skill/plugin
```

`install.sh` 处理内容：

| Agent | Skill | 专属配置 | MCP | Plugin |
|---|---|---|---|---|
| codex | `~/.codex/skills/`（软链） | hooks/rules/AGENTS.md 软链；config.toml 手动 merge | `codex-mcp.toml`（手并入 config.toml） | 原生（不共用） |
| claude | `~/.claude/skills/`（软链） | CLAUDE.md 软链 | `claude-mcp.json`（手并入 ~/.claude.json） | 原生（不共用） |
| opencode | `~/.agents/skills/` + `~/.config/opencode/skills` | opencode.json/agents/commands/plugins 软链 | `opencode-mcp.json`（install 自动并入 opencode.jsonc） | `~/.config/opencode/plugins/`（软链） |

> **config.toml 不软链**：codex config.toml 含本机运行时字段（`hooks.state`/`trusted_hash`），整文件软链会互相污染。install 时手动把 `ai/codex/config.toml` 的内容 merge 到 `~/.codex/config.toml`。pre-commit hook 会校验 `ai/codex/config.toml` 的严格语法。

## 修改流程

1. **改共享 skill**：直接改 `ai/skills/<name>/SKILL.md`，提交后各机器重新 install 即可（软链目标不变，内容实时跟随）。
2. **改 MCP**：编辑 `ai/mcp/mcp-servers.json` → 运行 `node ai/mcp/generate.mjs` 重新生成 → 把新片段并入各 agent 配置。
3. **加新 skill**：放入 `ai/skills/<name>/SKILL.md`，install.sh 自动软链到三套。
4. **改各 agent 专属**：直接改 `ai/<agent>/` 下对应文件。
5. **第三方 skill**：加到 `install-thirdparty.sh` 清单。

## 第三方 skill/plugin 清单

| 来源 | 用途 | 安装 |
|---|---|---|
| `larksuite/cli` | 飞书/Lark 全套 agent skills（lark-*） | `npx skills add larksuite/cli -g -y` |
| `vercel-labs/agent-skills` | 社区通用 skill 集合 | `npx skills add vercel-labs/agent-skills -g -y` |
| Standard Robots ONES | ONES 工作项处理 | 内部源，见 `~/.agents/skills/ones` |

opencode 第三方插件走 `plugin` 数组（见 `ai/opencode/opencode.json`），同样不入仓。

## 校验

```bash
opencode debug config        # opencode 合并配置是否正确
codex --strict-config exec   # codex 配置语法校验
npx skills list              # skill 是否已装
```
