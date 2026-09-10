"""Import gtasks_panel with its files under tmp_path.

`gtasks_panel.paths` reads the XDG environment at import time, and every
other module reads it as `paths.NAME`. So one reload after the env is set
moves the whole package to a scratch directory.

The fake Google service lives here too: three test files use it.
"""

import importlib
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

ENTRY = ROOT / "bin" / "gtasks-panel"
WINDOW_ENTRY = ROOT / "bin" / "gtasks-window"


@pytest.fixture
def mod(tmp_path, monkeypatch):
    """The panel module, with the package pointed at tmp_path."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    from gtasks_panel import panel

    importlib.reload(panel.paths)
    # A packaged /usr/share secret on the dev host must not leak into tests.
    panel.paths.SECRET_PATH = panel.paths.USER_SECRET_PATH
    panel.configure(entry=ENTRY)
    # The plugin id is remembered between calls. Start every test blank.
    monkeypatch.setattr(panel, "_PLUGIN_ID", None)
    # Never start a real background fetch from a test.
    monkeypatch.setattr(panel, "spawned", [], raising=False)
    monkeypatch.setattr(panel, "spawn_fetch", lambda: panel.spawned.append(True))
    return panel


@pytest.fixture
def secret(mod):
    """An OAuth client file. Its content is not a real client."""
    mod.paths.USER_SECRET_PATH.parent.mkdir(parents=True, exist_ok=True)
    mod.paths.USER_SECRET_PATH.write_text("{}")
    return mod.paths.USER_SECRET_PATH


@pytest.fixture
def token(mod):
    """A token file. Its content is not a real token."""
    mod.paths.TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)
    mod.paths.TOKEN_PATH.write_text("{}")
    return mod.paths.TOKEN_PATH


@pytest.fixture
def files(mod, secret, token):
    """Secret and token in place, so render() reaches the state file."""
    return mod


def default_cfg(**overrides) -> dict:
    """The settings a test starts from: the defaults, refresh as a number."""
    from gtasks_panel import paths

    return dict(paths.DEFAULTS, refresh=300, **overrides)


def xml(mod, capsys, cfg=None):
    mod.render(cfg or default_cfg())
    return capsys.readouterr().out


def tag(out, name):
    start = out.index(f"<{name}>") + len(name) + 2
    return out[start:out.index(f"</{name}>", start)]


def pump() -> None:
    """Run the waiting GLib callbacks now.

    The store collects its change notices into one idle callback, so a
    test must let the main context run before it looks at the widgets.
    """
    from gi.repository import GLib

    context = GLib.MainContext.default()
    while context.pending():
        context.iteration(False)


# --------------------------------------------------------------------------
# A fake googleapiclient service that records every call
# --------------------------------------------------------------------------

class FakePages:
    """One list request. `pages` is what the pages after it hold."""

    def __init__(self, pages):
        self.pages = pages

    def execute(self):
        return self.pages[0]


FakeRequest = FakePages  # the name the fetch tests use


class FakeResult:
    def __init__(self, item):
        self.item = item

    def execute(self):
        return self.item


class FakeCollection:
    """Records (name, kwargs) for every call. `list` walks its pages.

    `id_key` names the keyword that holds the id of the thing a write
    changes: `task` for `tasks()`, `tasklist` for `tasklists()`. Google
    gives that id back in the answer, so the fake does the same.
    """

    def __init__(self, pages=None, id_key="task"):
        self.pages = pages or {}
        self.id_key = id_key
        self.calls = []

    def list(self, **kwargs):
        self.calls.append(("list", kwargs))
        key = kwargs.get("tasklist", "lists")
        return FakePages(list(self.pages.get(key, [{"items": []}])))

    def list_next(self, request, response):
        return FakePages(request.pages[1:]) if len(request.pages) > 1 else None

    def insert(self, **kwargs):
        return self._write("insert", kwargs)

    def patch(self, **kwargs):
        return self._write("patch", kwargs)

    def move(self, **kwargs):
        return self._write("move", kwargs)

    def delete(self, **kwargs):
        return self._write("delete", kwargs)

    def _write(self, name, kwargs):
        self.calls.append((name, kwargs))
        body = {key: value for key, value in (kwargs.get("body") or {}).items()
                if value is not None}
        return FakeResult({"id": kwargs.get(self.id_key) or "new-id", **body})


class FakeService:
    def __init__(self, lists=None, tasks=None):
        self._lists = FakeCollection({"lists": lists or [{"items": []}]},
                                     id_key="tasklist")
        self._tasks = FakeCollection(tasks or {})

    def tasklists(self):
        return self._lists

    def tasks(self):
        return self._tasks
