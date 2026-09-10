# gtasks-panel 0.3.0 — User guide

## Lists (full window)

Double click the panel item to open the full window.

- **New list:** click "New list" under the sidebar. Type the title.
  Press Enter. Press Escape to cancel.
- **Rename:** move the mouse over a list. Click the "…" button, or right
  click the row. Choose Rename. Change the title. Press Enter.
- **Mark all done:** row menu, "Mark all done". A dialog shows the
  number of open tasks. Click "Mark done".
- **Clear completed:** row menu, "Clear completed". A dialog asks to
  confirm, with no count (the window may not hold every completed
  task). Click Delete. This cannot be undone.
- **Delete list:** row menu, "Delete list". A dialog asks to confirm,
  with no count. Click Delete. Google deletes the list and all its
  tasks. This cannot be undone.

The "All lists" row has no menu. Offline, the menu entries are grey.

## Due dates

- **Popup, on a task:** click the date, or the calendar icon, on the
  right of the row. Choose Today, Tomorrow, a day and Set, or Clear.
- **On a new task (popup or full window):** click the calendar icon
  beside the add field before you press Enter. The icon shows the date
  you chose. After the add, it clears.

## Manual test table

| # | Step | Expected |
|---|------|----------|
| 1 | Full window: click New list, type "Test list", Enter. | "Test list" appears in the sidebar and is selected. Google Tasks on the web shows it. |
| 2 | Row menu on "Test list": Rename, type "Test list 2", Enter. | The sidebar shows "Test list 2". The web shows it. |
| 3 | Popup: choose "Test list 2", click the calendar icon, click Tomorrow, type "Due tomorrow", Enter. | The row shows "Tomorrow". The web shows the due date. |
| 4 | Popup: click "Tomorrow" on that row, click Today. | The row shows "Today". Panel count unchanged. |
| 5 | Full window: row menu, Mark all done, confirm. | The task leaves the open list. Panel count −1. |
| 6 | Full window: row menu, Clear completed, confirm. | With Show completed on, the task is gone. The web shows no task. |
| 7 | Full window: row menu, Delete list, confirm. | The list is gone from the sidebar and the popup chooser. The web shows no list. |
| 8 | Row menu on "My Tasks": Delete list, confirm. | Either the list is gone, or the error bar shows Google's text. |
| 9 | Disconnect the network. Open the row menu. | The entries are grey. The due pickers are grey. |
