# Skills & Conventions for the Google Tasks panel indicator

---

## Debian packaging (debhelper 13)

- **Source:** Debian Policy and `man dh`. Host has `debhelper 13.24.2`.
- **Why it applies:** The user wants to install with the package manager.
- **Key points:**
  - `debian/source/format` = `3.0 (native)`. No orig tarball.
  - Version has no dash: `0.1.0`.
  - `Architecture: all`. Only scripts, no compiled code.
  - Depend on apt Python packages. Do not use pip. Python 3.13 on this
    host is "externally managed".
  - Build: `dpkg-buildpackage -us -uc -b`.

## Genmon output format (xfce4-genmon-plugin 4.1.1)

- **Source:** `/usr/share/doc/xfce4-genmon-plugin/README.gz` and the
  plugin source, tag `xfce4-genmon-plugin-4.1.1`.
- **Key points:**
  - Tags: `<txt>`, `<txtclick>`, `<icon>`, `<iconclick>`, `<img>`,
    `<click>`, `<tool>`, `<bar>`.
  - `<click>` binds to the image. `<txtclick>` binds to the text.
  - `<txt>` and `<tool>` accept Pango markup. Escape user data.
  - Config file: `~/.config/xfce4/panel/genmon-N.rc`. Keys: `Command`,
    `UseLabel` (0/1), `Text`, `UpdatePeriod` (milliseconds), `Font`.

## Google OAuth 2.0 for installed apps

- **Source:** Google Identity docs (via google-developer-knowledge MCP).
- **Key points:**
  - Desktop-app client. `InstalledAppFlow.run_local_server(port=0)`.
  - Scope `https://www.googleapis.com/auth/tasks.readonly`.
  - "Testing" publishing status: refresh tokens expire after 7 days.
    Set the app to "In production" for a long-lived token.

## User global rules

- ASD-STE100 in all docs and chat.
- Conventional commits. Commit only after user confirmation.
- Keep `CLAUDE.md` current in the same change.
