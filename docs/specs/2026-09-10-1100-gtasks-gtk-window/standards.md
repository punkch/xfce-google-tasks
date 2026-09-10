# Skills & Conventions for gtasks-panel 0.2.0 (GTK window)

The standards from `docs/specs/2026-09-09-1705-gtasks-genmon-panel-deb/standards.md`
still apply. This file adds what is new for the window.

---

## GTK 3 with PyGObject

- **Source:** host packages `python3-gi 3.50`, `gir1.2-gtk-3.0 3.24.49`.
- **Why it applies:** The XFCE theme ARK-Snow ships `gtk-3.0` styling
  only. GTK 4 windows would look foreign.
- **Key points:**
  - `gi.require_version("Gtk", "3.0")` before the import.
  - Never block the GTK main loop. All network work runs in one worker
    thread. Results go back with `GLib.idle_add`.
  - `httplib2.Http` and credential refresh are not thread safe. One
    worker thread only.
  - No `Gtk.HeaderBar` as the window titlebar. xfwm4 draws the frame.
  - Popup: undecorated, type hint `UTILITY`, skip taskbar and pager,
    keep above. Hide on focus-out and Escape.
  - Popup list chooser: `Gtk.MenuButton` + `Gtk.Popover`. A
    `Gtk.ComboBox` dropdown is a new toplevel and fires focus-out.
  - Icons from the elementary-xfce theme: `task-due`,
    `task-due-symbolic`, `checkbox-checked-symbolic`.
  - `Gtk.Window.set_default_icon_name("task-due")`.

## Gtk.Application single instance

- **Source:** GIO docs, `Gio.ApplicationFlags.HANDLES_COMMAND_LINE`.
- **Key points:**
  - Application id `com.belneiski.gtasks`. Desktop file name
    `com.belneiski.gtasks.desktop` so xfwm4 and GTK link the window to
    it.
  - The second process passes its argv to the primary over DBus. The
    panel environment has `DBUS_SESSION_BUS_ADDRESS`.
  - `app.hold()` keeps the process resident after the popup hides.
  - `gtasks-window --quit` stops a resident process (needed after a
    package upgrade).

## genmon click handling (xfce4-genmon-plugin 4.1.1)

- **Source:** `panel-plugin/main.c` at tag `xfce4-genmon-plugin-4.1.1`,
  click binding near lines 1211–1232 and the remote event handler near
  line 1271.
- **Key points:**
  - Click commands bind to GtkButton `clicked`. A double click runs the
    command twice. To verify live before use.
  - `xfce4-panel --plugin-event=genmon-<id>:refresh:bool:true` re-runs
    the command now. The window uses this after a write.

## Google Tasks API v1 writes

- **Source:** Google Tasks API reference (google-developer-knowledge
  MCP).
- **Key points:**
  - Writable fields: `title`, `notes`, `due`, `status`, `completed`.
  - `parent` and `position` are read-only. Use `tasks.move`
    (`destinationTasklist` for cross-list moves).
  - `due` keeps the date only.
  - `tasks.delete` is permanent. The UI delays the call behind an undo
    bar.
  - Completed tasks are hidden. Pass `showCompleted=True` and
    `showHidden=True` together.
  - Scope `https://www.googleapis.com/auth/tasks`.
  - `Credentials.from_authorized_user_info(info, scopes)` uses the
    `scopes` argument when given. Load with `scopes=None` and check
    `creds.has_scopes(SCOPES)` to detect an old read-only token.

## Packaging additions

- Install only `*.py` under `/usr/share/gtasks-panel/gtasks_panel/`,
  mode 0644, no `__pycache__`.
- `make check` runs `python3 -m compileall -q gtasks_panel` and
  `desktop-file-validate` when present.
- UI smoke tests run only with `GTASKS_UI_TESTS=1`, under `xvfb-run`.

## User global rules

- ASD-STE100 in all docs and chat.
- Conventional commits. Commit only after user confirmation. No
  attribution trailers.
- Keep `CLAUDE.md` current in the same change.
- Python 3.13 is externally managed: apt packages only.
