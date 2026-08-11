# config

Personal configuration files.

The repo stores configuration that is useful to review and reuse across machines.

## Claude

### CLAUDE.md

Tracks `.claude/CLAUDE.md` for reusable Claude Code coding guidelines.

`.codex/AGENTS.md` is a symlink to `.claude/CLAUDE.md`, so Codex uses the same file.

`.claude/skills` is a symlink to `.codex/skills`, so Claude reuses Codex skills.

Source: https://github.com/multica-ai/andrej-karpathy-skills

## CodeGraph

Local code knowledge graph for AI coding agents.

Install or run from upstream when needed:

```bash
npx @colbymchenry/codegraph
```

Initialize per project:

```bash
cd your-project
codegraph init -i
```

Project indexes live in `.codegraph/` and should stay local.

Reference: https://github.com/colbymchenry/codegraph

## Codex

### Config Validation

Enable the tracked pre-commit hook once per clone:

```bash
git config core.hooksPath .githooks
```

Before each commit, the hook runs `codex --strict-config` when the commit includes `.codex/config.toml`.

### OpenSpec Prompts

Install from OpenSpec when needed:

```bash
npm install -g @fission-ai/openspec@latest
openspec init --tools codex
```

Reference: https://openspec.dev/

## Hermes and Hindsight

The `ai` branch tracks the reusable parts of the local AI workflow:

- Codex and Claude shared instructions;
- Codex MCP, plugin, and Hindsight hook configuration;
- Claude Code Hindsight memory configuration;
- Hermes provider, memory, MCP, and delegation configuration;
- custom Hermes scripts and skills;
- Hindsight API, control-plane, and daily-forge user services.

Credentials and runtime state are intentionally not tracked. Create local files from the examples:

```bash
cp ~/.hermes/.env.example ~/.hermes/.env
cp ~/.hermes/hindsight/postgres.env.example ~/.hermes/hindsight/postgres.env
chmod 600 ~/.hermes/.env ~/.hermes/hindsight/postgres.env
```

Set `OPENAI_API_KEY`, `ANTHROPIC_TOKEN`, and any enabled messaging credentials in `.hermes/.env`. Set `DAILY_FORGE_LARK_WIKI_URL` before publishing knowledge documents to Feishu.

Reload the tracked user services after checkout:

```bash
systemctl --user daemon-reload
systemctl --user enable --now hindsight-api.service hindsight-control-plane.service
systemctl --user enable --now hindsight-daily-forge.timer
```

Validate the local configuration with:

```bash
hermes config check
```

The tracked pre-commit hook strictly validates `.codex/config.toml` when that file is staged.

## OpenCode

The `ai` branch tracks reusable OpenCode configuration:

- `.opencode/opencode.json` — general skeleton: codegraph MCP server and permissions (credential-free);
- `.opencode/agents/` — generic reusable subagents (e.g. `git-commit-pusher`);
- `.opencode/commands/` — custom commands;
- `.opencode/plugins/` — plugins such as the Hindsight memory recall/retain hooks;
- `.opencode/install.sh` — symlink installer.

Credentials and machine-specific paths are intentionally not tracked. The global `opencode.json` (from this repo) and the local `opencode.jsonc` are deep-merged at startup, with `opencode.jsonc` taking precedence on conflicting keys.

Install once per machine:

```bash
bash .opencode/install.sh
```

The installer symlinks the tracked skeleton into `~/.config/opencode/` (creating `opencode.json`, `agents/`, `commands/`, `plugins/` only if absent) and generates a local `opencode.jsonc` template with detected Hindsight/Hermes paths. Fill in your provider API keys there:

```bash
$EDITOR ~/.config/opencode/opencode.jsonc
```

Then restart OpenCode and verify with:

```bash
opencode debug config
```

Local overrides live in `~/.config/opencode/opencode.jsonc` (not tracked), so the repo skeleton stays credential-free.
