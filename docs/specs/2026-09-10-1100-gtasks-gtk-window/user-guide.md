# User guide: gtasks-panel 0.2.0 (GTK window)

## Setup

1. Install the package:
   `sudo apt install ./dist/gtasks-panel_0.2.0_all.deb`
2. If you upgrade from 0.1.0, stop the old window process:
   `gtasks-window --quit`
3. Sign in one time. The new version needs read-write access:
   `gtasks-panel --auth`
   Google can show "Google hasn't verified this app". Click "Advanced",
   then "Go to (your app name) (unsafe)".
4. If the panel item is not there yet:
   `gtasks-panel --install-panel`

## Use

| Action | Result |
|--------|--------|
| Click the panel item | The popup opens under the pointer. |
| Click again, press Escape, or click elsewhere | The popup hides. |
| Double click the panel item | The full window opens. |
| Type in the popup field and press Enter | A new task goes to the chosen list. |
| Click the check box on a task | The task is complete. The panel count updates. |
| "Open window" button in the popup | The full window opens. |
| Menu > Quit in the full window | The resident process stops. |

Full window: lists on the left, tasks in the middle, details on the
right. Edit the title, notes, and due date. Move a task to another list.
Delete shows an undo bar for 8 seconds.

## Files

| Path | Content |
|------|---------|
| `~/.config/gtasks-panel/config.ini` | Options: `open_command`, `default_list`, `icon`, `label`, `refresh`. |
| `~/.local/state/gtasks-panel/token.json` | Google token. |
| `~/.local/state/gtasks-panel/state.json` | Last count for the panel. |
| `~/.local/state/gtasks-panel/window.json` | Full window size. |
| `~/.cache/gtasks-panel/tasks.json` | Offline copy of the tasks. |

## Manual test table

| # | Step | Expected |
|---|------|----------|
| 1 | Install 0.2.0 over 0.1.0. Do not run `--auth`. | Panel shows "sign in". |
| 2 | Click the item once. | Popup shows the Sign in page (the first click is always a single click). |
| 3 | Click Sign in. Finish in the browser. | Popup shows the tasks. Panel shows the count. |
| 4 | Click the item once. | Popup under the pointer. |
| 5 | Click the item again. | Popup hides. |
| 6 | Double click the item. | Full window opens. |
| 7 | Popup: type "Test task", Enter. | Task appears. Panel count +1 within 2 s. |
| 8 | Popup: check "Test task". | Row leaves the list. Panel count −1. |
| 9 | Full window: Show completed. Uncheck "Test task". | Task is open again. |
| 10 | Full window: Delete "Test task". Click Undo. | Task stays. |
| 11 | Full window: Delete "Test task". Wait 8 s. | Task is gone in Google Tasks on the web. |
| 12 | Disconnect the network. Open the window. | Banner "Offline. Showing saved tasks." Add and check are disabled. |
| 13 | `gtasks-window --quit` | Process stops. Next click starts a new one. |

## Troubleshooting

- **Popup does not hide on focus loss.** Click the panel item again.
- **Panel count is old after a change.** Wait for the next refresh, or
  run `gtasks-panel --fetch`.
- **"sign in" comes back after an upgrade.** The new scope needs a new
  token. Run `gtasks-panel --auth`.
- **Window shows old code after an upgrade.** Run `gtasks-window --quit`.
