# References for gtasks-panel 0.2.0 (GTK window)

Line numbers are for the 0.1.0 tree at commit `69a66ee`.

## `bin/gtasks-panel` (0.1.0, the code to split)

- **Location:** `bin/gtasks-panel`.
- **Relevance:** All of it moves into `gtasks_panel/`. Behaviour must
  stay the same.
- **Key patterns:**
  - Lines 41–63: `SCOPES`, `SELF`, XDG paths, `STATE_PATH`, `LOCK_PATH`.
    `SELF` leaves the package; the entry script passes its path in.
  - Lines 117–160: `atomic_write`, `load_state`, `save_state`,
    `try_lock`, `lock_held`. The window reuses `try_lock` for
    `write_summary_if_free`.
  - Lines 177–232: `load_credentials` returns `(creds, verdict)`.
    Add the scope check here.
  - Lines 233–277: `iter_items`, `build_service`, `fetch_summary` with
    the `service=` seam. New write functions follow the same seam.
  - Lines 278–328: `run_fetch` (lock, `finally` close) and
    `_fetch_locked`; `spawn_fetch` with `DEVNULL` stdio and
    `start_new_session`.
  - Lines 353–454: `emit` (escape `<txt>` and `<tool>` only) and
    `render`. The `setup` and `sign in` clicks change to
    `gtasks-window`.
  - Line 455: `find_installed(types)` gives the genmon plugin id for
    the plugin-event.

## `tests/conftest.py`

- **Location:** `tests/conftest.py`, fixture `mod` at line 15.
- **Relevance:** Loads the script as a module with XDG dirs under
  `tmp_path` and patches `spawn_fetch` and `terminal_command`. After
  the split it imports the package and patches the same seams.
- **Key patterns:** helpers `xml(mod, capsys, cfg)` and `tag(out, name)`
  at lines 49–58 parse the genmon output.

## `tests/test_fetch.py`

- **Location:** `tests/test_fetch.py`.
- **Relevance:** `FakeService`, `FakeCollection`, `FakeRequest` (lines
  9–42) are the pattern for `tests/test_api.py`. Extend `FakeCollection`
  to record `insert`, `patch`, `move`, `delete` calls.

## genmon plugin source

- **Location:** scratchpad `genmon-src/panel-plugin/main.c`, tag
  `xfce4-genmon-plugin-4.1.1`.
- **Relevance:** Click binding (`clicked` on GtkButton, lines
  1211–1232) and the remote event handler (line 1271) that re-runs the
  command.

## google-auth credentials loader

- **Location:**
  `/usr/lib/python3/dist-packages/google/oauth2/credentials.py`,
  `from_authorized_user_info`.
- **Relevance:** The `scopes` argument overrides the file's scopes.
  Load with `scopes=None` to see what the token really has.

## XFCE panel xfconf layout on this host

- Channel `xfce4-panel`, `/panels/panel-N/plugin-ids` (int array, write
  with `-a`), `/plugins/plugin-N` (type string). Unchanged from 0.1.0.
