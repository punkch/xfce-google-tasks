# gtasks-panel

Google Tasks counter and window for the XFCE panel, shipped as a Debian
package. No compiled code. Genmon (xfce4-genmon-plugin) runs
`gtasks-panel` on a timer and shows its XML output; a panel click runs
`gtasks-window`, a GTK 3 popup/window pair, for a single sign-in.

## Layout

| Path | Purpose |
|------|---------|
| `bin/gtasks-panel` | Python 3 entry script. Finds `gtasks_panel/` beside itself or under `<prefix>/share/gtasks-panel`, then calls `gtasks_panel.panel.main()`. Genmon XML output (tick, no network), `--fetch`, `--auth`, `--status`, `--install-panel`, `--uninstall-panel`. |
| `bin/gtasks-window` | Python 3 entry script. Stamps the click time first (before any import), then calls `gtasks_panel.ui.app.run()`. `--window` opens the full window, `--quit` stops the resident process. Answers `--help`/`--version` before GTK loads. |
| `gtasks_panel/` | Private package (installed to `<prefix>/share/gtasks-panel/gtasks_panel/`). Core modules: `paths.py` (XDG paths, constants — read as `paths.NAME`, never imported by name, so tests can reload it), `config.py` (`load_config`), `state.py` (state file, lock, task cache, window geometry), `auth.py` (token load/refresh, scope check), `api.py` (Google Tasks API calls, `service=` seam), `model.py` (`Task`, `TaskList` dataclasses, tree/sort/summary, pure Python), `panel.py` (genmon XML, `--fetch`, install/uninstall, xfconf, plugin-event refresh). |
| `gtasks_panel/ui/` | GTK 3 layer. `click.py` (the pure parts of a click: `parse_args`, single vs double click, popup `place`, popup size — no GTK, so tests need no display), `store.py` (shared model both windows subscribe to; `notify()` collects the changes into one `GLib.idle_add` redraw), `worker.py` (one background thread + queue for every Google call, `GLib.idle_add` back to the GTK thread), `widgets.py` (task row, list row, CSS, shared helpers), `signin.py` (sign-in page), `popup.py` (380×520 popup at the pointer), `mainwindow.py` (960×600 sidebar/list/detail window), `app.py` (`Gtk.Application`, single instance; the UI imports happen in `do_startup`, so a forwarding second process pays for none of them). |
| `data/com.belneiski.gtasks.desktop` | Desktop entry for the full window, named after the app id so xfwm4/GTK link the window to it. |
| `tests/` | pytest. `conftest.py` imports the `gtasks_panel` package, reloads `paths` with XDG dirs under `tmp_path`, and holds the fake Google service, the `secret`/`token` fixtures, `default_cfg()` and `pump()` (runs the waiting GLib callbacks). Tests patch the module that owns a name (`api`, `auth`, `state`, `config`), never a re-export. Plain tests need no Google packages, no display and no network; `test_store.py`, `test_worker.py`, `test_popup_place.py` and `test_click.py` need `python3-gi` only. `test_ui_smoke.py` opens real GTK windows and runs only when `GTASKS_UI_TESTS=1` (gate is the env var, not `DISPLAY` — `make deb`/`dh_auto_test` run with a real `DISPLAY` and must not pop up windows). |
| `debian/` | debhelper 13, native source format, `Architecture: all`. `rules` calls `make install PREFIX=/usr`. No `dh-python`: the package ships plain `.py` files, no byte-compiled `.pyc`. |
| `Makefile` | `check` (syntax, `compileall`, man warnings, `desktop-file-validate`, pytest if installed), `install`, `uninstall`, `deb` (output in `dist/`), `clean`. Installs `share/client_secret.json` if present. |
| `man/` | Man pages `gtasks-panel.1`, `gtasks-window.1`. Installed by `make install`. |
| `share/client_secret.json` | Optional, gitignored. Packaged OAuth client as fallback for `~/.config/gtasks-panel/client_secret.json`. |
| `config.ini.example` | Optional user settings (icon, icon_overdue, label, open command, refresh, default_list). |
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
- Python 3.13 is externally managed. Use apt packages, never pip.
- Google OAuth apps in "Testing" status expire refresh tokens after 7 days.
- genmon (xfce4-genmon-plugin 4.1.1) binds click commands to GtkButton
  `clicked`, so it runs the click command once per click: a double
  click on the panel item starts the command twice (verified live,
  2026-09-10). `gtasks-window` tells single from double apart by the
  gap between the two process start times.
- A `Gtk.Application` with `HANDLES_COMMAND_LINE` gives one resident
  process per application id, found over the session D-Bus. Every
  later launch of `gtasks-window` hands its argv to that one process
  and exits. The panel's environment already carries
  `DBUS_SESSION_BUS_ADDRESS`. No window-focus tool (`wmctrl` etc.) is
  needed.
- All Google API calls run on one worker thread with a queue, never on
  the GTK thread: `httplib2.Http` and credential refresh are not
  thread-safe, and blocking the GTK loop would freeze the popup/window.
- `google.oauth2.credentials.Credentials.from_authorized_user_info(info,
  scopes)` uses the `scopes` argument when given and only falls back to
  the token file's own `scopes` when the argument is `None`. Load with
  `scopes=None`, then call `creds.has_scopes(SCOPES)`, to tell an old
  read-only 0.1.0 token from a current one.
- `tests/test_ui_smoke.py` opens real GTK windows and is gated on the
  env var `GTASKS_UI_TESTS=1`, not on `DISPLAY`: `make deb` runs
  `make check` under the desktop's real `DISPLAY`, and a `DISPLAY` gate
  would pop windows up on the user's screen during a package build.
- `dh-python` is not installed on the dev host, so the package ships
  plain `.py` files under `/usr/share/gtasks-panel/gtasks_panel/`,
  mode 0644, no `__pycache__` (lintian flags byte code in a package).

## Conventions

- Docs and chat in ASD-STE100 Simplified Technical English.
- Conventional commits. Commit only after the user confirms.
- Version lives in `debian/changelog` and `VERSION` in `gtasks_panel/__init__.py`. Bump both.
- Update this file in the same change when layout or conventions change.

## Build and test

```
make check              # syntax, compileall, man warnings, desktop-file-validate, pytest if installed
GTASKS_UI_TESTS=1 xvfb-run -a python3 -m pytest tests/test_ui_smoke.py   # GTK smoke tests
make deb && sudo apt install ./dist/gtasks-panel_*.deb
gtasks-panel            # prints genmon XML
gtasks-panel --fetch    # runs the Google query in the foreground, shows errors
gtasks-panel --status
gtasks-window --quit    # stop a resident window process (needed after every upgrade)
```

On the dev host `make` is a zsh function. Call `/usr/bin/make`.
