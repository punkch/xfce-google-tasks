# User guide and manual test scenarios

## Install

```
make deb
sudo apt install ./dist/gtasks-panel_0.1.0_all.deb
```

## First setup

1. Make a Google Cloud project. Enable the **Google Tasks API**.
2. Go to **APIs & Services → OAuth consent screen**. Set the app to
   **In production** (external) or **Internal** (Workspace account).
   If you keep **Testing**, the token expires after 7 days.
3. Go to **Credentials → Create credentials → OAuth client ID →
   Desktop app**. Download the JSON.
4. Save it as `~/.config/gtasks-panel/client_secret.json`.
5. Run `gtasks-panel --auth`. A browser opens. Accept the read-only
   scope. The token is saved to `~/.local/state/gtasks-panel/token.json`.
6. Run `gtasks-panel --install-panel`. The panel restarts and shows the
   item.

## Test scenarios

| # | Scenario | Steps | Expected |
|---|----------|-------|----------|
| 1 | No secret | Remove `client_secret.json`. Run `gtasks-panel`. | XML with text `setup`. Tooltip names the path. |
| 2 | No token | Secret present, no token. Run `gtasks-panel`. | XML with text `sign in`. |
| 3 | Auth | Run `gtasks-panel --auth`. | Browser opens. Token file written. Prints the count. |
| 4 | First tick | Remove `state.json`. Run `gtasks-panel`. | XML with text `…`. Returns in well under 1 s. A `--fetch` process runs in the background. |
| 5 | Count | Wait 5 s. Run `gtasks-panel`. | XML with the number of open tasks. No new fetch (state is fresh). |
| 6 | Offline | Turn off the network. Run `gtasks-panel --fetch`, then `gtasks-panel`. | Exit 1. Last count with `?`. Tooltip shows the error. |
| 7 | Revoked | Revoke the app at myaccount.google.com. Run `gtasks-panel --fetch`, then `gtasks-panel`. | Text `sign in`. |
| 8 | Panel wiring | Run `gtasks-panel --install-panel`. | Item appears left of the tray. `plugin-ids` is still an array. Run it twice: no duplicate. |
| 9 | Open | Click the item. | A Google Tasks app window opens. |
| 10 | Focus | Click again. | The same window gets focus. No new window. |
| 11 | Remove | Run `gtasks-panel --uninstall-panel`. | Item is gone. rc file removed. |
| 12 | Status | Run `gtasks-panel --status`. | Plain text: paths, token state, last count, last error, fetch idle/in progress. |
| 13 | Bad config | Put `label = {nope} 100%` in `config.ini`. Run `gtasks-panel`. | XML with the default label. No crash. |

## Commands

| Command | What it does |
|---------|--------------|
| `gtasks-panel` | Print genmon XML from the state file. Genmon runs this. Starts `--fetch` when the file is stale. |
| `gtasks-panel --fetch` | Query Google and update the state file. |
| `gtasks-panel --auth` | Sign in with Google. Then fetch one time. |
| `gtasks-panel --status` | Show state as plain text. |
| `gtasks-panel --install-panel [--period 60]` | Add the panel item. Period minimum 30. |
| `gtasks-panel --uninstall-panel` | Remove the panel item. |
| `gtasks-open` | Focus or open the Google Tasks window. |
