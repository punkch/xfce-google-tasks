# Skills & Conventions for 0.3.0 list management

## Project conventions (`CLAUDE.md`)

- Docs and chat in ASD-STE100 Simplified Technical English.
- Conventional commits. Commit only after the user confirms. No
  attribution trailer.
- Version lives in `debian/changelog` and `gtasks_panel/__init__.py`.
  Bump both.
- Update `CLAUDE.md` in the same change when layout or conventions
  change.
- Python 3.13 is externally managed. Use apt packages, never pip.
- Tests patch the module that owns a name, never a re-export.
- `paths` is read as `paths.NAME`, never imported by name.

## GTK rules from 0.2.0

- Never block the GTK loop. Every Google call runs in the one worker
  thread. Results come back with `GLib.idle_add`.
- A job must never kill the thread: the worker catches every exception
  and calls `on_failed`.
- Optimistic changes roll back in `on_error`, and only if the task is
  still in the store (`find_task` guard).
- `Gtk.Popover` is a child of the window. It does not fire the popup's
  focus-out. A `Gtk.ComboBox` dropdown and a `Gtk.Menu` are new
  toplevels: in the popup use popovers only.
- `test_ui_smoke.py` runs only with `GTASKS_UI_TESTS=1`, under
  `xvfb-run -a`.
- Widgets fill under `self._loading = True`, so that programmatic
  changes do not look like user input.

## Google Tasks API facts

- `tasklists.insert`, `patch`, `update`, `delete` exist. Writable field:
  `title` (max 1024 chars). Up to 2,000 lists per user.
- `tasks.delete` is permanent.
- `due` is a date only: `YYYY-MM-DDT00:00:00.000Z` (`api.due_to_api`).
