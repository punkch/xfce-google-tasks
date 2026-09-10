"""gtasks-panel: Google Tasks counter for the XFCE Generic Monitor plugin.

Without options it prints genmon XML with the number of open tasks. Genmon
runs it on a timer and blocks the panel until it exits, so this path does
no network I/O: it reads the state file and, when that is stale, starts a
detached `--fetch` process that talks to Google and updates the file.

Other modes:

  --fetch            Query Google and update the state file (background).
  --auth             Sign in with Google (opens a browser).
  --status           Print the current state as plain text.
  --install-panel    Add a Generic Monitor item that runs this script.
  --uninstall-panel  Remove that item again.

Files:
  $XDG_CONFIG_HOME/gtasks-panel/client_secret.json  OAuth client (you add it)
  $XDG_CONFIG_HOME/gtasks-panel/config.ini          optional settings
  $XDG_STATE_HOME/gtasks-panel/token.json           saved sign-in
  $XDG_STATE_HOME/gtasks-panel/state.json           last count and errors
  $XDG_CACHE_HOME/gtasks-panel/tasks.json           tasks for the window
"""

import argparse
import os
import re
import shutil
import subprocess
import sys
import time
from html import escape
from pathlib import Path

from typing import TYPE_CHECKING

from . import auth, config, paths, state
from .paths import APP, AUTH_NO_SECRET, AUTH_NO_TOKEN, AUTH_OK, AUTH_REAUTH

if TYPE_CHECKING:  # `model` costs the tick and only the window path needs it
    from .model import TaskList

_ENTRY: Path | None = None
# The genmon plugin id, remembered after the first lookup (see refresh_panel_item).
_PLUGIN_ID: int | None = None


def configure(entry: Path | None = None) -> None:
    """Remember the path of the entry script that started us."""
    global _ENTRY
    if entry is not None:
        _ENTRY = Path(entry)


def entry_path() -> Path:
    """The CLI script. `configure` sets it; else look beside us and on PATH."""
    if _ENTRY is not None:
        return _ENTRY
    beside = Path(__file__).resolve().parent.parent / "bin" / APP
    return beside if beside.is_file() else Path(shutil.which(APP) or f"/usr/bin/{APP}")


# --------------------------------------------------------------------------
# Background fetch
# --------------------------------------------------------------------------

def run_fetch() -> int:
    """Background worker: update the state file. Returns an exit code."""
    lock_fd = state.try_lock()
    if lock_fd is None:
        return 1
    try:
        return _fetch_locked()
    finally:
        os.close(lock_fd)


def _fetch_locked() -> int:
    # Only this path talks to Google. The tick must not pay for the import.
    from . import api

    data_file = state.load_state()
    now = time.time()
    try:
        creds, verdict = auth.load_credentials()
        if verdict in (AUTH_NO_SECRET, AUTH_NO_TOKEN):
            return 1  # the tick reports these from the file checks
        if verdict == AUTH_REAUTH:
            data_file["auth"] = AUTH_REAUTH
            state.save_state(data_file)
            return 1
        data = api.fetch_summary(creds)
    except ImportError as exc:
        data_file.update(error=f"Python module missing: {exc}. Install "
                         "python3-googleapi, python3-google-auth-oauthlib, "
                         "python3-google-auth-httplib2 and python3-httplib2.",
                         error_at=now)
        state.save_state(data_file)
        return 1
    except Exception as exc:
        if auth.needs_reauth(exc):
            data_file["auth"] = AUTH_REAUTH
        else:  # network, API, timeout: keep the last count
            data_file.update(error=state.error_text(exc), error_at=now)
        state.save_state(data_file)
        return 1
    state.save_state(state.apply_summary(data_file, data, now))
    return 0


def spawn_fetch() -> None:
    """Start --fetch detached. It must not inherit genmon's pipes."""
    subprocess.Popen(
        [sys.executable, str(entry_path()), "--fetch"],
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        start_new_session=True,
    )


