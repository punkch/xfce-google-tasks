"""Panel wiring against a fake xfconf-query."""

import os
import types

from gtasks_panel import model, state


def fake_run(calls, returncode=0):
    def run(cmd, **kwargs):
        calls.append(cmd)
        return types.SimpleNamespace(returncode=returncode, stdout="", stderr="")
    return run


def test_plugin_types_parses_listing(mod, monkeypatch):
    listing = "/plugins/plugin-1    launcher\n/plugins/plugin-2  genmon\n/plugins/plugin-19 systray\n"
    monkeypatch.setattr(mod, "xfconf", lambda *a, **k: listing)
    assert mod.plugin_types() == {1: "launcher", 2: "genmon", 19: "systray"}


def test_find_installed_reads_rc(mod, monkeypatch):
    mod.paths.PANEL_RC_DIR.mkdir(parents=True)
    mod.genmon_rc(2).write_text("Command=/usr/bin/gtasks-panel\nUseLabel=0\n")
    mod.genmon_rc(3).write_text("Command=date\n")
    assert mod.find_installed({2: "genmon", 3: "genmon", 4: "genmon"}) == 2
    assert mod.find_installed({3: "genmon"}) is None


def test_set_plugin_ids_uses_array_flag(mod, monkeypatch):
    calls = []
    monkeypatch.setattr(mod, "xfconf", lambda *a, **k: calls.append(a) or "")
    mod.set_plugin_ids(0, [7])
    assert calls[-1] == ("-p", "/panels/panel-0/plugin-ids", "-a", "-t", "int", "-s", "7")
    mod.set_plugin_ids(0, [])
    assert calls[-1] == ("-p", "/panels/panel-0/plugin-ids", "-r")


def test_install_inserts_before_systray(mod, monkeypatch, capsys):
    calls = []

    def fake_xfconf(*args, check=True):
        calls.append(args)
        if args[:2] == ("-p", "/plugins") and "-l" in args:
            return "/plugins/plugin-1 launcher\n/plugins/plugin-19 systray\n/plugins/plugin-5 clock\n"
        if args == ("-p", "/panels"):
            return "0\n"
        if args == ("-p", "/panels/panel-0/plugin-ids"):
            return "Value is an array with 3 items:\n\n1\n19\n5\n"
        return ""

    monkeypatch.setattr(mod, "xfconf", fake_xfconf)
    monkeypatch.setattr(mod, "require_panel", lambda: None)
    monkeypatch.setattr(mod, "restart_panel", lambda: True)
    mod.install_panel(60, 0)
    rc = mod.genmon_rc(20).read_text()
    command = next(line for line in rc.splitlines() if line.startswith("Command="))
    assert command.endswith("bin/gtasks-panel")  # the entry script, not the module
    assert "UpdatePeriod=60000\n" in rc
    assert ("-p", "/plugins/plugin-20", "-n", "-t", "string", "-s", "genmon") in calls
    assert calls[-1] == ("-p", "/panels/panel-0/plugin-ids", "-a",
                         "-t", "int", "-s", "1", "-t", "int", "-s", "20",
                         "-t", "int", "-s", "19", "-t", "int", "-s", "5")
    assert "plugin-20" in capsys.readouterr().out


def test_uninstall_removes_rc_after_restart(mod, monkeypatch, capsys):
    mod.paths.PANEL_RC_DIR.mkdir(parents=True)
    mod.genmon_rc(20).write_text("Command=/usr/bin/gtasks-panel\n")
    order = []

    def fake_xfconf(*args, check=True):
        order.append(args)
        if args[:2] == ("-p", "/plugins") and "-l" in args:
            return "/plugins/plugin-20 genmon\n"
        if args == ("-p", "/panels"):
            return "0\n"
        if args == ("-p", "/panels/panel-0/plugin-ids"):
            return "1\n20\n19\n"
        return ""

    def fake_restart():
        order.append("restart")
        assert mod.genmon_rc(20).exists()  # not yet deleted
        return True

    monkeypatch.setattr(mod, "xfconf", fake_xfconf)
    monkeypatch.setattr(mod, "require_panel", lambda: None)
    monkeypatch.setattr(mod, "restart_panel", fake_restart)
    mod.uninstall_panel()
    assert not mod.genmon_rc(20).exists()
    assert ("-p", "/panels/panel-0/plugin-ids", "-a", "-t", "int", "-s", "1", "-t", "int", "-s", "19") in order
    assert ("-p", "/plugins/plugin-20", "-r", "-R") in order
    assert order.index("restart") > order.index(("-p", "/plugins/plugin-20", "-r", "-R"))


