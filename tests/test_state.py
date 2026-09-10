"""State file, fetch lock, task cache and window geometry."""

import datetime as dt
import json
import os

from gtasks_panel import model, state

COUNTS = {"count": 3, "overdue": 1, "lists": [["Work", 3]]}


def sample_lists():
    return [model.TaskList("1", "Work", [
        model.Task(id="a", list_id="1", title="Pay", due=dt.date(2026, 9, 1))])]


def test_write_summary_if_free_updates_the_state(mod):
    assert state.write_summary_if_free(COUNTS) is True
    saved = state.load_state()
    assert (saved["count"], saved["overdue"]) == (3, 1)
    assert saved["auth"] == mod.paths.AUTH_OK
    assert saved["error"] is None
    assert saved["fetched_at"] > 0 and saved["time"]


def test_write_summary_if_free_skips_a_running_fetch(mod):
    lock_fd = state.try_lock()
    try:
        assert state.write_summary_if_free(COUNTS) is False
        assert not mod.paths.STATE_PATH.exists()
    finally:
        os.close(lock_fd)
    assert state.write_summary_if_free(COUNTS) is True


def test_cache_round_trip(mod):
    assert state.load_cache() is None
    state.save_cache(sample_lists())
    back = state.load_cache()
    assert [task.title for task in back[0].tasks] == ["Pay"]
    assert back[0].tasks[0].due == dt.date(2026, 9, 1)
    assert oct(mod.paths.CACHE_PATH.stat().st_mode & 0o777) == "0o600"
    mod.paths.CACHE_PATH.write_text("not json")
    assert state.load_cache() is None


def test_a_cache_of_another_version_is_no_cache(mod):
    state.save_cache(sample_lists())
    data = json.loads(mod.paths.CACHE_PATH.read_text())
    assert data["version"] == model.CACHE_VERSION
    data["version"] = model.CACHE_VERSION + 1
    mod.paths.CACHE_PATH.write_text(json.dumps(data))
    assert state.load_cache() is None
    del data["version"]
    mod.paths.CACHE_PATH.write_text(json.dumps(data))
    assert state.load_cache() is None


def test_window_state_round_trip(mod):
    assert state.load_window_state() == {}
    state.save_window_state({"width": 900, "height": 600})
    assert state.load_window_state()["width"] == 900
    mod.paths.WINDOW_STATE_PATH.write_text("[]")
    assert state.load_window_state() == {}


def test_atomic_write_replaces_and_leaves_no_temp_file(mod):
    path = mod.paths.STATE_DIR / "x.json"
    state.atomic_write(path, "1", mode=0o600)
    state.atomic_write(path, "2", mode=0o600)
    assert path.read_text() == "2"
    assert list(mod.paths.STATE_DIR.glob("x.json.*")) == []
    assert oct(path.stat().st_mode & 0o777) == "0o600"