def is_stale(counts: dict, refresh: int) -> bool:
    """True when a new fetch is due."""
    if counts["count"] is None and not counts["error"]:
        return True
    failed_since_success = counts["error_at"] > counts["fetched_at"]
    last = max(counts["fetched_at"], counts["error_at"])
    wait = paths.RETRY_AFTER if failed_since_success else refresh
    return time.time() - last >= wait


# --------------------------------------------------------------------------
# Genmon output (the tick; no network)
# --------------------------------------------------------------------------

def emit(txt: str, tooltip: str, click: str, icon: str) -> None:
    """Print the genmon XML block.

    <txt> and <tool> are Pango markup sinks and get escaped. Genmon passes
    <icon> and the click commands through verbatim, so they must not be.
    """
    if icon:
        print(f"<icon>{icon}</icon>")
        print(f"<iconclick>{click}</iconclick>")
    print(f"<txt>{escape(txt, quote=False)}</txt>")
    print(f"<txtclick>{click}</txtclick>")
    print(f"<tool>{escape(tooltip, quote=False)}</tool>")


def summary_tooltip(counts: dict, note: str = "") -> str:
    lines = [f"{counts['count']} open task(s)"]
    if counts["overdue"]:
        lines[0] += f", {counts['overdue']} overdue"
    for title, count in counts["lists"]:
        lines.append(f"  {title}: {count}")
    if counts["time"]:
        lines.append(f"Updated {counts['time']}")
    if note:
        lines.append(note)
    return "\n".join(lines)


def render(cfg: dict) -> None:
    """Print the panel state. Reads files only; never talks to Google."""
    # Every state opens the window: it shows the sign-in page when needed.
    open_cmd = cfg["open_command"]

    if not paths.SECRET_PATH.is_file():
        emit("setup", "Google Tasks: no OAuth client.\n"
             f"Put client_secret.json in {paths.CONFIG_DIR}\n"
             "then click here to sign in. See README.", open_cmd, cfg["icon"])
        return
    if not paths.TOKEN_PATH.is_file():
        emit("sign in", "Google Tasks: not signed in.\nClick to sign in.",
             open_cmd, cfg["icon"])
        return

    counts = state.load_state()
    if counts["auth"] == AUTH_REAUTH:
        emit("sign in", "Google Tasks: sign-in expired or revoked.\nClick to sign in.",
             open_cmd, cfg["icon"])
        return

    if is_stale(counts, cfg["refresh"]) and not state.lock_held():
        spawn_fetch()

    icon = cfg["icon_overdue"] if counts["overdue"] and cfg["icon_overdue"] else cfg["icon"]
    if counts["count"] is None:
        note = f"\nLast error: {counts['error']}" if counts["error"] else ""
        emit("…", f"Google Tasks: fetching…{note}", open_cmd, icon)
        return

    txt = cfg["label"].format(count=counts["count"])
    note = ""
    if counts["error"] and counts["error_at"] > counts["fetched_at"]:
        txt += "?"
        note = f"Refresh failed: {counts['error']}"
    emit(txt, summary_tooltip(counts, note), open_cmd, icon)


# --------------------------------------------------------------------------
# Panel wiring (xfce4-genmon-plugin 4.1.x: rc file + xfconf plugin list)
# --------------------------------------------------------------------------

def xfconf(*args, check=True):
    return subprocess.run(
        ["xfconf-query", "-c", paths.XFCONF_CHANNEL, *args],
        capture_output=True, text=True, check=check,
    ).stdout


def xfconf_int_list(prop):
    """Parse an int array property. Returns [] when the property is absent."""
    out = xfconf("-p", prop, check=False)
    return [int(line) for line in out.splitlines() if line.strip().isdigit()]


_PLUGIN_LINE = re.compile(r"^/plugins/plugin-(\d+)\s+(\S+)$")


def plugin_types() -> dict:
    """Return {plugin_id: type} for every panel plugin."""
    result = {}
    for line in xfconf("-p", "/plugins", "-l", "-v", check=False).splitlines():
        match = _PLUGIN_LINE.match(line.strip())
        if match:
            result[int(match.group(1))] = match.group(2)
    return result


def panel_numbers():
    return xfconf_int_list("/panels")


def genmon_rc(plugin_id: int) -> Path:
    return paths.PANEL_RC_DIR / f"genmon-{plugin_id}.rc"


