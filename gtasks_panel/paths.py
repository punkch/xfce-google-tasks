"""File locations and constants.

Every path here comes from the environment at import time. Other modules
read the path names as `paths.NAME`, never `from .paths import NAME`, so a
test can reload this module and point them at a scratch directory. The
plain constants (APP, the timeouts, DEFAULTS, AUTH_*) do not change with
the environment and may be imported by name.
"""

import os
from pathlib import Path

APP = "gtasks-panel"

HTTP_TIMEOUT = 20      # seconds per socket operation
FETCH_DEADLINE = 60    # seconds for one whole fetch
RETRY_AFTER = 60       # seconds before a fetch is retried after an error

XDG_CONFIG_HOME = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
XDG_STATE_HOME = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local" / "state"))
XDG_CACHE_HOME = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))

CONFIG_DIR = XDG_CONFIG_HOME / APP
STATE_DIR = XDG_STATE_HOME / APP
CACHE_DIR = XDG_CACHE_HOME / APP

USER_SECRET_PATH = CONFIG_DIR / "client_secret.json"
# The user's own file wins. A packaged one (see Makefile) is the fallback.
SECRET_PATH = next(
    (p for p in (USER_SECRET_PATH,
                 Path("/usr/share/gtasks-panel/client_secret.json"),
                 Path("/usr/local/share/gtasks-panel/client_secret.json"))
     if p.is_file()),
    USER_SECRET_PATH,
)
CONFIG_PATH = CONFIG_DIR / "config.ini"
TOKEN_PATH = STATE_DIR / "token.json"
STATE_PATH = STATE_DIR / "state.json"
LOCK_PATH = STATE_DIR / "lock"
WINDOW_STATE_PATH = STATE_DIR / "window.json"
CACHE_PATH = CACHE_DIR / "tasks.json"

PANEL_RC_DIR = XDG_CONFIG_HOME / "xfce4" / "panel"
XFCONF_CHANNEL = "xfce4-panel"

# Auth verdicts. The first two come from file checks, the rest from Google.
AUTH_NO_SECRET = "no_secret"
AUTH_NO_TOKEN = "no_token"
AUTH_REAUTH = "reauth"
AUTH_OK = "ok"

DEFAULTS = {
    "icon": "task-due",
    "icon_overdue": "task-past-due",
    "label": "{count}",
    "open_command": "gtasks-window",
    "refresh": "300",
    "default_list": "",
}

EMPTY_STATE = {
    "count": None,
    "overdue": 0,
    "lists": [],
    "fetched_at": 0.0,
    "time": "",
    "error": None,
    "error_at": 0.0,
    "auth": AUTH_OK,
}
