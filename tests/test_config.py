def write_config(mod, text):
    mod.CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    mod.CONFIG_PATH.write_text(text)


def test_missing_file_gives_defaults(mod):
    cfg = mod.load_config()
    assert cfg["label"] == "{count}"
    assert cfg["refresh"] == 300


def test_percent_in_value_does_not_crash(mod):
    write_config(mod, "[panel]\nlabel = {count}%\nopen_command = echo 100%\n")
    cfg = mod.load_config()
    assert cfg["label"] == "{count}%"
    assert cfg["open_command"] == "echo 100%"


def test_bad_label_falls_back(mod):
    write_config(mod, "[panel]\nlabel = {nope}\n")
    assert mod.load_config()["label"] == "{count}"
    write_config(mod, "[panel]\nlabel = {\n")
    assert mod.load_config()["label"] == "{count}"


def test_refresh_bounds(mod):
    write_config(mod, "[panel]\nrefresh = 5\n")
    assert mod.load_config()["refresh"] == 30
    write_config(mod, "[panel]\nrefresh = abc\n")
    assert mod.load_config()["refresh"] == 300


def test_broken_ini_gives_defaults(mod):
    write_config(mod, "no section header\n")
    assert mod.load_config() == dict(mod.DEFAULTS, refresh=300)


def test_state_roundtrip_and_corrupt_file(mod):
    assert mod.load_state() == mod.EMPTY_STATE
    mod.save_state({**mod.EMPTY_STATE, "count": 4})
    assert mod.load_state()["count"] == 4
    mod.STATE_PATH.write_text("not json")
    assert mod.load_state() == mod.EMPTY_STATE
    mod.STATE_PATH.write_text("[1, 2]")
    assert mod.load_state() == mod.EMPTY_STATE
