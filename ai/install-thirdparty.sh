#!/usr/bin/env bash
# 安装第三方 skill / plugin 到本机（不入仓库真源，避免同步维护负担）
#
# 原则：
#   - 自有 skill 在 ai/skills/（真源，install.sh 软链三套）
#   - 第三方 skill 用 `npx skills add` 从上游安装，升级靠 `npx skills update`
#   - 各第三方来源记录在下方清单，方便重新安装
set -euo pipefail

# 可执行的 skill 包：格式 "source_spec|说明"
THIRDPARTY_SKILLS=(
  "larksuite/cli|Lark/Feishu 官方 agent skills (lark-*)，含 CLI 依赖"
  "vercel-labs/agent-skills|社区通用 skill 集合（含部分通用项）"
)

echo "==> 第三方 skill 安装"
echo "    使用 npx skills（https://github.com/vercel-labs/skills）从上游安装到 ~/.agents/skills"
echo "    不复制进仓库，升级用 'npx skills update' 即可"
echo ""

for spec in "${THIRDPARTY_SKILLS[@]}"; do
  source="${spec%%|*}"
  desc="${spec#*|}"
  echo "==> 安装 ${source} (${desc})"
  echo "    npx skills add ${source} -g -y"
  # 注释掉的默认不执行，避免批量装一堆；需要的取消注释或单独跑
  # npx skills add "${source}" -g -y
done

echo ""
echo "==> 按需安装（未自动执行，需手动确认）："
cat <<'EOF'
  # lark 系列（公司内部，强烈推荐）
  npx skills add larksuite/cli -g -y

  # 社区 skill（caveman / grill-me / cavecrew 等，按需）
  # npx skills add vercel-labs/agent-skills -g -y

  # Standard Robots ONES skill（若未随仓库分发）
  # 见 ~/.agents/skills/ones 或公司内部源
EOF

echo ""
echo "==> opencode 插件（不进仓的第三方）"
echo "    opencode plugin 生态：https://opencode.ai/docs/plugins/#from-npm"
echo "    需要时在 ~/.config/opencode/opencode.json 的 plugin 数组添加："
echo '    { "plugin": ["<npm-package>"] }'
echo ""
echo "==> 提示：安装后重启对应 agent。用 'npx skills list' 查看已装。"
