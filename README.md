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
