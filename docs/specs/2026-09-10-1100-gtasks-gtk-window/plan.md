# gtasks-panel 0.2.0: own GTK window instead of Chrome

## Context

Today a click on the panel item opens Google Tasks in a Chrome app window. That window needs a
second Google sign-in in the browser. The user wants one sign-in only (the `--auth` token) and a
UI we own. Decision from the user: a GTK window (option 1). Chrome and `gtasks-open` go away.

Window behaviour, from the user:

- Single click on the panel item: a **popup** near the item. It shows the open tasks, lets you
  mark tasks complete, and has a quick-add field. It has a button to open the full window.
- Double click: the **full window**. Lists on the left, tasks in the middle, task details on the
  right. Add, edit title, notes, due date, complete, delete, move to another list.

## Facts verified this session

- Host has `python3-gi 3.50`, `gir1.2-gtk-3.0 3.24.49`, GTK 4 and libadwaita too. The XFCE theme
  is ARK-Snow and ships `gtk-3.0` styling only. So **GTK 3**, not GTK 4.
- Tasks API v1 (Google docs via MCP): writable `title`, `notes`, `due`, `status`, `completed`.
  `parent` and `position` are read-only; use `tasks.move` (supports `destinationTasklist`).
  `due` stores a date only, the time part is dropped. No recurrence, no starred. Read-write
  scope is `https://www.googleapis.com/auth/tasks`. Google's docs do not state whether that
  scope is "sensitive". An unverified External app in production shows an "unverified app"
  warning once. README must tell the user to click "Advanced, go to app".
- genmon 4.1.1 (`main.c` from the tag): click commands are bound to GtkButton `clicked`, so a
  double click runs the command twice. It supports
  `xfce4-panel --plugin-event=genmon-<id>:refresh:bool:true` to re-run the command now.
- The panel's environment has `DBUS_SESSION_BUS_ADDRESS` and `DISPLAY`. So a spawned
  `Gtk.Application` can find the running instance over DBus. `wmctrl` is not needed.
- GTK double-click time on the host: 250 ms. `xvfb-run`, `Xvfb`, `desktop-file-validate` exist.
- `dh-python` is **not** installed. The package ships plain `.py` files under
  `/usr/share/gtasks-panel/`. No byte-compile. Startup cost is small.
- Icons `task-due`, `task-due-symbolic`, `checkbox-checked-symbolic` exist in elementary-xfce.
- `debian/gtasks-panel.debhelper.log` is a build artifact and is staged by mistake.

## Design decisions

1. **Code layout.** Move the logic from `bin/gtasks-panel` into a private package
   `gtasks_panel/` installed to `/usr/share/gtasks-panel/gtasks_panel/`. The two entry scripts
   in `/usr/bin` insert that dir into `sys.path`. Modules:
   - `paths.py` (XDG paths, constants), `config.py` (`load_config`), `state.py` (state file,
     lock, `atomic_write`), `auth.py` (`load_credentials`, `run_auth_flow`, `needs_reauth`),
     `api.py` (`build_service`, `iter_items`, `fetch_summary`, plus `list_tasklists`,
     `list_tasks`, `insert_task`, `patch_task`, `complete_task`, `move_task`, `delete_task`,
     all with the `service=` seam), `panel.py` (genmon XML, `--fetch`, install/uninstall),
     `model.py` (pure Python: `Task`, `TaskList`, tree from `parent`, sort order, overdue,
     summary for the state file), `ui/app.py`, `ui/popup.py`, `ui/mainwindow.py`,
     `ui/worker.py`, `ui/signin.py`.
   - `bin/gtasks-panel` keeps its CLI. `bin/gtasks-window` is the new UI entry point.
   - Entry scripts find the package by their own path: try `<script dir>/../` (repo checkout),
     then `<script dir>/../share/gtasks-panel` (any prefix). No hard-coded `/usr/share`.
   - `SELF` moves out of the package. Each entry script resolves its own path and passes it
     to the package (`panel.configure(entry=Path)`), because `__file__` inside
     `gtasks_panel/panel.py` is the module, not `bin/gtasks-panel`. The install test asserts
     the genmon rc `Command=` ends in `bin/gtasks-panel`. `spawn_fetch` uses the same path.
   - `VERSION` moves to `gtasks_panel/__init__.py`. Modules have no shebang lines.
   - Tests import the package directly. `conftest.py` sets XDG env and inserts the repo root.
2. **Never block the GTK loop.** One worker thread with a `queue.Queue`. The UI posts jobs;
   results come back with `GLib.idle_add`. One thread only: `httplib2.Http` and credential
   refresh are not thread safe.
