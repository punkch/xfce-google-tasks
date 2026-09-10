# Plan: Google Tasks panel indicator as a Debian package

Date: 2026-09-09

## Agent setup

- Main session (Fable 5.1) does all tasks. Zero subagents.
- Reason: the work is two scripts, one `debian/` folder, and docs. There
  is no parallel file boundary that gives a gain.
- Review: `/unops-toolkit:code-review` after the build and install test.
- UX check: a screenshot of the real panel after `--install-panel`.

## Task 1: Save spec documentation

Create `docs/specs/2026-09-09-1705-gtasks-genmon-panel-deb/` with
`plan.md`, `shape.md`, `standards.md`, `references.md`, `user-guide.md`.

## Task 2: `bin/gtasks-panel` (Python)

Rewrite `gtasks_count.py` from the handover file.

- Shebang `#!/usr/bin/python3`.
- Paths: `$XDG_CONFIG_HOME/gtasks-panel/client_secret.json`,
  `$XDG_STATE_HOME/gtasks-panel/token.json`,
  `$XDG_STATE_HOME/gtasks-panel/state.json` (last count, error, auth),
  `$XDG_STATE_HOME/gtasks-panel/lock`.
- Optional `$XDG_CONFIG_HOME/gtasks-panel/config.ini` with `icon`,
  `label`, `open_command`, `refresh`.
- Sub-commands:
  - no argument: print genmon XML from `state.json`. No network. Spawn
    `--fetch` detached when the state is stale.
  - `--fetch`: query Google under the file lock, write `state.json`.
  - `--auth`: run the OAuth flow in the browser, save the token, fetch once.
  - `--status`: print plain text state for debugging.
  - `--install-panel [--period SECONDS] [--panel N]`: add a genmon item.
  - `--uninstall-panel`: remove it.
- States for the panel:
  - no secret: text "setup", tooltip with the path, click opens a
    terminal with `gtasks-panel --auth`.
  - no token or refresh failed: text "sign in", click opens the same.
  - API or network error: last count with "?" suffix, tooltip shows the
    error, click opens `gtasks-open`.
  - OK: count, tooltip "N open task(s)", click opens `gtasks-open`.
  - no count yet: text "…", tooltip shows the last error if any.
- HTTP timeout 20 s, fetch deadline 60 s. `maxResults=100` on
  `tasks.list`. Pagination with `list_next`. `fields=` on both calls.
- A file lock stops two fetches at the same time.
- Use `<txtclick>` and `<icon>` + `<iconclick>`. Escape only `<txt>` and
  `<tool>`.
- `configparser` with `interpolation=None`. Validate `label`. A catch-all
  in `main` prints minimal XML on any crash.

## Task 2b: `tests/` (pytest, added after code review)

- `conftest.py` loads `bin/gtasks-panel` with `SourceFileLoader`, XDG
  dirs under `tmp_path`, `spawn_fetch` and `terminal_command` patched.
- `test_render.py`, `test_config.py`, `test_fetch.py` (fake service),
  `test_panel.py` (fake `xfconf`). `make check` runs them when
  `python3-pytest` is installed.

## Task 3: `bin/gtasks-open` (shell)

- `wmctrl -x -a GoogleTasksApp` if a window with that class exists.
- Else start `google-chrome`, or `chromium` as fallback, with
  `--app=https://tasks.google.com --class=GoogleTasksApp
  --user-data-dir=~/.config/google-chrome-tasks-app`.
- `set -u`, quoted variables, `exec` for the browser start.

## Task 4: Debian packaging

- `debian/control`: source `gtasks-panel`, binary `gtasks-panel`,
  `Architecture: all`. Depends: `python3`, `python3-googleapi`,
  `python3-google-auth-oauthlib`, `python3-google-auth-httplib2`,
  `xfce4-genmon-plugin`, `wmctrl`. Recommends:
  `google-chrome-stable | chromium`, `xfce4-terminal | x-terminal-emulator`.
- `debian/rules`: `dh $@`.
- `debian/install`: both scripts to `usr/bin`.
- `debian/docs`: `README.md`, `config.ini.example`.
- `debian/changelog`, `debian/copyright`, `debian/source/format`
  (`3.0 (native)`).
- `Makefile`: `install`, `uninstall` (PREFIX), `deb` (build to `dist/`),
  `check` (syntax checks).
- `.gitignore` for build output.

## Task 5: Docs and repo files

- `README.md`: install, Google Cloud setup, the 7-day token gotcha,
  usage, troubleshooting.
- `CLAUDE.md`: repo index.
- Move the handover file to `docs/handover.md`.

## Task 6: Build, install, verify

- `make check`.
- `make deb`, then `sudo apt install ./dist/gtasks-panel_*.deb`.
- `gtasks-panel` prints "setup" XML. `gtasks-panel --status` works.
- `gtasks-panel --install-panel`. Panel shows the item. Screenshot.
- `gtasks-open` twice: second call focuses, no second window.

## Task 7: Review

- `/unops-toolkit:code-review` on the diff. Fix findings. Re-run checks.
- Stop before commit. Ask the user.

## Out of scope

- Creating the Google Cloud OAuth client. Only the user can do this.
- Wayland support. Host runs X11. `wmctrl` needs X11.
- A compiled XFCE panel plugin.
