import time

from conftest import tag, xml


def test_no_secret_shows_setup(mod, capsys):
    out = xml(mod, capsys)
    assert tag(out, "txt") == "setup"
    assert "--auth" in tag(out, "txtclick")
    assert not mod.spawned


def test_no_token_shows_sign_in(mod, capsys):
    mod.USER_SECRET_PATH.parent.mkdir(parents=True)
    mod.USER_SECRET_PATH.write_text("{}")
    out = xml(mod, capsys)
    assert tag(out, "txt") == "sign in"
    assert not mod.spawned


def test_reauth_state_shows_sign_in(files, capsys):
    files.save_state({**files.EMPTY_STATE, "auth": files.AUTH_REAUTH, "count": 3})
    out = xml(files, capsys)
    assert tag(out, "txt") == "sign in"
    assert "expired" in tag(out, "tool")
    assert not files.spawned


def test_empty_state_spawns_fetch_and_shows_ellipsis(files, capsys):
    out = xml(files, capsys)
    assert tag(out, "txt") == "…"
    assert files.spawned


def test_fresh_state_shows_count_without_fetch(files, capsys):
    files.save_state({**files.EMPTY_STATE, "count": 7, "overdue": 0,
                      "lists": [["Inbox", 7]], "fetched_at": time.time(), "time": "now"})
    out = xml(files, capsys)
    assert tag(out, "txt") == "7"
    assert "Inbox: 7" in tag(out, "tool")
    assert tag(out, "icon") == "task-due"
    assert tag(out, "txtclick") == "gtasks-open"
    assert not files.spawned


def test_stale_state_spawns_fetch_and_keeps_count(files, capsys):
    files.save_state({**files.EMPTY_STATE, "count": 7, "fetched_at": time.time() - 1000})
    out = xml(files, capsys)
    assert tag(out, "txt") == "7"
    assert files.spawned


def test_overdue_uses_overdue_icon(files, capsys):
    files.save_state({**files.EMPTY_STATE, "count": 2, "overdue": 1, "fetched_at": time.time()})
    out = xml(files, capsys)
    assert tag(out, "icon") == "task-past-due"
    assert "1 overdue" in tag(out, "tool")


def test_error_after_success_shows_question_mark(files, capsys):
    now = time.time()
    files.save_state({**files.EMPTY_STATE, "count": 7, "fetched_at": now - 10,
                      "error": "Name or service not known", "error_at": now})
    out = xml(files, capsys)
    assert tag(out, "txt") == "7?"
    assert "Refresh failed: Name or service not known" in tag(out, "tool")


def test_error_and_no_count_shows_ellipsis_with_error(files, capsys):
    files.save_state({**files.EMPTY_STATE, "error": "boom", "error_at": time.time()})
    out = xml(files, capsys)
    assert tag(out, "txt") == "…"
    assert "Last error: boom" in tag(out, "tool")
    assert not files.spawned  # RETRY_AFTER not reached yet


def test_lock_held_does_not_spawn(files, capsys, monkeypatch):
    monkeypatch.setattr(files, "lock_held", lambda: True)
    xml(files, capsys)
    assert not files.spawned


def test_text_is_escaped_but_click_is_not(files, capsys):
    files.save_state({**files.EMPTY_STATE, "count": 1, "lists": [["A & B <x>", 1]],
                      "fetched_at": time.time()})
    cfg = dict(files.DEFAULTS, refresh=300, label="<{count}>", open_command="sh -c 'a && b'")
    out = xml(files, capsys, cfg)
    assert tag(out, "txt") == "&lt;1&gt;"
    assert "A &amp; B &lt;x&gt;" in tag(out, "tool")
    assert tag(out, "txtclick") == "sh -c 'a && b'"
    assert tag(out, "iconclick") == "sh -c 'a && b'"


def test_main_catch_all_prints_xml(mod, capsys, monkeypatch):
    def boom(cfg):
        raise RuntimeError("bad <thing>")
    monkeypatch.setattr(mod, "render", boom)
    assert mod.main([]) == 0
    out = capsys.readouterr().out
    assert tag(out, "txt") == "!"
    assert "bad &lt;thing&gt;" in tag(out, "tool")


def test_is_stale_rules(mod):
    now = time.time()
    assert mod.is_stale({**mod.EMPTY_STATE}, 300)
    assert not mod.is_stale({**mod.EMPTY_STATE, "count": 1, "fetched_at": now}, 300)
    assert mod.is_stale({**mod.EMPTY_STATE, "count": 1, "fetched_at": now - 301}, 300)
    failed = {**mod.EMPTY_STATE, "count": 1, "fetched_at": now - 100,
              "error": "x", "error_at": now - 30}
    assert not mod.is_stale(failed, 300)
    assert mod.is_stale({**failed, "error_at": now - 61}, 300)