3. **Single instance, resident.** `Gtk.Application` with id `com.belneiski.gtasks` and
   `HANDLES_COMMAND_LINE`. The process stays resident after the popup hides (`app.hold()`), so
   the next click is instant. "Quit" in the full window's menu stops it.
4. **Click vs double click.** The launched process records `time.time()` as its first
   statement and passes it as `--clicked-at`. The primary compares it with the previous one.
   Delta below `max(400 ms, 2 × gtk-double-click-time)` = double click: hide the popup, show the
   full window. Else: toggle the popup. No `--clicked-at` (started from the menu): full window.
   Classification is a pure function `classify_click(prev_ts, ts, threshold) -> "single" |
   "double"` in `ui/app.py` with a headless test. The "two `clicked` per double click" fact
   comes from reading genmon `main.c`, not from a live test. Agent 2 verifies it first on the
   real panel: set a click command `sh -c 'date +%s.%N >> /tmp/clicks'` and run
   `xdotool click --repeat 2 --delay 100 1` over the item. If it does not hold, the "Open
   window" button in the popup is the only path to the full window, and the docs say so.
5. **Popup.** Undecorated toplevel, type hint UTILITY, skip taskbar and pager, keep above.
   Placed under the pointer position at activation, clamped to the monitor work area. Hides on
   focus-out and Escape. Size about 380×520. The list chooser is a `Gtk.MenuButton` with a
   `Gtk.Popover`, not a `Gtk.ComboBox`: a combo dropdown is a new toplevel, fires focus-out,
   and would hide the popup.
6. **Full window.** Normal decorated window (no `Gtk.HeaderBar` as titlebar: CSD does not
   match xfwm4 themes). In-window toolbar. Remembers size in
   `$XDG_STATE_HOME/gtasks-panel/window.json`.
7. **Scope change.** `SCOPES = ["https://www.googleapis.com/auth/tasks"]`. `load_credentials`
   returns `AUTH_REAUTH` when the saved token lacks the scope. Verified in
   `/usr/lib/python3/dist-packages/google/oauth2/credentials.py`: `from_authorized_user_info`
   uses the `scopes` argument when given and reads the file's `scopes` only when the argument
   is `None`. So load with `scopes=None` and then check `creds.has_scopes(SCOPES)`. Panel
   shows "sign in" one time. The window shows a sign-in page with a Sign in button. The button
   runs `gtasks-panel --auth` as a **subprocess** (not in the worker thread: `run_local_server`
   blocks until the browser calls back and would wedge the worker). The window polls for
   `token.json`, then loads. Cancel kills the subprocess. The panel's `setup` and `sign in`
   clicks open the window too. `xfce4-terminal` is no longer needed.
8. **Panel count after a change.** After a successful write the window computes the summary
   from its data, takes the file lock (non-blocking), writes `state.json`, and runs
   `xfce4-panel --plugin-event=genmon-<id>:refresh:bool:true` with the id from
   `find_installed`. If the lock is held, skip. The next `--fetch` catches up.
9. **Offline.** Full task data cached at `$XDG_CACHE_HOME/gtasks-panel/tasks.json`. The UI
   shows it at once and refreshes in the worker. On a network error an `Gtk.InfoBar` says
   "Offline. Showing saved tasks." and write actions are disabled. No write queue in v1.
10. **v1 scope.** In: lists, tasks, complete and un-complete, add, edit title, notes, due date
    (date-only `Gtk.Calendar` popover), delete with undo bar, move to another list, show
    completed toggle, subtasks shown indented from `parent`. Out: re-parenting, manual reorder,
    recurrence, starred, editing notes of Docs-assigned tasks.
    - Delete is a **delayed delete**: `tasks.delete` is permanent, so the row leaves the view,
      the undo bar shows, and the API call runs only when the bar times out (8 s) or is
      dismissed. Undo cancels the pending call.
    - Show completed passes `showCompleted=True` **and** `showHidden=True` (Google hides
      completed tasks). Un-complete patches `status=needsAction`; the exact shape for clearing
      `completed` is confirmed against the real API in the live test.
11. **Packaging.** Version 0.2.0. Depends add `python3-gi`, `gir1.2-gtk-3.0`; drop `wmctrl`;
    Recommends dropped (`google-chrome-stable | chromium`, `xfce4-terminal`). Install only
    `*.py` files, mode 0644, no `__pycache__` (lintian flags it). Ship
    `data/com.belneiski.gtasks.desktop` (named after the application id so xfwm4 and GTK link
    the window to it; Categories Office, Icon task-due) and man page `gtasks-window.1`. The
    app calls `Gtk.Window.set_default_icon_name("task-due")`. Remove `bin/gtasks-open` and
    `man/gtasks-open.1`. `make check` adds `desktop-file-validate` when present and
    `python3 -m compileall -q gtasks_panel`; `.gitignore` and `make clean` add
    `debian/*.debhelper.log` and `gtasks_panel/**/__pycache__`.
