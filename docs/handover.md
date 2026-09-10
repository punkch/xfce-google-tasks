# Handover: XFCE Panel Indicator for Google Tasks

## Goal
A Generic Monitor (genmon) item in the XFCE panel that shows the count of
pending Google Tasks, sitting next to the other panel indicators. Clicking it
should focus an existing Google Tasks app window, or open one if none is open.

## Status so far
- `xfce4-genmon-plugin` and `wmctrl` packages: **already installed** by the user.
- Python deps (`google-auth-oauthlib`, `google-api-python-client`,
  `google-auth-httplib2`): **not yet confirmed installed** — check/install with:
  ```
  pip install --user google-auth-oauthlib google-api-python-client google-auth-httplib2
  ```
- Two scripts have been written (full contents below) but **not yet placed,
  not yet authenticated, and not yet wired into the panel**.

## Remaining tasks
1. Choose/create a folder, e.g. `~/.local/bin/gtasks/`, and put both scripts
   there (`gtasks_count.py`, `gtasks_open.sh`). `chmod +x` both.
2. Get a Google Cloud OAuth client:
   - Console → enable **Google Tasks API**.
   - Credentials → Create Credentials → OAuth client ID → **Desktop app**.
   - Download the JSON, save as `client_secret.json` in the same folder as
     `gtasks_count.py`.
3. Run `python3 gtasks_count.py` once manually in a terminal. It should open a
   browser for OAuth consent (read-only Tasks scope) and then write
   `token.json` next to itself. Confirm it then prints valid genmon XML with a
   task count, non-interactively, on a second run.
4. Add a Generic Monitor to the XFCE panel:
   - Right-click panel → Panel → Add New Items → Generic Monitor.
   - Command: `python3 /full/path/to/gtasks_count.py`
   - Period: ~300 seconds (avoid hammering Google's API).
5. Drag the new item into position next to the other panel indicators (Panel
   → Items, reorder).
6. Click it once to test: it should launch a Chrome app window
   (`--app=https://tasks.google.com`) in an isolated profile at
   `~/.config/google-chrome-tasks-app`. User will need to sign into Google
   inside that window once. Click again while it's open to confirm it
   refocuses the existing window rather than opening a duplicate.
7. If `wmctrl -x -l` doesn't show a window matching `GoogleTasksApp` after
   opening (window class naming can vary by Chrome version/DE), adjust the
   `WIN_HINT` value in `gtasks_open.sh` to match whatever `wmctrl -x -l`
   actually reports for that window, and re-test.

## Known gotchas
- Genmon only re-reads output on its Period interval — after first wiring it
  up, task count won't update until the next tick (or panel item refresh).
- If `token.json` or `client_secret.json` go missing/invalid, the script
  degrades gracefully to showing `Tasks: !` with an error tooltip rather than
  crashing genmon — check the tooltip text for the underlying error.
- The Tasks API scope used is read-only (`tasks.readonly`), which is
  intentional — the count script never modifies anything; all editing happens
  in the clicked-through browser window.

## Full script contents

### `gtasks_count.py`
```python
#!/usr/bin/env python3
"""
Fetches the number of pending (incomplete) Google Tasks across all task lists
and prints XML that the xfce4-genmon-plugin understands.

First run will open a browser window for the OAuth consent flow and store a
token.json next to this script. After that it runs unattended.
"""
import os
import sys
from html import escape

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

SCOPES = ['https://www.googleapis.com/auth/tasks.readonly']
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TOKEN_PATH = os.path.join(BASE_DIR, 'token.json')
CREDS_PATH = os.path.join(BASE_DIR, 'client_secret.json')
OPEN_SCRIPT = os.path.join(BASE_DIR, 'gtasks_open.sh')


def get_credentials():
    creds = None
    if os.path.exists(TOKEN_PATH):
        creds = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists(CREDS_PATH):
                raise FileNotFoundError(
                    f"Missing {CREDS_PATH}. Download your OAuth client "
                    "secret from Google Cloud Console and put it here."
                )
            flow = InstalledAppFlow.from_client_secrets_file(CREDS_PATH, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(TOKEN_PATH, 'w') as f:
            f.write(creds.to_json())
    return creds


def count_pending_tasks():
    creds = get_credentials()
    service = build('tasks', 'v1', credentials=creds)

    tasklists = service.tasklists().list(maxResults=100).execute().get('items', [])
    total = 0
    for tl in tasklists:
        page_token = None
        while True:
            res = service.tasks().list(
                tasklist=tl['id'],
                showCompleted=False,
                showHidden=False,
                pageToken=page_token,
            ).execute()
            total += len(res.get('items', []))
            page_token = res.get('nextPageToken')
            if not page_token:
                break
    return total


def main():
    try:
        count = count_pending_tasks()
        txt = f"Tasks: {count}"
        tooltip = f"{count} pending task(s)"
    except Exception as e:  # noqa: BLE001 - genmon just needs *something* to show
        txt = "Tasks: !"
        tooltip = f"Error fetching tasks: {e}"

    print("<genmonoutput>")
    print(f"<txt>{escape(txt)}</txt>")
    print(f"<tool>{escape(tooltip)}</tool>")
    print(f"<click>bash {escape(OPEN_SCRIPT)}</click>")
    print("</genmonoutput>")


if __name__ == '__main__':
    sys.exit(main())
```

### `gtasks_open.sh`
```bash
#!/bin/bash
# Focuses an existing Google Tasks app window if one is open,
# otherwise opens Google Tasks as a standalone Chrome "app" window.

WIN_HINT="GoogleTasksApp"
PROFILE_DIR="$HOME/.config/google-chrome-tasks-app"

if command -v wmctrl >/dev/null 2>&1 && wmctrl -x -l | grep -qi "$WIN_HINT"; then
    wmctrl -x -a "$WIN_HINT"
else
    google-chrome \
        --app=https://tasks.google.com \
        --class="$WIN_HINT" \
        --user-data-dir="$PROFILE_DIR" \
        >/dev/null 2>&1 &
fi
```
