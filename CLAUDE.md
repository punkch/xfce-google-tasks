# gtasks-panel

Google Tasks counter for the XFCE panel, shipped as a Debian package.
No compiled code. Genmon (xfce4-genmon-plugin) runs `gtasks-panel` on a
timer and shows its XML output.

## Layout

| Path | Purpose |
|------|---------|
| `bin/gtasks-panel` | Python 3. Genmon XML output (tick, no network), `--fetch` (background Google query), `--auth`, `--status`, `--install-panel`, `--uninstall-panel`. |
| `tests/` | pytest. `conftest.py` loads the script as a module with XDG dirs under `tmp_path`. No Google packages or network needed. |
| `bin/gtasks-open` | Bash. Focus the `GoogleTasksApp` window with `wmctrl`, or start Chrome/Chromium in app mode. |
| `debian/` | debhelper 13, native source format, `Architecture: all`. `rules` calls `make install PREFIX=/usr`. |
| `Makefile` | `check` (syntax, man warnings, pytest if installed), `install`, `uninstall`, `deb` (output in `dist/`), `clean`. Installs `share/client_secret.json` if present. |
| `man/` | Man pages `gtasks-panel.1`, `gtasks-open.1`. Installed by `make install`. |
| `share/client_secret.json` | Optional, gitignored. Packaged OAuth client as fallback for `~/.config/gtasks-panel/client_secret.json`. |
| `config.ini.example` | Optional user settings (icon, label, open command). |
| `docs/handover.md` | The original draft this repo started from. |
| `docs/specs/` | Timestamped spec folders (shape, plan, standards, references, user guide). |

## Facts verified on the dev host (Parrot 7.3, Debian 13 base, XFCE 4.20)

- genmon runs the command synchronously inside the panel's GTK loop. The
  panel freezes for as long as the command runs. So the tick reads
  `state.json` only and spawns `--fetch` detached (`start_new_session`,
  all stdio to `/dev/null`, or genmon waits on the inherited pipe).
- genmon 4.1.1 stores config in `~/.config/xfce4/panel/genmon-N.rc`.
  Keys: `Command`, `UseLabel`, `Text`, `UpdatePeriod` (milliseconds), `Font`.
  Newer genmon (master) moves these to xfconf. `--install-panel` targets 4.1.x.
- Panel plugin list: xfconf channel `xfce4-panel`, `/panels/panel-N/plugin-ids`
  (int array), `/plugins/plugin-N` (type string). Always write the array with
  `xfconf-query -a`; without it a one-element list becomes a plain int.
- `<txt>` and `<tool>` are Pango markup: escape them. `<icon>`, `<txtclick>`,
  `<iconclick>` are passed through verbatim: never escape them.
- The panel re-writes every plugin rc file when it exits. `xfce4-panel -r`
  therefore restores an rc you deleted before the restart. Delete after.
  It does not re-write `plugin-ids`.
- Chrome `--app=... --class=GoogleTasksApp --user-data-dir=...` gives
  `WM_CLASS = "tasks.google.com", "GoogleTasksApp"`.
- Python 3.13 is externally managed. Use apt packages, never pip.
- Google OAuth apps in "Testing" status expire refresh tokens after 7 days.

## Conventions

- Docs and chat in ASD-STE100 Simplified Technical English.
- Conventional commits. Commit only after the user confirms.
- Version lives in `debian/changelog` and `VERSION` in `bin/gtasks-panel`. Bump both.
- Update this file in the same change when layout or conventions change.

## Build and test

```
make check              # also runs tests/ when python3-pytest is installed
make deb && sudo apt install ./dist/gtasks-panel_*.deb
gtasks-panel            # prints genmon XML
gtasks-panel --fetch    # runs the Google query in the foreground, shows errors
gtasks-panel --status
```

On the dev host `make` is a zsh function. Call `/usr/bin/make`.
