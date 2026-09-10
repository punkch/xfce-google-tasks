"""Load bin/gtasks-panel (no .py suffix) as a module with scratch dirs."""

import importlib.util
import os
import sys
from importlib.machinery import SourceFileLoader
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "bin" / "gtasks-panel"


@pytest.fixture
def mod(tmp_path, monkeypatch):
    """Fresh import of the script with XDG dirs under tmp_path.

    The module computes its paths at import time, so the env must be set
    before the import. SECRET_PATH is pinned to the user path so a
    packaged /usr/share secret on the dev host cannot leak into tests.
    """
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    loader = SourceFileLoader("gtasks_panel", str(SCRIPT))
    spec = importlib.util.spec_from_loader("gtasks_panel", loader)
    module = importlib.util.module_from_spec(spec)
    sys.modules["gtasks_panel"] = module
    loader.exec_module(module)
    module.SECRET_PATH = module.USER_SECRET_PATH
    # No terminal lookup in tests: deterministic click command.
    monkeypatch.setattr(module, "terminal_command", lambda inner: " ".join(inner))
    # Never start a real background fetch from a test.
    module.spawned = []
    monkeypatch.setattr(module, "spawn_fetch", lambda: module.spawned.append(True))
    yield module
    sys.modules.pop("gtasks_panel", None)


@pytest.fixture
def files(mod):
    """Create secret and token files so render() reaches the state file."""
    mod.USER_SECRET_PATH.parent.mkdir(parents=True)
    mod.USER_SECRET_PATH.write_text("{}")
    mod.TOKEN_PATH.parent.mkdir(parents=True)
    mod.TOKEN_PATH.write_text("{}")
    return mod


def xml(mod, capsys, cfg=None):
    mod.render(cfg or dict(mod.DEFAULTS, refresh=300))
    return capsys.readouterr().out


def tag(out, name):
    start = out.index(f"<{name}>") + len(name) + 2
    return out[start:out.index(f"</{name}>", start)]
