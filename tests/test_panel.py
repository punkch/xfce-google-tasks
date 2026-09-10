"""Panel wiring against a fake xfconf-query."""


def test_plugin_types_parses_listing(mod, monkeypatch):
    listing = "/plugins/plugin-1    launcher\n/plugins/plugin-2  genmon\n/plugins/plugin-19 systray\n"
    monkeypatch.setattr(mod, "xfconf", lambda *a, **k: listing)
    assert mod.plugin_types() == {1: "launcher", 2: "genmon", 19: "systray"}


def test_find_installed_reads_rc(mod, monkeypatch):
    mod.PANEL_RC_DIR.mkdir(parents=True)
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
    assert f"Command={mod.SELF}\n" in rc and "UpdatePeriod=60000\n" in rc
    assert ("-p", "/plugins/plugin-20", "-n", "-t", "string", "-s", "genmon") in calls
    assert calls[-1] == ("-p", "/panels/panel-0/plugin-ids", "-a",
                         "-t", "int", "-s", "1", "-t", "int", "-s", "20",
                         "-t", "int", "-s", "19", "-t", "int", "-s", "5")
    assert "plugin-20" in capsys.readouterr().out


def test_uninstall_removes_rc_after_restart(mod, monkeypatch, capsys):
    mod.PANEL_RC_DIR.mkdir(parents=True)
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
