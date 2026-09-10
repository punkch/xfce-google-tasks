"""State file, task cache, window geometry and the fetch lock."""

import datetime as dt
import fcntl
import json
import os
import tempfile
import time
from pathlib import Path
from typing import TYPE_CHECKING

from . import paths

if TYPE_CHECKING:  # `model` costs the genmon tick and the tick never needs it
    from .model import TaskList


def atomic_write(path: Path, text: str, mode: int = 0o644) -> None:
    """Write the file in one step. A reader never sees half a file.

    The temporary file has a name of its own, so two writers of the same
    file cannot write into one another's temporary file.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=path.name + ".")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            os.fchmod(fh.fileno(), mode)
            fh.write(text)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _load_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def load_state() -> dict:
    """Return the state dict. Every key of EMPTY_STATE is present."""
    data = _load_json(paths.STATE_PATH)
    if not isinstance(data, dict):
        data = {}
    return {**paths.EMPTY_STATE, **data}


def save_state(state: dict) -> None:
    atomic_write(paths.STATE_PATH, json.dumps(state))


def try_lock():
    """Return a lock fd, or None when another process holds the lock."""
    paths.STATE_DIR.mkdir(parents=True, exist_ok=True)
    fd = os.open(paths.LOCK_PATH, os.O_RDWR | os.O_CREAT, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        os.close(fd)
        return None
    return fd


def lock_held() -> bool:
    fd = try_lock()
    if fd is None:
        return True
    os.close(fd)
    return False


def error_text(exc: BaseException) -> str:
    """Short human text for an exception. google-auth errors carry tuples."""
    args = getattr(exc, "args", ())
    if args and isinstance(args[0], str):
        return args[0]
    return str(exc) or type(exc).__name__


def apply_summary(state: dict, data: dict, now: float | None = None) -> dict:
    """Put fresh counts into a state dict and clear the last error."""
    now = time.time() if now is None else now
    state.update(data, auth=paths.AUTH_OK, error=None, fetched_at=now,
                 time=dt.datetime.now().isoformat(sep=" ", timespec="seconds"))
    return state


def write_summary_if_free(summary: dict) -> bool:
    """Write new counts for the panel. False when a fetch holds the lock.

    The window calls this after a write to Google. A skipped write is not a
    problem: the next --fetch gets the same numbers.
    """
    fd = try_lock()
    if fd is None:
        return False
    try:
        save_state(apply_summary(load_state(), summary))
    finally:
        os.close(fd)
    return True


def load_cache() -> "list[TaskList] | None":
    """Task lists from the last fetch, or None when there is no cache.

    A cache written by another version of the file format is no cache.
    """
    from .model import CACHE_VERSION, lists_from_json  # only this path needs model

    data = _load_json(paths.CACHE_PATH)
    if not isinstance(data, dict) or data.get("version") != CACHE_VERSION:
        return None
    return lists_from_json(data)


def save_cache(lists: "list[TaskList]") -> None:
    """Keep the full task tree so the window can open without network."""
    from .model import lists_to_json  # only this path needs model

    atomic_write(paths.CACHE_PATH, json.dumps(lists_to_json(lists)), mode=0o600)


def load_window_state() -> dict:
    """Saved window size. Empty dict when there is none."""
    data = _load_json(paths.WINDOW_STATE_PATH)
    return data if isinstance(data, dict) else {}


def save_window_state(data: dict) -> None:
    atomic_write(paths.WINDOW_STATE_PATH, json.dumps(data))
