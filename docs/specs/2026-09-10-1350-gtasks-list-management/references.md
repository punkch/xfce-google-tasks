# References for 0.3.0 list management

## Calendar popover

- **Location:** `gtasks_panel/ui/mainwindow.py`, `_build_calendar`,
  `_calendar_date`, `_set_due`, `_clear_due`.
- **Relevance:** the popup rows and quick-add need the same calendar.
- **Key patterns:** `Gtk.Calendar.get_date()` returns a month that
  starts at 0. `popdown()` after a pick. Guard on `self._loading`.

## Sidebar rows

- **Location:** `gtasks_panel/ui/mainwindow.py`, `_rebuild_sidebar`,
  `_on_list_selected`; `gtasks_panel/ui/widgets.py`, `ListRow`.
- **Relevance:** the row menu, the "…" button and the inline rename
  entry go here.
- **Key patterns:** `_rebuilding = True` while the rows change, so that
  `row-selected` does not fire as user input. `clear()` empties a box.

## Optimistic write with rollback

- **Location:** `gtasks_panel/ui/worker.py`, `patch`, `move`, `delete`.
- **Relevance:** `rename_list` follows `patch`; `delete_list` follows
  `delete` (change the store on success only).
- **Key patterns:** `old = {...}` copy before the change, `failed()`
  puts it back, `_written` replaces the task from Google's answer,
  `_notify_panel()` at the end.

## Fake service in tests

- **Location:** `tests/conftest.py`, `FakeService`, `FakeCollection`
  (`insert`, `patch`, `move`, `delete` record their kwargs in
  `service.calls`).
- **Relevance:** `test_api.py` for the new tasklist calls.

## Worker tests without a thread

- **Location:** `tests/test_worker.py`, class `Jobs` replaces
  `Worker.post`; the test runs `job.fn`, `on_done`, `on_error` by hand.

## Undo bar smoke tests

- **Location:** `tests/test_ui_smoke.py`,
  `test_deleting_a_task_waits_behind_the_undo_bar` and the tests after
  it.
- **Relevance:** the pattern for a smoke test that clicks a widget and
  checks `worker.calls`.