def test_refresh_panel_item_sends_the_plugin_event(mod, monkeypatch):
    calls = []
    monkeypatch.setattr(mod.shutil, "which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(mod, "plugin_types", lambda: {7: "genmon"})
    monkeypatch.setattr(mod, "find_installed", lambda types_: 7)
    monkeypatch.setattr(mod.subprocess, "run", fake_run(calls))
    assert mod.refresh_panel_item() is True
    assert calls[-1] == ["xfce4-panel", "--plugin-event=genmon-7:refresh:bool:true"]


def test_refresh_panel_item_without_an_item(mod, monkeypatch):
    calls = []
    monkeypatch.setattr(mod.shutil, "which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(mod, "plugin_types", lambda: {})
    monkeypatch.setattr(mod, "find_installed", lambda types_: None)
    monkeypatch.setattr(mod.subprocess, "run", fake_run(calls))
    assert mod.refresh_panel_item() is False
    assert not calls


def test_refresh_panel_item_reports_a_failed_command(mod, monkeypatch):
    monkeypatch.setattr(mod.shutil, "which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(mod, "plugin_types", lambda: {7: "genmon"})
    monkeypatch.setattr(mod, "find_installed", lambda types_: 7)
    monkeypatch.setattr(mod.subprocess, "run", fake_run([], returncode=1))
    assert mod.refresh_panel_item() is False


def test_refresh_panel_item_looks_the_id_up_one_time(mod, monkeypatch):
    """The lookup reads every genmon rc file. Once is enough."""
    lookups = []
    calls = []
    monkeypatch.setattr(mod.shutil, "which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(mod, "plugin_types", lambda: {7: "genmon"})
    monkeypatch.setattr(mod, "find_installed", lambda types_: lookups.append(1) or 7)
    monkeypatch.setattr(mod.subprocess, "run", fake_run(calls))
    assert mod.refresh_panel_item() is True
    assert mod.refresh_panel_item() is True
    assert len(lookups) == 1 and len(calls) == 2


def test_a_failed_event_makes_the_next_call_look_again(mod, monkeypatch):
    lookups = []
    monkeypatch.setattr(mod.shutil, "which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(mod, "plugin_types", lambda: {7: "genmon"})
    monkeypatch.setattr(mod, "find_installed", lambda types_: lookups.append(1) or 7)
    monkeypatch.setattr(mod.subprocess, "run", fake_run([], returncode=1))
    assert mod.refresh_panel_item() is False
    assert mod.refresh_panel_item() is False
    assert len(lookups) == 2


def test_notify_summary_writes_the_count(mod, monkeypatch):
    monkeypatch.setattr(mod, "refresh_panel_item", lambda: True)
    lists = [model.TaskList("1", "Work", [model.Task(id="a", list_id="1")])]
    assert mod.notify_summary(lists) is True
    saved = state.load_state()
    assert saved["count"] == 1 and saved["lists"] == [["Work", 1]]


def test_notify_summary_skips_a_running_fetch(mod, monkeypatch):
    calls = []
    monkeypatch.setattr(mod, "refresh_panel_item", lambda: calls.append(True) or True)
    lock_fd = state.try_lock()
    try:
        assert mod.notify_summary([]) is False
    finally:
        os.close(lock_fd)
    assert not calls
