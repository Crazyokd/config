# Primary Linux Test Machine

Use the private SSH alias `self` as the primary test machine for now. Keep its
address, SSH authentication, and passwords outside this public repository.

## Environment Observed on 2026-10-14

| Component | Test-machine environment |
| --- | --- |
| OS | Ubuntu 22.04.5 LTS, x86_64 |
| Desktop | GNOME Wayland, with XWayland available |
| Input method | Fcitx 5, with keyboard-us and Rime in its active profile |
| VS Code | Snap installation; launcher is `/snap/bin/code` |
| Alacritty | 0.17.0, installed for the user under `~/.local/bin` |
| Terminal font | JetBrainsMono Nerd Font, installed under the user's font directory |

The tracked Fcitx 4/Sogou files do not describe the test machine's active input
framework. Keep Fcitx 5/Rime configured while testing shared desktop settings.
The tracked VS Code launcher expects a native `/usr/bin/code` installation;
the Snap machine needs its installed desktop entry before launcher restore.

## First Verification

Configuration commit: `2af3f582446801399835dc48242f2eda6840f706`.

- Cloned the exact configuration branch into `~/repo/config` using a Git bundle
  after direct GitHub access failed with a TLS error.
- Installed Alacritty and the font files in user directories. No system package
  installation was required for this test.
- Validated the TOML configuration with Alacritty 0.17.0.
- Confirmed font matches for Light, Medium, and Light Italic.
- Opened an XWayland test window and inspected its screenshot: normal, italic,
  bold, and Chinese text displayed successfully.

This verifies rendering and font fallback, not interactive Chinese input. The
VS Code, GNOME, Wox, Neovim, and input-method restore procedures have not yet
been tested on this machine.

## Local Evidence and Rollback

Each test keeps a private run directory under `~/.local/state/config-tests/`.
`latest-alacritty-test` points to the first Alacritty run. Its `manifest.json`
records the exact source commit and each modified path's prior existence;
existing destinations are copied under `backup/` before replacement.

The first run also stores `preview.png`, `window.log`, and `result.json` there.
The Alacritty binary and font files were transferred as a local test package;
they are not versioned in this repository. Its preview can be closed normally.

To undo that run, close the preview, restore destinations marked `existed: true`
from `backup/`, remove only the recorded destinations marked `existed: false`,
and refresh the user font cache. Leave unrelated home-directory files intact.
