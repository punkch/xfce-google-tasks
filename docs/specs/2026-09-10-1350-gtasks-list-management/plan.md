# gtasks-panel 0.3.0: list management and due dates in the popup

## Context

0.2.0 is committed (`bfd6792`) and installed. The user can only read task lists; new lists must
be made on the web. The user asked for list management with "the main actions", and for a due
date picker in the popup. Answers from the user (2026-09-10):

- List actions: **New list, Rename list, Delete list, Clear completed, Mark all done**.
- Rename and delete live in a **row menu** in the sidebar (right click, or a small "…" button
  that shows when the mouse is over the row).
- Popup due date: **both** per task row and in the quick-add field.

## Facts verified

- Tasks API v1 `tasklists` has `insert`, `patch`, `update`, `delete`. The only writable field
  is `title` (max 1024 chars). A user can have up to 2,000 lists. Google's docs do not say
  whether the default list can be deleted, so the app shows Google's error text if it refuses.
  (Source: google-developer-knowledge, developers.google.com/workspace/tasks/reference/rest.)
- `tasks.delete` is permanent. So "Delete list", "Clear completed" and "Mark all done" ask
  first with a dialog. "Mark all done" can be undone by hand, but it is N calls, so it asks too.
- GTK 3 `Gtk.Popover` is a child of the window, not a new toplevel: the popup's list chooser
  already uses one and the popup does not hide on it (verified live in 0.2.0). So a calendar
  popover in the popup is safe.
- Today `mainwindow.py:_build_calendar` builds the calendar popover inline. The popup rows and
  quick-add need the same thing: move it to a shared widget.

## Design decisions

1. **API** (`gtasks_panel/api.py`): `insert_tasklist(service, title) -> TaskList`,
   `rename_tasklist(service, list_id, title) -> TaskList` (patch `title`),
   `delete_tasklist(service, list_id) -> None`. `tasklist_from_api(item)` in `model.py`.
   `clear_completed(service, list_: TaskList) -> list[str]` deletes each completed task with
   `tasks.delete` and returns the ids it deleted. `complete_all(service, list_) -> list[Task]`
   patches each open task with `status=completed` and returns the fresh tasks. Both run as one
   worker job each; the job reports "N of M…" through `store.set_status` via `GLib.idle_add`.
   `insert_task` takes `due` (add the parameter if it is missing; `due_to_api` exists).
2. **Store** (`ui/store.py`): `add_list(list_)`, `remove_list(list_id) -> int` (index; resets
   `selected_list_id` to All lists when it was that list), `rename_list(list_id, title)`,
   `replace_list(list_)`. All call `notify()`.
3. **Worker** (`ui/worker.py`): `add_list(title)` (adds on success, selects it),
   `rename_list(list_, title)` (optimistic, rollback on error), `delete_list(list_)` (removes on
   success only), `clear_completed(list_)` (removes the returned ids), `complete_all(list_)`
   (replaces the returned tasks). Each ends with `_notify_panel()`.
4. **Shared due widget** (`ui/widgets.py`): `DuePopover(on_pick)`: `Gtk.Calendar`, buttons
   Today, Tomorrow, Clear, Set. `on_pick(date | None)`. `due_shortcuts(today) -> dict` is a
   pure helper (`ui/click.py`, no GTK) for the tests. `mainwindow.py` drops
   `_build_calendar` and uses `DuePopover`.
5. **Popup rows**: `TaskRow` gets `due_picker=True` in the popup: the due label becomes a flat
   `Gtk.MenuButton` (text = due date, or a `x-office-calendar-symbolic` icon when none) with a
   `DuePopover`. Pick → `worker.patch(task, due=date)`. Offline: insensitive.
6. **Quick-add due**: `quick_add()` in `widgets.py` gets a `due` argument. Popup and main window
   get a small flat `Gtk.MenuButton` (calendar icon; shows the date once picked) beside the add
   entry. After a successful add the pick resets to none. `worker.add(list_id, title, due)`.
7. **Sidebar** (`mainwindow.py`): a "New list" button (icon `list-add-symbolic` + label) under
   the sidebar list. Click → an inline `Gtk.Entry` row at the bottom of the sidebar; Enter
   creates, Escape or empty cancels. Rename uses the same inline entry in place of the row.
   `ListRow` gets a "…" button (`view-more-symbolic`, flat, opacity 0 until the pointer enters
   the row, always visible for keyboard focus) and a right-click handler; both open a
   `Gtk.Menu`: Rename, Mark all done, Clear completed, Delete list. The All lists row has no
   menu. Menu items are insensitive offline.
8. **Confirm dialogs**: `confirm(parent, title, text, action_label) -> bool` in `widgets.py`,
   a modal `Gtk.MessageDialog` with Cancel and a destructive action button. Texts:
   "Delete list “Work” and its 5 tasks? This cannot be undone." /
   "Delete 3 completed tasks in “Work”? This cannot be undone." /
   "Mark 5 open tasks in “Work” as done?" A list with nothing to do skips the dialog and
   shows "Nothing to do." in the status line. Tests bypass the dialog through
   `MainWindow.confirm` (an attribute the test replaces with `lambda *a: True`).
9. **Version 0.3.0**: `gtasks_panel/__init__.py`, `debian/changelog`. Man page
   `gtasks-window.1` and README get the new actions. No new dependencies.
10. **Out of scope**: reorder lists, list colours, `tasks.clear` (it hides, we delete), undo for
    list actions, moving all tasks between lists.

## Corrections from the advisor review (before implementation)

