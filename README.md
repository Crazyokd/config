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
