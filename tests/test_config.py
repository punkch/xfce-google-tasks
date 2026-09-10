"""config.ini and the state file, read from the modules that own them."""

from conftest import default_cfg

from gtasks_panel import config, state


def write_config(mod, text):
    mod.paths.CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    mod.paths.CONFIG_PATH.write_text(text)


def test_missing_file_gives_defaults(mod):
    cfg = config.load_config()
    assert cfg["label"] == "{count}"
    assert cfg["refresh"] == 300


def test_percent_in_value_does_not_crash(mod):
    write_config(mod, "[panel]\nlabel = {count}%\nopen_command = echo 100%\n")
    cfg = config.load_config()
    assert cfg["label"] == "{count}%"
    assert cfg["open_command"] == "echo 100%"


def test_bad_label_falls_back(mod):
    write_config(mod, "[panel]\nlabel = {nope}\n")
    assert config.load_config()["label"] == "{count}"
    write_config(mod, "[panel]\nlabel = {\n")
    assert config.load_config()["label"] == "{count}"


def test_refresh_bounds(mod):
    write_config(mod, "[panel]\nrefresh = 5\n")
    assert config.load_config()["refresh"] == 30
    write_config(mod, "[panel]\nrefresh = abc\n")
    assert config.load_config()["refresh"] == 300


def test_broken_ini_gives_defaults(mod):
    write_config(mod, "no section header\n")
    assert config.load_config() == default_cfg()


def test_state_roundtrip_and_corrupt_file(mod):
    assert state.load_state() == mod.paths.EMPTY_STATE
    state.save_state({**mod.paths.EMPTY_STATE, "count": 4})
    assert state.load_state()["count"] == 4
    mod.paths.STATE_PATH.write_text("not json")
    assert state.load_state() == mod.paths.EMPTY_STATE
    mod.paths.STATE_PATH.write_text("[1, 2]")
    assert state.load_state() == mod.paths.EMPTY_STATE
