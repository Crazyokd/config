# Linux Input Methods

The 2026-10-14 snapshot records Fcitx **4.2.9.8** and Sogou Pinyin **4.2.1.145**.
The source machine's `im-config` selection is `fcitx`. Its Alacritty processes
use Fcitx input modules; GNOME's recorded input sources also include IBus
`libpinyin`. These are separate framework settings, not one portable activation
switch.

## Saved Preferences

| File | Purpose |
| --- | --- |
| `.config/fcitx/config` | Global preferences, including `SwitchKey=Disabled` |
| `.config/fcitx/profile` | Selected input method and enabled/disabled input-method list |
| `.config/fcitx/conf/fcitx-notify.config` | Notification preferences |
| `.config/sogoupinyin/conf/env.ini` | Sogou keys, candidate display, font, skin, and input behavior |
| `.config/sogoupinyin/dict/shell.conf` | Engine preferences; this text file contains settings, not learned words |

The selected Fcitx engine is `sogoupinyin`; `rime` and `googlepinyin` are also
enabled in the saved profile. Install the corresponding Fcitx 4 engines if you
want all three, or adjust the list using the configuration tool.

Sogou's saved font is `Droid Sans Fallback` and its skin is `default`. Candidate
window coordinates are omitted so another monitor layout can choose its own
position.

Input history, clipboard history, learned dictionaries, compiled Rime data,
machine identifiers, and session bus addresses are not tracked. Keep user
dictionary backups private. No customized IBus engine or IBus switching-hotkey
values were present when this snapshot was captured.

## Restore on Another Machine

1. Choose the input framework for that desktop session. This snapshot is for
   Fcitx 4 with Sogou, not Fcitx 5. Fcitx documents that Fcitx 4 configuration
   files do not migrate directly to Fcitx 5:
   <https://fcitx-im.org/wiki/Upgrade_from_Fcitx_4>.
2. Install Fcitx 4, its GTK/Qt input modules, and Sogou Pinyin using packages
   appropriate for the distribution. Install the saved font or choose an
   available font after restoring.
3. Quit Fcitx and Sogou before replacing configuration files so they cannot
   overwrite the restored preferences. Back up the existing destination files.
4. Copy the five files listed above into the same paths under the new user's
   home directory. Copy the listed files individually to preserve existing
   dictionaries and other local data.
5. On distributions using `im-config`, select Fcitx through that tool. Otherwise
   follow the distribution's Fcitx session setup. Log out and back in, then
   verify Chinese input in the applications you use.

If you choose GNOME's IBus integration instead, install the engine referenced
by `linux/gnome.ini` before restoring its `sources` key. The name `libpinyin`
there is a GNOME preference; it does not install or validate the engine. Avoid
automatically starting both frameworks as part of a bulk restore.

Framework-selection files such as `.xinputrc`, global input-module environment
variables, and Fcitx 5's inactive profile are deliberately left machine-local.
Reference: <https://fcitx-im.org/wiki/Configure_(Other)>.
