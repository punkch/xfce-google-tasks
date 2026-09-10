# gtasks-panel 0.2.0: own GTK window — Shaping Notes

## Scope

Replace the Chrome app window with a GTK 3 window that we own. The
window uses the same Google token as the panel. The user signs in one
time only.

Two ways to open it from the panel item:

- Single click: a popup near the item. It shows the open tasks. The user
  can mark a task complete and add a task fast. A button opens the full
  window.
- Double click: the full window. Lists on the left, tasks in the middle,
  task details on the right. Add, edit title, notes, due date, complete,
  delete, move to another list.

Chrome and `gtasks-open` go away.

## User answers

- "can you make it fully use the API (with a custom google login) and
  then fully custom UI?" Three options were shown. The user picked
  option 1: a GTK window in Python.
- Window behaviour: "Both, click opens popup panel with an optin to
  open normal window. Double click, opens the Normal Window. The popup
  panel should give option to view tasks, mark them complete and an
  option to create a new task quickly."
- Chrome opener: "Drop it".

## Decisions

See `plan.md`, section "Design decisions", for the full list. Short form:

- **GTK 3, not GTK 4.** The XFCE theme ARK-Snow has `gtk-3.0` styling
  only.
- **Private package `gtasks_panel/`** in `/usr/share/gtasks-panel/`. Two
  thin entry scripts in `/usr/bin`. No `dh-python` on the host, so plain
  `.py` files.
- **One worker thread** for all network work. Results come back with
  `GLib.idle_add`.
- **Resident `Gtk.Application`**, id `com.belneiski.gtasks`. The panel
  click starts a short process that hands the click to the resident one
  over DBus.
- **Double click = two clicks less than 400 ms apart.** Genmon runs the
  click command one time per `clicked` signal. Agent 2 verifies this on
  the real panel first.
- **Read-write scope** `https://www.googleapis.com/auth/tasks`. The old
  read-only token gives "sign in" one time.
- **Sign in runs `gtasks-panel --auth` as a subprocess.** Not in the
  worker thread. The browser callback can block for a long time.
- **Delayed delete with undo.** The API delete is permanent.
- **Offline cache** at `$XDG_CACHE_HOME/gtasks-panel/tasks.json`. Writes
  are disabled offline.
- **No `Gtk.ComboBox` in the popup.** Its dropdown fires focus-out and
  hides the popup. Use `Gtk.MenuButton` with a `Gtk.Popover`.
- **UI tests run only with `GTASKS_UI_TESTS=1`.** A `DISPLAY` gate would
  open windows during `make deb`.

## Constraints and known risks

- Double-click detection depends on process start time. The timestamp
  is taken before any import.
- Focus-out to hide the popup needs xfwm4 to give the popup focus. The
  toggle on the next click always works.
- An unverified OAuth app shows a warning at `--auth`. Documented.
- A resident old process survives a package upgrade. `gtasks-window
  --quit` stops it.

## Context

- **Visuals:** None. Screenshots under Xvfb are made during
  verification.
- **References:** see `references.md`.
- **Product alignment:** N/A. No `docs/product/` folder.

## Skills & Conventions Applied

- Debian packaging with debhelper 13, native format, `Architecture: all`.
- Global user rules: conventional commits after confirmation, ASD-STE100,
  keep `CLAUDE.md` current, no attribution trailers.
- Delivery workflow: Workflow tool with three agents (opus, opus,
  sonnet), then the code-review skill with five agents, then
  interface-craft on screenshots.

## As built (2026-09-10)

- `ui/click.py` holds `parse_args`, `classify_click`, `place` and the
  popup size. It imports no GTK. `ui/store.py` holds the shared task
  data; it sends one notification per main-loop turn (`GLib.idle_add`).
- `refresh_panel_item` and `notify_summary` live in `panel.py`, not in
  `state.py`.
- `Task.completed` is a property of `status`, not a field.
- `gtasks-window --quit` starts no load.
- Real API writes (add, complete, un-complete, move, delete) were not
  run against Google: the user's token still has the read-only scope.
  The manual test table in `user-guide.md` covers them.