- The store holds completed tasks only when "Show completed" is on. So `clear_completed`
  fetches inside the job: `api.list_tasks(service, list_id, show_completed=True)`, keeps
  `status == STATUS_DONE`, deletes those, returns their ids. Its dialog has no count:
  "Delete all completed tasks in “Work”? This cannot be undone." Delete list says
  "Delete list “Work” and all its tasks? This cannot be undone." Mark all done keeps its
  count (open tasks are always loaded).
- `_rebuild_sidebar` clears the ListBox on every refresh. The New-list entry lives outside
  the ListBox (a Box under it, revealed on click). Rename holds `self._editing =
  (list_id, text)` and `_rebuild_sidebar` re-creates that row as an entry with the saved text.
- Delete list cancels a pending task delete of that list first (remove the timer source,
  hide the undo bar), so no `tasks.delete` lands in a gone list.
- `worker.add(list_id, title, due=None)` and `quick_add(..., due=None)` keep defaults.
- Progress text from the worker thread goes through `GLib.idle_add(self.store.set_status,
  text)`; the store is not thread-safe.
- The quick-add due pick resets when the job is posted.
- `tests/conftest.py` belongs to Agent 1.
- A smoke test clicks **Set** on `DuePopover` and asserts `patch(due=...)`.
- Before the deb: `grep -rn '0\.2\.0' README.md CLAUDE.md man/ debian/control` for stale
  version strings.

## Tasks

### Task 1: Spec documentation (main thread)

Create `docs/specs/2026-09-10-1350-gtasks-list-management/` with `plan.md` (this plan in
full), `shape.md` (scope, the user's answers, decisions), `standards.md` (STE, conventions from
`CLAUDE.md`, the GTK and API facts), `references.md` (`mainwindow.py:_build_calendar`,
`_rebuild_sidebar`, `worker.py:delete`/`patch` rollback pattern, `test_ui_smoke.py` undo tests),
`user-guide.md` (how to use each action, manual test table).

### Task 2: Core (Agent 1, opus)

Owns `gtasks_panel/api.py`, `gtasks_panel/model.py`, `gtasks_panel/ui/store.py`,
`gtasks_panel/ui/worker.py`, `gtasks_panel/ui/click.py` (`due_shortcuts`), and
`tests/test_api.py`, `tests/test_model.py`, `tests/test_store.py`, `tests/test_worker.py`,
`tests/test_click.py`. Decisions 1–3 and the pure helper of 4. `pytest -q` green.

### Task 3: UI and packaging (Agent 2, opus, after Task 2)

Owns `gtasks_panel/ui/widgets.py`, `mainwindow.py`, `popup.py`, `tests/test_ui_smoke.py`,
`gtasks_panel/__init__.py`, `debian/changelog`, `man/gtasks-window.1`. Decisions 4–9. New
smoke tests: new-list entry posts `add_list`; rename posts `rename_list`; row menu delete with
`confirm` patched posts `delete_list`; popup row due pick posts `patch(due=)`; quick-add with a
due posts `add(..., due)`; `DuePopover` Today/Tomorrow/Clear call back with the right value.
`GTASKS_UI_TESTS=1 xvfb-run -a python3 -m pytest tests/test_ui_smoke.py` green.

### Task 4: Docs (Agent 3, sonnet, after Task 3)

Owns `README.md`, `CLAUDE.md` (layout rows for `widgets.py` DuePopover/confirm, new facts,
version 0.3.0), spec `user-guide.md`. Runs parallel with my verification.

### Task 5: Verification and review (main thread)

1. `/usr/bin/make check`, UI smoke tests under Xvfb.
2. Screenshots under Xvfb with the fake cache (`scratchpad/fakecache.py`, `shots.sh`): popup
   with a row due popover open, sidebar with the row menu open, the delete dialog. Then
   `/unops-toolkit:interface-craft` critique. Fix findings.
3. Live on the real panel with a copy of the real token in scratch XDG dirs (deleted after):
   new list "Test list", rename it, add a task with a due date from the popup, change the due
   from the popup row, mark all done, clear completed, delete the list. Check each on Google
   through `api.list_tasklists`. Stop the user's window process first (`gtasks-window --quit`)
   and tell the user.
4. `/unops-toolkit:code-review` with its five agents. Apply findings. Re-run 1.
5. `make clean && make deb`, lintian. One final `advisor` call. Ask before the commit.

## Workflow and agent setup

| Agent | Model | Owns | Runs |
|-------|-------|------|------|
| 1 core | opus | `api.py`, `model.py`, `ui/store.py`, `ui/worker.py`, `ui/click.py`, their tests | first |
| 2 UI | opus | `ui/widgets.py`, `ui/mainwindow.py`, `ui/popup.py`, `test_ui_smoke.py`, version, changelog, man page | after 1 |
| 3 docs | sonnet | `README.md`, `CLAUDE.md`, spec `user-guide.md` | after 2, parallel with verification |
| review | code-review skill, 5 agents | read-only | after verification |

One `Workflow` script, `pipeline` 1 → 2 → 3, no parallel edits on the same file. Verification
is the session model in the main thread. Total: 3 agents + 5 review agents.

## Verification (summary)

- Unit: new tests in `test_api.py`, `test_store.py`, `test_worker.py`, `test_click.py`.
- UI: new smoke tests under Xvfb.
- Live: the list of real actions in Task 5.3, each checked on Google.
- Package: deb builds, lintian clean, `apt install --reinstall` not needed (new version).

## Risks

- "Clear completed" and "Mark all done" are N sequential calls. A list with 200 done tasks
  takes a while; the status line shows progress and the worker stays responsive to nothing
  else meanwhile (one thread). Accepted for v1.
- The default list may refuse `delete`. The error bar shows Google's text.
- Hover-only "…" buttons are hard to find. The right click and the always-present keyboard
  path (the row is focusable, Menu key) cover it; the user guide says so.
