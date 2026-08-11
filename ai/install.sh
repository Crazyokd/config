#!/usr/bin/env bash
# 一键安装 ai/ 公共真源到本机三套 code agent（codex / claude / opencode）
#
# 功能：
#   1. 软链 ai/skills/ 下自有 skill 到三套 agent 的 skills 目录
#   2. 运行 MCP 生成器，把公共 MCP 片段合并进各 agent 配置
#   3. 软链 ai/opencode/ 骨架到 ~/.config/opencode/
#   4. 软链 codex/claude 专属配置（CLAUDE.md / hooks / rules / AGENTS.md）
#   5. 生成本机 opencode.jsonc（凭据覆盖，gitignored；已存在则跳过）
#
# 第三方 skill/plugin 见 install-thirdparty.sh。
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
AI_DIR="${REPO_DIR}/ai"
OPENCODE_DEST="${XDG_CONFIG_HOME:-$HOME/.config}/opencode"

echo "==> ai/ 真源: ${AI_DIR}"
echo "==> opencode 目标: ${OPENCODE_DEST}"

link() {
  local src="$1" dst="$2"
  if [ -e "$dst" ] || [ -L "$dst" ]; then
    echo "    [skip] ${dst} 已存在"
  else
    mkdir -p "$(dirname "$dst")"
    ln -s "$src" "$dst"
    echo "    [link] ${dst} -> ${src}"
  fi
}

# ---------- 1. 软链自有 skill 到三套目录 ----------
echo "==> 软链自有 skill 到三套 agent"
if [ -d "${AI_DIR}/skills" ]; then
  for skill_dir in "${AI_DIR}"/skills/*/; do
    [ -d "$skill_dir" ] || continue
    skill_name="$(basename "$skill_dir")"
    link "$skill_dir" "${HOME}/.agents/skills/${skill_name}"
    link "$skill_dir" "${HOME}/.codex/skills/${skill_name}"
    link "$skill_dir" "${HOME}/.claude/skills/${skill_name}"
  done
fi

# ---------- 2. MCP 公共规范生成 + 合并 ----------
echo "==> 生成 MCP 配置片段"
if command -v node >/dev/null 2>&1 && [ -f "${AI_DIR}/mcp/generate.mjs" ]; then
  MCP_OUT="${AI_DIR}/mcp/out"
  ( cd "${AI_DIR}/mcp" && node generate.mjs --out-dir "${MCP_OUT}" >/dev/null )
  echo "    生成到 ${MCP_OUT}/"
  echo "    == opencode 片段将在步骤 4 自动并入 opencode.jsonc =="
  echo "    == codex: 请把 codex-mcp.toml 并入 ~/.codex/config.toml =="
  echo "    == claude: 请把 claude-mcp.json 并入 ~/.claude.json 的 mcpServers =="
else
  echo "    [warn] 未找到 node 或 generate.mjs，跳过 MCP 生成"
fi

# ---------- 3. opencode 骨架软链 ----------
mkdir -p "${OPENCODE_DEST}"

echo "==> opencode 骨架软链"
link "${AI_DIR}/opencode/opencode.json" "${OPENCODE_DEST}/opencode.json"
link "${AI_DIR}/opencode/agents"        "${OPENCODE_DEST}/agents"
link "${AI_DIR}/opencode/commands"      "${OPENCODE_DEST}/commands"
link "${AI_DIR}/plugins"                "${OPENCODE_DEST}/plugins"

# ---------- 4. codex / claude 专属配置软链 ----------
echo "==> codex 专属配置软链"
link "${AI_DIR}/codex/hooks"       "${HOME}/.codex/hooks"
link "${AI_DIR}/codex/rules"       "${HOME}/.codex/rules"
link "${AI_DIR}/codex/AGENTS.md"   "${HOME}/.codex/AGENTS.md"
echo "    == codex config.toml 含本机运行时字段（hooks.state/trusted_hash），"
echo "       不自动软链；请手动 merge ai/codex/config.toml 到 ~/.codex/config.toml =="

echo "==> claude 专属配置软链"
link "${AI_DIR}/claude/CLAUDE.md"  "${HOME}/.claude/CLAUDE.md"

# ---------- 5. 本机 opencode.jsonc 凭据 + MCP 合并模板 ----------
JSONC="${OPENCODE_DEST}/opencode.jsonc"
MCP_JSON="${AI_DIR}/mcp/out/opencode-mcp.json"
if [ -f "$JSONC" ]; then
  echo "==> ${JSONC} 已存在，保留不动（如需重新生成先删除它）"
else
  echo "==> 生成 ${JSONC}（凭据 + 生成的 MCP 片段，请填入本机凭据）"
  if [ -f "$MCP_JSON" ]; then
    python3 - "$JSONC" "$MCP_JSON" <<'PYEOF'
import json
import sys

jsonc_path, mcp_json_path = sys.argv[1], sys.argv[2]
mcp = json.load(open(mcp_json_path))

config = {
    "$schema": "https://opencode.ai/config.json",
    "mcp": mcp,
    "provider": {
        "devai": {
            "npm": "@ai-sdk/openai-compatible",
            "options": {
                "baseURL": "http://dev.ai.sr/v1",
                "apiKey": "REPLACE_ME",
            },
        },
    },
}
with open(jsonc_path, "w", encoding="utf-8") as fh:
    json.dump(config, fh, indent=2, ensure_ascii=False)
    fh.write("\n")
PYEOF
  else
    cat > "$JSONC" <<'EOF'
{
  "$schema": "https://opencode.ai/config.json",
  "provider": {
    "devai": {
      "npm": "@ai-sdk/openai-compatible",
      "options": {
        "baseURL": "http://dev.ai.sr/v1",
        "apiKey": "REPLACE_ME"
      }
    }
  }
}
EOF
  fi
  echo "    == 请编辑 ${JSONC} 填入真实 apiKey（devai）等本机凭据 =="
fi

echo "==> 完成。重启各 agent 使配置生效。"
echo "==> opencode 校验: opencode debug config"
echo "==> codex 校验: codex --strict-config"
echo "==> 第三方 skill/plugin: bash ai/install-thirdparty.sh"
