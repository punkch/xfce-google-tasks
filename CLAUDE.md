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
| `gtasks_panel/` | Private package (installed to `<prefix>/share/gtasks-panel/gtasks_panel/`). Core modules: `paths.py` (XDG paths, constants — read as `paths.NAME`, never imported by name, so tests can reload it), `config.py` (`load_config`), `state.py` (state file, lock, task cache, window geometry), `auth.py` (token load/refresh, scope check), `api.py` (Google Tasks API calls, `service=` seam; tasklist calls `insert_tasklist`, `rename_tasklist`, `delete_tasklist`; `clear_completed` and `complete_all` run one Google call per task, each taking a `progress(index, total)` callback; `clear_completed` reads the list fresh with `show_completed=True`, since the store may not hold every completed task), `model.py` (`Task`, `TaskList` dataclasses, tree/sort/summary, pure Python), `panel.py` (genmon XML, `--fetch`, install/uninstall, xfconf, plugin-event refresh). |
| `gtasks_panel/ui/` | GTK 3 layer. `click.py` (the pure parts of a click: `parse_args`, single vs double click, popup `place`, popup size — no GTK, so tests need no display), `store.py` (shared model both windows subscribe to; `notify()` collects the changes into one `GLib.idle_add` redraw), `worker.py` (one background thread + queue for every Google call, `GLib.idle_add` back to the GTK thread; `add_list`, `rename_list` (optimistic, rolls back on error), `delete_list`, `clear_completed`, `complete_all` are the list jobs; `clear_completed` and `complete_all` run N calls in the worker thread and post progress through `GLib.idle_add(self._show_progress, text)` after each one, since the store is not thread-safe), `widgets.py` (task row, list row, CSS, shared helpers; `DuePopover` — a `Gtk.Calendar` plus Today/Tomorrow/Clear/Set buttons, `on_pick(date | None)`; `DueButton` is a flat `Gtk.Button` that shows the date or a calendar icon and makes its `DuePopover` on the first click; `add_from_entry()` is the one quick-add path for both windows; `confirm()` — a modal `Gtk.MessageDialog` with Cancel and a destructive button, held on `MainWindow.confirm` so a test can replace it; `TaskRow(due_picker=True, on_due=)` swaps the due label for a `DueButton`, popup only; `ListRow(on_menu=)` adds a hover "…" button and a right click, both calling `on_menu(row, event)` — `None` on the "All lists" row, which gets no menu), `signin.py` (sign-in page), `popup.py` (380×520 popup at the pointer), `mainwindow.py` (960×600 sidebar/list/detail window; the New-list `Gtk.Entry` sits under the sidebar `Gtk.ListBox`, not inside it, so a `_rebuild_sidebar` refresh cannot wipe a half-typed title; `self._editing` holds `(list_id, text)` while a list is renamed, and `_rebuild_sidebar` redraws that one row as an entry instead of a `ListRow`; the row "…" button and a right click open a `Gtk.Menu` — Rename, Mark all done, Clear completed, Delete list — built fresh each time and destroyed before the next one), `app.py` (`Gtk.Application`, single instance; the UI imports happen in `do_startup`, so a forwarding second process pays for none of them). |
| `data/com.belneiski.gtasks.desktop` | Desktop entry for the full window, named after the app id so xfwm4/GTK link the window to it. |
| `tests/` | pytest. `conftest.py` imports the `gtasks_panel` package, reloads `paths` with XDG dirs under `tmp_path`, and holds the fake Google service, the `secret`/`token` fixtures, `default_cfg()` and `pump()` (runs the waiting GLib callbacks). Tests patch the module that owns a name (`api`, `auth`, `state`, `config`), never a re-export. Plain tests need no Google packages, no display and no network; `test_store.py`, `test_worker.py`, `test_popup_place.py` and `test_click.py` need `python3-gi` only. `test_ui_smoke.py` opens real GTK windows and runs only when `GTASKS_UI_TESTS=1` (gate is the env var, not `DISPLAY` — `make deb`/`dh_auto_test` run with a real `DISPLAY` and must not pop up windows). |
| `debian/` | debhelper 13, native source format, `Architecture: all`. `rules` calls `make install PREFIX=/usr`. No `dh-python`: the package ships plain `.py` files, no byte-compiled `.pyc`. |
| `Makefile` | `check` (syntax, `compileall`, man warnings, `desktop-file-validate`, pytest if installed), `install`, `uninstall`, `changelog` (adds a `debian/changelog` entry with `dch` when the top entry is older than `PKG_VERSION` from `gtasks_panel/__init__.py`; fails when it is newer), `deb` (runs `changelog` and `check` first; output in `dist/`), `clean`. Installs `share/client_secret.json` if present. |
| `.github/workflows/` | `ci.yml`: `make check`, `make deb`, lintian, deb artifact on every push and PR to `main` and `development`. `release.yml`: on push to `main`, release-please makes the release PR and the tag; a second job, gated on `release_created`, builds the deb, attaches it to the GitHub release, runs `scripts/publish-apt.sh` and pushes the `gh-pages` branch. Both jobs run in one workflow because a release made with `GITHUB_TOKEN` starts no other workflow. |
| `release-please-config.json`, `.release-please-manifest.json`, `version.txt`, `CHANGELOG.md` | release-please files (release type `simple`, tags `vX.Y.Z`). `extra-files` points at `gtasks_panel/__init__.py`, whose `VERSION` line carries the `x-release-please-version` annotation. |
| `scripts/publish-apt.sh`, `scripts/apt-release.conf` | Build the static apt repo in a site dir with `apt-ftparchive`: `pool/main/*.deb`, `dists/stable/main/binary-{all,amd64,arm64}/Packages[.gz]`, signed `Release`, `Release.gpg`, `InRelease`, the public key `gtasks-panel.gpg`, `index.html`. Needs `APT_SIGNING_KEY` (fingerprint) and the secret key in the keyring. |
| `docs/images/` | README screenshots with sample data, made under Xvfb + xfwm4 with the ARK-Snow theme (`panel.png` is a crop of the real panel). |
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
- `DueButton` makes its `DuePopover` (a `Gtk.Calendar`) on the first
  click. The popup rebuilds every row on each store change, and a long
  job (Mark all done) sends one change per task, so an eager calendar
  per row was slow. The popup also skips `refresh` while hidden and
  redraws when it shows (`_stale`).
