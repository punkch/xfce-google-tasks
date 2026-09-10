# References for the Google Tasks panel indicator

## Handover draft scripts

- **Location:** `docs/handover.md` (moved from the repo root).
- **Relevance:** The starting point. Two draft scripts.
- **Key patterns kept:** read-only scope, pagination over all task lists,
  genmon XML output, `wmctrl` focus-or-open logic.
- **Problems fixed:** script-relative paths, OAuth flow on every tick,
  no HTTP timeout, no cache, `<click>` instead of `<txtclick>`,
  hard dependency on `google-chrome`.

## Genmon plugin source

- **Location:** `https://gitlab.xfce.org/panel-plugins/xfce4-genmon-plugin`
  tag `xfce4-genmon-plugin-4.1.1`, file `panel-plugin/main.c` lines
  693-783.
- **Relevance:** Config keys and units for `--install-panel`.
- **Key facts:** rc keys `Command`, `UseLabel`, `Text`, `UpdatePeriod`
  (ms), `Font`. Newer master (4.2+) moves to xfconf properties
  `/command`, `/use-label`, `/text`, `/update-period`.

## XFCE panel xfconf layout on this host

- **Channel:** `xfce4-panel`.
- **Panels:** `/panels/panel-0/plugin-ids` is an int array.
- **Plugin types:** `/plugins/plugin-N` is a string, for example
  `systray`, `genmon`.
- **Config per plugin:** `~/.config/xfce4/panel/<type>-N.rc`.

## Chrome app window class

- **Command tested:** `google-chrome --app=https://tasks.google.com
  --class=GoogleTasksApp --user-data-dir=<dir>`.
- **Result:** `WM_CLASS = "tasks.google.com", "GoogleTasksApp"`.
  `wmctrl -x -l` shows `tasks.google.com.GoogleTasksApp`.
