# gtasks-panel

Google Tasks counter for the XFCE panel.

It shows the number of open tasks in the panel. A click opens Google
Tasks as an app window. A second click focuses that window.

It uses the XFCE **Generic Monitor** plugin (genmon). Genmon runs the
`gtasks-panel` script on a timer and shows its output. There is no
compiled code.

Genmon blocks the panel while the script runs. So the script never talks
to Google directly. It reads a state file and prints it. When the file is
older than `refresh` seconds (default 300), it starts `gtasks-panel
--fetch` in the background. That process queries Google and writes the
file. The panel stays responsive when the network is slow.

## Install

Build the Debian package and install it:

```
make deb
sudo apt install ./dist/gtasks-panel_0.1.0_all.deb
```

The package depends on `xfce4-genmon-plugin`, `wmctrl`, and the Google
API Python packages from apt. It recommends `google-chrome-stable` or
`chromium`.

Without Debian:

```
sudo make install            # to /usr/local/bin
sudo make install PREFIX=/usr
```

## Setup (one time)

You need your own Google OAuth client. Google does not give a shared one,
and an API key does not work for private user data. The Tasks API has no
price. Google's limits page lists a free quota of 50,000 queries per day.
This widget uses a few hundred per day.

1. Open <https://console.cloud.google.com/>. Make a project.
2. Go to **APIs & Services → Library**. Enable **Google Tasks API**.
3. Go to **APIs & Services → OAuth consent screen**.
   - Personal Gmail account: user type **External**. After you save it,
     click **Publish app** so the status is **In production**.
   - Google Workspace account: user type **Internal**.
   - Do not leave it in **Testing**. In Testing, the sign-in expires
     after 7 days and the panel shows "sign in" again every week.
4. Go to **Credentials → Create credentials → OAuth client ID**.
   Application type **Desktop app**. Download the JSON.
5. Save the file as `~/.config/gtasks-panel/client_secret.json`.
6. Sign in. A browser opens. Accept the read-only scope.

   ```
   gtasks-panel --auth
   ```

7. Add the panel item. The panel restarts.

   ```
   gtasks-panel --install-panel
   ```

The item appears left of the system tray. Move it with
**Panel → Panel Preferences → Items** if you want another position.

### Ship your OAuth client inside the package (optional)

Put your downloaded JSON at `share/client_secret.json` in this repo and run
`make deb` again. The package then installs it as
`/usr/share/gtasks-panel/client_secret.json`. A new install only needs
`gtasks-panel --auth`. A file in `~/.config/gtasks-panel/` still wins.
The file is in `.gitignore`. Google's docs do not state a policy on
shipping desktop-app secrets. You decide.

## Commands

| Command | What it does |
|---------|--------------|
| `gtasks-panel` | Print genmon XML from the state file. Genmon runs this every minute. |
| `gtasks-panel --fetch` | Query Google and update the state file. The panel starts this by itself. |
| `gtasks-panel --auth` | Sign in with Google. Then fetch one time. |
| `gtasks-panel --status` | Show paths, token state, last count, last error. |
| `gtasks-panel --install-panel [--period 60] [--panel 0]` | Add the panel item. Period minimum 30. |
| `gtasks-panel --uninstall-panel` | Remove the panel item. |
| `gtasks-panel --version` | Print the version. |
| `gtasks-open` | Focus or open the Google Tasks window. |

## Panel states

| Panel text | Meaning | Click does |
|-----------|---------|------------|
| `7` | 7 open tasks | Open or focus Google Tasks |
| `7?` | Last count was 7. The last refresh failed. | Open Google Tasks. Tooltip shows the error. |
| `…` | No count yet. A fetch runs or failed. | Open Google Tasks. Tooltip shows the error. |
| `setup` | `client_secret.json` is missing | Open a terminal with `gtasks-panel --auth` |
| `sign in` | No token, or token expired or revoked | Same |
| `!` | The script crashed | Tooltip shows the error |

The icon changes to `task-past-due` when at least one task is overdue.
Point to the item. The tooltip lists open tasks per list.

After a failed fetch the script waits 60 seconds before it tries again.

## Files

| Path | Content |
|------|---------|
| `~/.config/gtasks-panel/client_secret.json` | Your OAuth client. You add it. |
| `~/.config/gtasks-panel/config.ini` | Optional settings. See `config.ini.example`. |
| `~/.local/state/gtasks-panel/token.json` | Saved sign-in. Mode 0600. |
| `~/.local/state/gtasks-panel/state.json` | Last count, last error, sign-in state. |
| `~/.local/state/gtasks-panel/lock` | Held while a fetch runs. |
| `~/.config/google-chrome-tasks-app/` | Browser profile for the app window. |
| `~/.config/xfce4/panel/genmon-N.rc` | Genmon item config, written by `--install-panel`. |

## How the click works

`gtasks-open` asks `wmctrl` to focus a window with class
`GoogleTasksApp`. If there is none, it starts Chrome (or Chromium) with
`--app=https://tasks.google.com`, `--class=GoogleTasksApp` and its own
`--user-data-dir`. A separate profile directory is necessary. Without it,
a Chrome that already runs takes the URL and ignores `--class`.
`gtasks-open` exits with 1 when it finds no Chrome and no Chromium.

You sign in to Google inside that window one time. That sign-in is
separate from the `--auth` sign-in.

## Troubleshooting

- **Panel shows `XXX`**: genmon could not start the command. Check that
  `gtasks-panel` is in `PATH` for the panel (`/usr/bin` or
  `/usr/local/bin`).
- **Panel shows `…`, `!` or `7?`**: point to the item and read the
  tooltip. Run `gtasks-panel --status` in a terminal. Run
  `gtasks-panel --fetch` to see the error directly.
- **Panel shows `sign in` every week**: the OAuth app is in Testing
  status. See Setup step 3.
- **Click opens a second window**: run `wmctrl -x -l`. The class must
  contain `GoogleTasksApp`. If not, set `GTASKS_WIN_CLASS` in the
  environment of the panel, or check that no other Chrome uses the same
  profile dir.
- **Count does not change after `--auth`**: genmon updates on its timer
  (1 minute by default). Wait, or restart the panel with
  `xfce4-panel -r`.
- **Count is old**: a new fetch runs every `refresh` seconds (default
  300). Set a smaller value in `config.ini`. Minimum 30.
- **Wayland**: `wmctrl` needs X11. Focus does not work on Wayland.

## Development

```
make check     # syntax checks, man page check, pytest (tests/)
make deb       # build dist/gtasks-panel_*.deb
make clean
```

The tests in `tests/` load `bin/gtasks-panel` as a module with the XDG
directories under a temporary path. They do not need Google packages or
network. `python3-pytest` from apt runs them.

Bump the version in `debian/changelog` (`dch -v 0.2.0`) before a new
build. The `Makefile` reads the version from there.