def find_installed(types: dict):
    """Return the plugin id of an existing genmon item that runs us, or None."""
    for plugin_id, kind in sorted(types.items()):
        if kind != "genmon":
            continue
        try:
            text = genmon_rc(plugin_id).read_text(encoding="utf-8")
        except OSError:
            continue
        if any(line.startswith("Command=") and APP in line for line in text.splitlines()):
            return plugin_id
    return None


def set_plugin_ids(panel: int, ids: list) -> None:
    prop = f"/panels/panel-{panel}/plugin-ids"
    if not ids:
        xfconf("-p", prop, "-r", check=False)
        return
    args = ["-p", prop, "-a"]
    for plugin_id in ids:
        args += ["-t", "int", "-s", str(plugin_id)]
    xfconf(*args)


def panel_process_ids() -> set:
    out = subprocess.run(["pgrep", "-x", "-u", str(os.getuid()), "xfce4-panel"],
                         capture_output=True, text=True).stdout
    return set(out.split())


def restart_panel() -> bool:
    """Restart the panel and wait until the new process is up (max 15 s).

    The old panel writes every plugin's rc file when it exits. Anything that
    must not come back (a removed rc) has to be deleted after this returns.
    """
    old = panel_process_ids()
    subprocess.Popen(["xfce4-panel", "-r"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(30):
        time.sleep(0.5)
        now = panel_process_ids()
        if now and not (now & old):
            time.sleep(1.0)  # let the new panel finish loading plugins
            return True
    return False


def restart_message(restarted: bool) -> str:
    return "Panel restarted." if restarted else "Panel restart not confirmed. Run: xfce4-panel -r"


def require_panel() -> None:
    if not shutil.which("xfconf-query"):
        sys.exit("xfconf-query not found. Install the xfconf package.")
    if not panel_process_ids():
        sys.exit("xfce4-panel is not running.")


def install_panel(period: int, panel: int) -> None:
    require_panel()
    types = plugin_types()
    existing = find_installed(types)
    if existing is not None:
        print(f"Already installed as plugin-{existing}. Nothing to do.")
        return
    if panel not in panel_numbers():
        sys.exit(f"Panel {panel} does not exist. Panels: {panel_numbers()}")

    new_id = max(types, default=0) + 1
    # Absolute path: the panel's PATH may not contain the install dir.
    genmon_rc(new_id).parent.mkdir(parents=True, exist_ok=True)
    genmon_rc(new_id).write_text(
        f"Command={entry_path()}\nUseLabel=0\nText=Tasks\nUpdatePeriod={period * 1000}\n",
        encoding="utf-8",
    )
    xfconf("-p", f"/plugins/plugin-{new_id}", "-n", "-t", "string", "-s", "genmon")

    ids = xfconf_int_list(f"/panels/panel-{panel}/plugin-ids")
    anchor = next((i for i, plugin_id in enumerate(ids) if types.get(plugin_id) == "systray"),
                  len(ids))
    ids.insert(anchor, new_id)
    set_plugin_ids(panel, ids)
    restarted = restart_panel()
    print(f"Installed as plugin-{new_id} on panel {panel}, period {period}s. "
          + restart_message(restarted))


def uninstall_panel() -> None:
    require_panel()
    plugin_id = find_installed(plugin_types())
    if plugin_id is None:
        print("Not installed in any panel. Nothing to do.")
        return
    for panel in panel_numbers():
        ids = xfconf_int_list(f"/panels/panel-{panel}/plugin-ids")
        if plugin_id in ids:
            set_plugin_ids(panel, [i for i in ids if i != plugin_id])
    xfconf("-p", f"/plugins/plugin-{plugin_id}", "-r", "-R", check=False)
    restarted = restart_panel()
    # Delete the rc only now: the old panel re-wrote it while shutting down.
    try:
        genmon_rc(plugin_id).unlink()
    except FileNotFoundError:
        pass
    print(f"Removed plugin-{plugin_id}. " + restart_message(restarted))


def refresh_panel_item() -> bool:
    """Make the panel item run its tick now. False when there is no item.

    The lookup reads every genmon rc file, so the id is kept. A failed
    event means the panel changed, and the next call looks again.
    """
    global _PLUGIN_ID
    if not (shutil.which("xfconf-query") and shutil.which("xfce4-panel")):
        return False
    plugin_id = _PLUGIN_ID
    if plugin_id is None:
        plugin_id = find_installed(plugin_types())
        if plugin_id is None:
            return False
    try:
        done = subprocess.run(
            ["xfce4-panel", f"--plugin-event=genmon-{plugin_id}:refresh:bool:true"],
            capture_output=True, text=True, check=False)
    except OSError:
        _PLUGIN_ID = None
        return False
    _PLUGIN_ID = plugin_id if done.returncode == 0 else None
    return done.returncode == 0


def notify_summary(lists: "list[TaskList]") -> bool:
    """Window helper: save the new counts and redraw the panel item."""
    from .model import summary  # only the window path needs model

    if not state.write_summary_if_free(summary(lists)):
        return False
    return refresh_panel_item()


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def show_status() -> None:
    counts = state.load_state()
    print(f"config dir : {paths.CONFIG_DIR}")
    print(f"secret     : {paths.SECRET_PATH} "
          f"({'present' if paths.SECRET_PATH.is_file() else 'MISSING'})")
    print(f"token      : {paths.TOKEN_PATH} "
          f"({'present' if paths.TOKEN_PATH.is_file() else 'missing'})")
    print(f"auth       : {counts['auth']}")
    if shutil.which("xfconf-query"):
        plugin_id = find_installed(plugin_types())
        print(f"panel item : {'plugin-' + str(plugin_id) if plugin_id is not None else 'not installed'}")
    if counts["count"] is None:
        print("last count : none yet")
    else:
        print(f"last count : {counts['count']} open, {counts['overdue']} overdue, at {counts['time'] or 'unknown'}")
    if counts["error"]:
        print(f"last error : {counts['error']} (at {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(counts['error_at']))})")
    print(f"fetch      : {'in progress' if state.lock_held() else 'idle'}")


def period_type(text: str) -> int:
    value = int(text)
    if value < 30:
        raise argparse.ArgumentTypeError("period must be at least 30 seconds")
    return value


def main(argv=None, entry: Path | None = None) -> int:
    from . import VERSION

    configure(entry)
    parser = argparse.ArgumentParser(prog=APP, description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--version", action="version", version=f"{APP} {VERSION}")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--fetch", action="store_true", help="update the state file (background)")
    group.add_argument("--auth", action="store_true", help="sign in with Google")
    group.add_argument("--status", action="store_true", help="print state as plain text")
    group.add_argument("--install-panel", action="store_true", help="add the panel item")
    group.add_argument("--uninstall-panel", action="store_true", help="remove the panel item")
    parser.add_argument("--period", type=period_type, default=60, metavar="SECONDS",
                        help="genmon tick for --install-panel (default 60, minimum 30)")
    parser.add_argument("--panel", type=int, default=0, metavar="N",
                        help="panel number for --install-panel (default 0)")
    args = parser.parse_args(argv)

    if args.fetch:
        return run_fetch()
    if args.auth:
        auth.run_auth_flow()
        print(f"Signed in. Token saved to {paths.TOKEN_PATH}")
        counts = state.load_state()
        counts.update(auth=AUTH_OK, error=None)
        state.save_state(counts)
        if run_fetch() == 0:
            print(f"{state.load_state()['count']} open task(s). "
                  "The panel shows it on its next tick.")
        else:
            reason = state.load_state()["error"] or "another fetch is running"
            print(f"First fetch failed: {reason}. The panel retries by itself.")
        return 0
    if args.status:
        show_status()
        return 0
    if args.install_panel:
        install_panel(args.period, args.panel)
        return 0
    if args.uninstall_panel:
        uninstall_panel()
        return 0

    try:
        render(config.load_config())
    except Exception as exc:  # last resort: genmon must still get XML
        print(f"<txt>!</txt>\n"
              f"<tool>{escape(f'{APP} error: {state.error_text(exc)}', quote=False)}</tool>")
    return 0
