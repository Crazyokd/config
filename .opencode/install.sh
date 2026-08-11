#!/usr/bin/env bash
# 安装 OpenCode 配置到本机 ~/.config/opencode/
# - 软链进仓的骨架（opencode.json + agents + commands + plugins）
# - 生成本机 opencode.jsonc（凭据/本机路径覆盖，gitignored，若已存在则跳过）
# - 检测本机 hindsight / hermes 路径，写入 jsonc
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SRC="${REPO_DIR}/.opencode"
DEST="${XDG_CONFIG_HOME:-$HOME/.config}/opencode"

echo "==> 仓库配置目录: ${SRC}"
echo "==> 目标配置目录: ${DEST}"

mkdir -p "${DEST}"

# 1. 软链进仓骨架（仅当目标不存在时创建，避免覆盖本机文件）
link() {
  local src="$1" dst="$2"
  if [ -e "$dst" ] || [ -L "$dst" ]; then
    echo "    [skip] ${dst} 已存在"
  else
    ln -s "$src" "$dst"
    echo "    [link] ${dst} -> ${src}"
  fi
}

echo "==> 软链骨架文件/目录"
link "${SRC}/opencode.json" "${DEST}/opencode.json"
link "${SRC}/agents"        "${DEST}/agents"
link "${SRC}/commands"      "${DEST}/commands"
link "${SRC}/plugins"       "${DEST}/plugins"

# 2. 本机覆盖配置 opencode.jsonc（凭据 + 本机路径）
#    已存在则保留，不覆盖；仅当缺失时生成模板。
JSONC="${DEST}/opencode.jsonc"
if [ -f "$JSONC" ]; then
  echo "==> ${JSONC} 已存在，保留不动（如需重新生成先删除它）"
else
  echo "==> 生成 ${JSONC}（模板，请填入本机凭据与路径）"
  HINDSIGHT_ROOT=""
  for d in "$HOME/.codex/plugins/cache/hindsight/hindsight-memory/"*; do
    [ -d "$d/scripts" ] && HINDSIGHT_ROOT="$d" && break
  done
  HINDSIGHT_DATA="${HINDSIGHT_DATA:-$HOME/.codex/plugins/data/hindsight-memory}"
  HERMES_BIN="$HOME/.hermes/hermes-agent/venv/bin/python3"

  # 未检测到的 MCP 置 enabled:false，避免空路径导致启动失败
  HINDSIGHT_ENTRY='{ "enabled": false }'
  if [ -n "${HINDSIGHT_ROOT}" ] && [ -x "${HINDSIGHT_ROOT}/scripts/run_mcp.sh" ]; then
    HINDSIGHT_ENTRY=$(cat <<EOF2
{ "type": "local", "enabled": true, "command": ["bash", "${HINDSIGHT_ROOT}/scripts/run_mcp.sh"], "environment": { "CLAUDE_PLUGIN_DATA": "${HINDSIGHT_DATA}", "CLAUDE_PLUGIN_ROOT": "${HINDSIGHT_ROOT}", "HINDSIGHT_AGENT_NAME": "opencode", "HINDSIGHT_API_URL": "http://127.0.0.1:8888", "HINDSIGHT_BANK_ID": "hermes-unified", "HINDSIGHT_REQUEST_TIMEOUT_SECONDS": "120" } }
EOF2
)
  else
    echo "    [warn] 未找到 hindsight run_mcp.sh，hindsight MCP 将保持 enabled:false"
  fi

  HERMES_ENTRY='{ "enabled": false }'
  if [ -x "${HERMES_BIN}" ]; then
    HERMES_ENTRY="{ \"type\": \"local\", \"enabled\": true, \"command\": [\"${HERMES_BIN}\", \"-m\", \"agent.transports.hermes_tools_mcp_server\"], \"environment\": { \"HERMES_HOME\": \"$HOME/.hermes\", \"HERMES_QUIET\": \"1\", \"HERMES_REDACT_SECRETS\": \"true\" } }"
  else
    echo "    [warn] 未找到 hermes MCP bin，hermes-tools 将保持 enabled:false"
  fi

  # 用 Python 生成合法 JSON，避免手拼逗号出错
  python3 - "$JSONC" "$HINDSIGHT_ENTRY" "$HERMES_ENTRY" <<'PYEOF'
import json
import sys

jsonc_path, hindsight_entry, hermes_entry = sys.argv[1], sys.argv[2], sys.argv[3]

config = {
    "$schema": "https://opencode.ai/config.json",
    "mcp": {
        "hindsight": json.loads(hindsight_entry),
        "hermes-tools": json.loads(hermes_entry),
    },
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
  echo "    == 请编辑 ${JSONC} 填入真实 apiKey（devai）等本机凭据 =="
fi

echo "==> 完成。重启 opencode 使配置生效。"
echo "==> 校验：opencode debug config"