12. **Config.** `open_command` default becomes `gtasks-window`. New key `default_list` (title
    of the list for quick-add; empty = first list).
13. **Quit after upgrade.** A resident window process survives `apt install` of a newer
    version, and the panel click goes to the old process over DBus. `gtasks-window --quit`
    stops it. README says: after an upgrade, run `gtasks-window --quit` once.
14. **UI test gate.** `tests/test_ui_smoke.py` runs only when `GTASKS_UI_TESTS=1`, not on
    `DISPLAY`. `dh_auto_test` runs `make check` with the desktop `DISPLAY` set, and a
    `DISPLAY` gate would open windows on the user's screen during `make deb`.

## Tasks

### Task 0: Baseline commit (main thread, before any change)

- `git rm --cached debian/gtasks-panel.debhelper.log`; add the pattern to `.gitignore` and
  the `clean` target.
- One conventional commit of the staged 0.1.0 tree: `feat: gtasks-panel 0.1.0 genmon item
  with background fetch`. Plan approval is the commit confirmation. No attribution trailer
  (user's global rule).

### Task 1: Spec documentation (main thread)

Create `docs/specs/2026-09-10-1100-gtasks-gtk-window/` with `plan.md` (this plan in full),
`shape.md` (scope, the decisions above, user answers), `standards.md` (STE, conventions from
`CLAUDE.md`, the genmon and GTK facts), `references.md` (`bin/gtasks-panel` state and lock
code, `tests/conftest.py`, genmon `main.c` remote-event and click binding),
`user-guide.md` (setup, the two click modes, manual test table).

### Task 2: Shared package, API, model, tests (Agent 1)

- Split `bin/gtasks-panel` into `gtasks_panel/` as in decision 1. `bin/gtasks-panel` becomes a
  thin entry. Behaviour of every CLI mode stays the same. All 33 tests stay green after the
  conftest change.
- `api.py`: write functions listed in decision 1. `fields=` on list calls. Pagination with
  `list_next` (reuse `iter_items`).
- `model.py`: dataclasses, tree from `parent`, sort (overdue first, then due date, then
  `position`), `summary(lists) -> state dict` reused by `--fetch` and the window.
- `auth.py`: scope check (decision 7). Keep `needs_reauth`.
- `state.py`: `write_summary_if_free(summary)` (lock non-blocking) and
  `refresh_panel_item()` (plugin-event).
- `panel.py`: `open_command` default `gtasks-window`; `setup` and `sign in` clicks run
  `gtasks-window`; remove `terminal_command`.
- Tests: `tests/test_api.py` (fake service records calls for insert, patch, complete, move,
  delete), `tests/test_model.py`, `tests/test_auth.py` (missing scope = reauth), update
  existing tests for the new paths. `pytest -q` under 1 s.
- Makefile: install the package dir, `check` byte-compiles with `python3 -m compileall -q`.

### Task 3: GTK UI, desktop file, packaging (Agent 2, after Task 2)

- `ui/worker.py`: thread + queue + `GLib.idle_add` callbacks. Jobs: `load` (cache then
  network), `complete`, `uncomplete`, `add`, `patch`, `move`, `delete`, `signin`.
- `ui/app.py`: `Gtk.Application`, command line parsing, click vs double click (decision 4),
  popup toggle, main window show, hold, quit action, cache read at start.
- `ui/popup.py`: list chooser (All lists + each list), quick-add `Gtk.Entry` (Enter adds to
  the chosen list, or `default_list`), rows with check button, title, due label (red when
  overdue), "Open window" button, status line, Escape and focus-out hide.
- `ui/mainwindow.py`: sidebar (`Gtk.ListBox` of lists with counts), toolbar (Add, Show
  completed toggle, Refresh, menu), task list (`Gtk.ListBox`, indent by depth), detail pane
  (title entry, notes `Gtk.TextView`, due `Gtk.Calendar` in a popover with Clear, list
  combo for move, Delete with undo `Gtk.InfoBar`). Edits save on focus-out and on Enter.
  Offline banner. Size persisted.
- `ui/signin.py`: page for no-secret (path and short steps) and no-token or reauth (Sign in
  button, runs the flow in the worker, then loads).
- `bin/gtasks-window` (`--clicked-at`, `--quit`), `data/com.belneiski.gtasks.desktop`,
  `man/gtasks-window.1`.
- `debian/control`, `debian/changelog` 0.2.0, `gtasks_panel/__init__.py` VERSION 0.2.0,
  Makefile install rules for `data/` and the man page, remove `bin/gtasks-open` and its man
  page. (Agent 1 created the Makefile package rules; Agent 2 edits the same file after
  Agent 1 is done. The overlap is safe because the two run one after the other.)
- `tests/test_ui_smoke.py`: skipped unless `GTASKS_UI_TESTS=1` (decision 14); under
  `xvfb-run` builds the popup and the main window with fake data, checks widget tree, that a
  check click posts a `complete` job, and `classify_click` cases.
- First step of Agent 2: the live double-click check from decision 4. Report the result.

### Task 4: Docs (Agent 3, after Task 3, parallel with verification)

README (setup with the scope warning, the two click modes, states, files, troubleshooting),
`config.ini.example`, `CLAUDE.md` (layout table, new facts), spec `user-guide.md`, memory
file `gtasks-panel-project.md`.

### Task 5: Verification and review (main thread)

See "Verification" below, then `/unops-toolkit:code-review` with its five agents, apply
findings, re-run checks, rebuild the deb, one final `advisor` call, then ask before the
0.2.0 commit.

## Workflow and agent setup

| Agent | Model | Owns (file boundary) | Runs |
|-------|-------|----------------------|------|
| 1 implementation | opus | `gtasks_panel/` (all modules except `ui/`; `model.py` included), `bin/gtasks-panel`, `tests/` except `test_ui_smoke.py`, `Makefile` (package install rules, compileall) | first |
| 2 implementation | opus | `gtasks_panel/ui/`, `bin/gtasks-window`, `data/`, `man/`, `debian/`, `tests/test_ui_smoke.py`, removal of `bin/gtasks-open`; also edits `Makefile` (data and man rules) and `gtasks_panel/__init__.py` (VERSION) after Agent 1 | after 1 |
| 3 docs | sonnet | `README.md`, `config.ini.example`, `CLAUDE.md` (layout table, facts, the version convention line now names `gtasks_panel/__init__.py`), spec `user-guide.md` | after 2, parallel with my verification |
| review | code-review skill, 5 agents as the skill specifies | read-only | after verification |

Orchestration: one `Workflow` script (load `workflow-authoring` first), `pipeline` 1 → 2 → 3.
Agents run one after the other, so the two files both Agent 1 and Agent 2 touch (`Makefile`,
`gtasks_panel/__init__.py`) never see parallel edits. Agent 3 and my verification run at the
same time and touch different files. Verification is the session model in the main thread
(it needs the real panel and the screen). Total: 3 implementation and docs agents + 5 review
agents.

## Verification

1. `/usr/bin/make check`: syntax, compileall, man warnings, desktop-file-validate, pytest.
2. `GTASKS_UI_TESTS=1 xvfb-run -a python3 -m pytest tests/test_ui_smoke.py`.
3. Screenshots under `xvfb-run` of popup and main window with fake data (`import -display`),
   with `GTK_THEME=ARK-Snow` and the elementary-xfce icon theme set in the script, so the
   pictures show the real look (Xvfb has no xsettings daemon and would show Adwaita). Then
   `/unops-toolkit:interface-craft` critique on the images. `agent-browser` cannot drive
   GTK, so screenshots are the UX gate. Fix findings in the same batch. Xvfb has no window
   manager: placement, focus-out hide, and decorations are checked live only (step 4).
3b. Scope check with a fake token file in the scratchpad (never the user's real token): a
   token JSON whose `scopes` is the readonly scope must give `AUTH_REAUTH`.
4. Live on the real panel with the system Python (google libs are in
   `/usr/lib/python3/dist-packages`): single click shows the popup under the pointer, second
   click hides it, double click opens the full window, quick-add creates a task, complete and
   un-complete round-trip (needs the user's real token, which now exists), the panel count
   updates at once via plugin-event. If the screensaver is on, report it and use the xvfb
   screenshots.
5. Scope migration: with the 0.1.0 token the panel shows "sign in", the window shows the
   Sign in page, `--auth` re-consents, count returns.
6. Offline (`unshare -rn`): window shows the cache and the offline banner; writes disabled.
7. `make clean && make deb`, lintian clean, `dpkg -c` lists the package dir, desktop file,
   two scripts, two man pages.
8. After the user installs 0.2.0: `gtasks-panel --auth` once (new scope), then click.

## Risks

- Double-click detection depends on process start latency being similar for both clicks.
  Mitigation: the timestamp is taken before any import (decision 4). Threshold 400 ms.
- Focus-out to hide the popup needs xfwm4 to give the popup focus. Fallback: also hide on the
  next single click (toggle), which always works.
- An unverified OAuth app shows a warning at `--auth`. Documented, not fixable by us.
