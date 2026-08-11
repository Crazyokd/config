# AI 公共配置真源

本目录是三套 code agent（**codex / claude / opencode**）共享配置的唯一真源，解决"每个 agent 各维护一份 skill/mcp/plugin"的问题。

## 结构

```
ai/
  skills/                    # ★ 自有 skill 单一真源（三套共用）
    git-commit/SKILL.md
  mcp/
    mcp-servers.json         # ★ MCP 公共规范（单一真源）
    generate.mjs             #   生成器 → codex/claude/opencode 三套片段
    out/                     #   生成产物（gitignored）
  plugins/
    hindsight-hooks.ts       #   通用 plugin（opencode TS 生态）
  opencode/
    opencode.json            #   opencode 骨架（codegraph MCP + 权限，无凭据）
    agents/                  #   opencode 通用 subagent
    commands/                #   opencode 自定义命令
  install.sh                 #   一键安装：skill 软链三套 + MCP 生成 + opencode 软链
  install-thirdparty.sh      #   第三方 skill/plugin 安装说明
```

## 设计原则

1. **单一真源**：skill 和 MCP 只维护一份，分发到各 agent。
2. **凭证不进仓**：`mcp-servers.json` 用 `{home}`（生成时替换为 `$HOME`）和 `{env:VAR}`（留给 opencode 展开）占位；opencode 凭据留在本机 `opencode.jsonc`（gitignored）。
3. **第三方不进仓**：lark-*、caveman 等第三方 skill 用 `npx skills` 从上游安装，避免仓库同步上游改动的负担。
4. **可迁移**：拉下来 `bash ai/install.sh` 即可用，不依赖某台机器的绝对路径。

## 安装

```bash
bash ai/install.sh            # 软链 skill 三套 + 生成 MCP + opencode 骨架
bash ai/install-thirdparty.sh # 按需装第三方 skill/plugin
```

`install.sh` 生成/软链的内容：

| Agent | Skill | MCP | Plugin |
|---|---|---|---|
| codex | `~/.codex/skills/`（软链） | `codex-mcp.toml`（手并入 config.toml） | 原生（不共用） |
| claude | `~/.claude/skills/`（软链） | `claude-mcp.json`（手并入 ~/.claude.json） | 原生（不共用） |
| opencode | `~/.agents/skills/` + `~/.config/opencode/skills` | `opencode-mcp.json`（并入配置） | `~/.config/opencode/plugins/`（软链） |

## 修改流程

1. **改 skill**：直接改 `ai/skills/<name>/SKILL.md`，提交后各机器 `bash ai/install.sh` 重新软链即可（软链目标不变，内容实时跟随）。
2. **改 MCP**：编辑 `ai/mcp/mcp-servers.json` → 运行 `node ai/mcp/generate.mjs` 重新生成 → 把新片段并入各 agent 配置。
3. **加新 skill**：放入 `ai/skills/<name>/SKILL.md`，install.sh 自动软链到三套。
4. **第三方 skill**：加到 `install-thirdparty.sh` 清单。

## 第三方 skill/plugin 清单

| 来源 | 用途 | 安装 |
|---|---|---|
| `larksuite/cli` | 飞书/Lark 全套 agent skills（lark-*） | `npx skills add larksuite/cli -g -y` |
| `vercel-labs/agent-skills` | 社区通用 skill 集合 | `npx skills add vercel-labs/agent-skills -g -y` |
| Standard Robots ONES | ONES 工作项处理 | 内部源，见 `~/.agents/skills/ones` |

opencode 第三方插件走 `plugin` 数组（见 `opencode.json`），同样不入仓。

## 校验

```bash
opencode debug config        # opencode 合并配置是否正确
npx skills list              # skill 是否已装
```
