# Google Tasks panel indicator — Shaping Notes

## Scope

Build an XFCE panel item that shows the number of open Google Tasks.
The item uses the Generic Monitor plugin (genmon). Genmon runs a script
and shows the script output in the panel.

A click on the item focuses the Google Tasks app window. If no window is
open, it opens one.

Ship the item as a Debian package (`.deb`). The user wants to install it
with the package manager.

Input: `gtasks-widget-handover.md` in the repo root. It has two draft
scripts. This spec reviews and improves them.

## Decisions

- **Shaping was done from the handover file.** The user was not available
  to answer the shape-spec interview questions. The handover file gives
  the scope, the constraints, and the reference scripts.
- **No new XFCE plugin in C.** A genmon script is enough. Genmon widgets
  are only scripts. Nothing is compiled.
- **Package format is a native Debian package.** The host is Parrot 7.3
  (Debian 13 base). All Python dependencies exist in apt. The package
  depends on them. No pip, no venv.
- **Two commands in `/usr/bin`:** `gtasks-panel` (Python) and
  `gtasks-open` (shell). No `.py` or `.sh` suffix.
- **XDG paths, not script-relative paths.** The scripts live in
  `/usr/bin`, which is read-only. Secrets and tokens go to
  `~/.config/gtasks-panel/` and `~/.local/state/gtasks-panel/`.
- **Never start the OAuth browser flow from the genmon tick.** Genmon
  runs the script every period. A browser pop-up every 5 minutes is not
  acceptable. `gtasks-panel --auth` is an explicit command.
- **Show a "setup" or "sign in" state in the panel** when the secret or
  the token is missing. A click on that state opens a terminal that runs
  `gtasks-panel --auth`.
- **Keep the last good count.** On a network or API error, show the last
  count with a warning mark, not only "!".
- **The genmon tick does no network I/O** (added after code review).
  Genmon runs the command synchronously inside the panel's GTK loop, so a
  slow network froze the whole panel. The tick reads `state.json` and
  starts `gtasks-panel --fetch` detached when the file is older than
  `refresh` seconds. The fetch takes a file lock, has a 60 s deadline, and
  writes count, error, and the sign-in verdict to the file.
- **Use `<txtclick>`.** Genmon binds `<click>` to the image, not the text.
- **`gtasks-panel --install-panel` wires the panel item.** Genmon 4.1.1
  stores its config in `~/.config/xfce4/panel/genmon-N.rc`. The panel
  plugin list is in xfconf. The command writes both and restarts the panel.
- **Chrome app window class is `tasks.google.com.GoogleTasksApp`.**
  Verified with `wmctrl -x -l` on this host. `wmctrl -x -a GoogleTasksApp`
  focuses it.
- **Fallback to `chromium`** when `google-chrome` is not installed.
- **Read-only scope** (`tasks.readonly`). The script never changes tasks.
- **Single thread, zero subagents.** The work is two scripts and a
  `debian/` folder. Fan-out gives no gain.

## Constraints and known risks

- The user must create a Google Cloud OAuth client (Desktop app). This
  cannot be automated.
- OAuth apps in "Testing" status give refresh tokens that expire after
  7 days. The user must set the consent screen to "In production", or use
  "Internal" type on a Workspace account. Source: Google OAuth 2.0 docs
  (checked via the google-developer-knowledge server).
- `--class` on Chrome works only with a separate `--user-data-dir`. If a
  Chrome with the same profile already runs, Chrome hands the URL to it
  and ignores `--class`.
- `tasks.list` returns max 100 items per page. Pagination stays.

## Context

- **Visuals:** None.
- **References:** `gtasks-widget-handover.md`; genmon source
  (`gitlab.xfce.org/panel-plugins/xfce4-genmon-plugin`, tag 4.1.1 and
  master); panel xfconf tree on this host.
- **Product alignment:** N/A. No `docs/product/` folder.

## Skills & Conventions Applied

- Debian packaging with debhelper 13 — the host has `debuild` and
  `dpkg-buildpackage`. Native source format `3.0 (native)`.
- Global user rules: conventional commits, ASD-STE100 in docs, keep
  CLAUDE.md updated.
