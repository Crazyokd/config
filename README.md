# config

Personal configuration files.

The repo stores configuration that is useful to review and reuse across machines.

## Claude

### CLAUDE.md

Tracks `.claude/CLAUDE.md` for reusable Claude Code coding guidelines.

`.codex/AGENTS.md` is a symlink to `.claude/CLAUDE.md`, so Codex uses the same file.

Source: https://github.com/multica-ai/andrej-karpathy-skills

## Codex

### OpenSpec Prompts

Install from OpenSpec when needed:

```bash
npm install -g @fission-ai/openspec@latest
openspec init --tools codex
```

Reference: https://openspec.dev/