- The main window has a status line under the task list (`self.status`)
  for `store.status` texts. Without it, "Nothing to do." and the
  progress of a long job were visible in the popup only.
- CSS: `alpha()` in a border needs a compositor; without one it comes out
  black. The popup border is an opaque `shade()`. A fixed overdue red on
  a selected row is unreadable, so `row:selected .gtasks-overdue` sets a
  light tint.
- `dh-python` is not installed on the dev host, so the package ships
  plain `.py` files under `/usr/share/gtasks-panel/gtasks_panel/`,
  mode 0644, no `__pycache__` (lintian flags byte code in a package).
- The store keeps completed tasks only while "Show completed" is on.
  `clear_completed` cannot trust the store to hold every completed
  task, so its worker job reads the list again with
  `show_completed=True` before it deletes.
- A `Gtk.Menu` is a new toplevel window. The full window is already a
  toplevel, so its list row menu can use one. The popup is a
  borderless toplevel that hides itself on focus-out; a `Gtk.Menu`
  popup would trigger that hide at once. So the popup uses
  `Gtk.Popover` only (a child of the window), never `Gtk.Menu`.

## Conventions

- Docs and chat in ASD-STE100 Simplified Technical English.
- Conventional commits. Commit only after the user confirms.
- The version lives in `gtasks_panel/__init__.py` (`VERSION`, with the
  `x-release-please-version` annotation). release-please bumps it in the
  release PR. `debian/changelog` is history; `make deb` adds the entry.
  Do not bump by hand.
- Releases: merge `development` into `main`, merge the release PR that
  release-please opens. The Release workflow builds and publishes.
- The apt repo is `https://punkch.github.io/xfce-google-tasks` (branch
  `gh-pages`). Signing key: secret `GPG_PRIVATE_KEY`, fingerprint in the
  variable `APT_SIGNING_KEY`. The private key is also in the dev host's
  `~/.gnupg` (uid "gtasks-panel apt repo").
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
