# config

Personal configuration files.

The repo stores configuration that is useful to review and reuse across machines.

## Linux Desktop

The desktop files mirror paths under the user's home directory:

| Repository path | Configuration |
| --- | --- |
| `.config/alacritty/alacritty.toml` | Terminal appearance and fonts |
| `.config/nvim/` | Neovim configuration and plugin lockfile |
| `.config/Code/User/settings.json` | Shared VS Code preferences |
| `.config/Code/User/keybindings.json` | VS Code shortcuts |
| `.config/Code/User/extensions.txt` | VS Code extension IDs |
| `.local/share/applications/` | VS Code file handler and Wox launcher |
| `.config/autostart/` | Wox startup entry |
| `linux/gnome.ini` | Selected GNOME appearance, keyboard, and Dock preferences |
| `linux/wox.json` | Selected Wox preferences, exported from its settings database |

The VS Code snapshot excludes Windows terminal profiles, SSH host mappings,
author identity, and extension environment variables. Keep credentials and
machine-specific settings outside the shared files. `local/` is ignored by Git;
applications do not automatically read that directory.

### Restore

Install the applications first. Alacritty uses JetBrainsMono Nerd Font;
Neovim's plugin manager uses `lazy-lock.json` to restore the recorded versions.
VS Code themes and language integrations require their corresponding extensions.
The included launchers expect `/usr/bin/code` and `/usr/bin/wox`.

To install the recorded VS Code extensions:

```bash
xargs -r -n 1 code --install-extension < .config/Code/User/extensions.txt
```

Back up each destination before copying its configuration. Restore one application
at a time; avoid copying the whole repository over the home directory.

For example, from the repository root:

```bash
mkdir -p "$HOME/.config/alacritty"
# Back up an existing alacritty.toml before this copy.
cp .config/alacritty/alacritty.toml "$HOME/.config/alacritty/alacritty.toml"
```

GNOME preferences are optional and intended for machines with the same installed
themes and applications. Back up the current preferences, review `linux/gnome.ini`,
then load the selected keys:

```bash
mkdir -p "$HOME/.local/state/config-backups"
gnome_backup=$(mktemp "$HOME/.local/state/config-backups/gnome-XXXXXX.ini")
dconf dump /org/gnome/ > "$gnome_backup"
dconf load / < linux/gnome.ini
```

`linux/wox.json` is a readable preferences snapshot, not a native Wox import file.
Apply it through Wox Settings: set the main shortcut to double Ctrl, the action
panel shortcut to Ctrl+J, the file-search root to your home directory, and disable
"Skip hidden files". `~` in the snapshot represents the current user's home.
Review the remaining general preferences there as well. Wox's search index,
query history, clipboard history, and credentials are not tracked.

On Wayland, Wox's double-Ctrl shortcut needs keyboard input access. On a new
machine, deliberately grant that access, then log out and log back in:

```bash
sudo usermod -aG input "$USER"
```

Membership in `input` allows programs running as that user to read raw input
events. The included Wox desktop entries use `GDK_BACKEND=x11` for the GNOME
window-display workaround. Wox may regenerate its launcher during upgrades;
compare it with the tracked copy if the override disappears.

### Maintain

After adjusting an application, copy only its configuration back into the matching
repository path and inspect `git diff` before committing. Update the selected
GNOME/Wox snapshots when their preferences change. The initial desktop snapshot
was captured on 2026-10-14.

Do not copy the entire `~/.config`, `~/.wox`, or shell environment into this public
repository. Review VS Code environment settings and private host mappings on every
update; the current machine's Bash configuration contains credentials and must not
be copied wholesale.

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
