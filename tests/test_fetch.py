"""fetch_summary and run_fetch with a fake googleapiclient service.

The panel calls `api.x`, `auth.x` and `state.x`, so a test patches the
module that owns the name, never a re-export.
"""

import datetime as dt
import sys

import pytest
from conftest import FakeService

from gtasks_panel import api, auth, state


@pytest.fixture
def fetch(mod):
    return api.fetch_summary


def test_counts_overdue_and_paginates(fetch):
    yesterday = (dt.date.today() - dt.timedelta(days=1)).isoformat()
    tomorrow = (dt.date.today() + dt.timedelta(days=1)).isoformat()
    service = FakeService(
        lists=[{"items": [{"id": "a", "title": "Work"}], "nextPageToken": "p2"},
               {"items": [{"id": "b", "title": "Home"}]}],
        tasks={"a": [{"items": [{"due": f"{yesterday}T00:00:00.000Z"}, {}], "nextPageToken": "x"},
                     {"items": [{"due": f"{tomorrow}T00:00:00.000Z"}]}],
               "b": [{"items": []}]},
    )
    data = fetch(None, service=service)
    assert data == {"count": 3, "overdue": 1, "lists": [["Work", 3], ["Home", 0]]}
    assert service._lists.calls[0][1]["fields"] == "items(id,title),nextPageToken"
    assert service._tasks.calls[0][1]["showCompleted"] is False


def test_deadline(fetch, monkeypatch):
    service = FakeService(lists=[{"items": [{"id": "a", "title": "A"}]}],
                          tasks={"a": [{"items": []}]})
    clock = iter([0, 100])
    monkeypatch.setattr(api.time, "monotonic", lambda: next(clock))
    with pytest.raises(TimeoutError):
        fetch(None, service=service, deadline=60)


def test_run_fetch_records_error_and_keeps_count(mod, monkeypatch):
    state.save_state({**mod.paths.EMPTY_STATE, "count": 5, "fetched_at": 1.0})
    monkeypatch.setattr(auth, "load_credentials", lambda: (object(), mod.paths.AUTH_OK))

    def fail(creds):
        raise OSError("Network unreachable")
    monkeypatch.setattr(api, "fetch_summary", fail)
    assert mod.run_fetch() == 1
    saved = state.load_state()
    assert saved["count"] == 5
    assert saved["error"] == "Network unreachable"
    assert saved["error_at"] > saved["fetched_at"]


def test_run_fetch_success_clears_error(mod, monkeypatch):
    state.save_state({**mod.paths.EMPTY_STATE, "error": "old", "error_at": 2.0})
    monkeypatch.setattr(auth, "load_credentials", lambda: (object(), mod.paths.AUTH_OK))
    monkeypatch.setattr(api, "fetch_summary",
                        lambda creds: {"count": 2, "overdue": 0, "lists": [["L", 2]]})
    assert mod.run_fetch() == 0
    saved = state.load_state()
    assert saved["count"] == 2 and saved["error"] is None
    assert saved["fetched_at"] > saved["error_at"]
    assert saved["auth"] == mod.paths.AUTH_OK


def test_run_fetch_reauth_marks_state(mod, monkeypatch):
    monkeypatch.setattr(auth, "load_credentials", lambda: (None, mod.paths.AUTH_REAUTH))
    assert mod.run_fetch() == 1
    assert state.load_state()["auth"] == mod.paths.AUTH_REAUTH


def test_run_fetch_names_the_debian_packages_for_a_missing_module(mod, monkeypatch):
    def missing():
        raise ImportError("No module named 'googleapiclient'")
    monkeypatch.setattr(auth, "load_credentials", missing)
    assert mod.run_fetch() == 1
    hint = state.load_state()["error"]
    for package in ("python3-googleapi", "python3-google-auth-oauthlib",
                    "python3-google-auth-httplib2", "python3-httplib2"):
        assert package in hint


class FakeRefreshError(Exception):
    def __init__(self, msg, retryable=False):
        super().__init__(msg)
        self.retryable = retryable


def test_run_fetch_refresh_error_during_api_call(mod, monkeypatch):
    state.save_state({**mod.paths.EMPTY_STATE, "count": 5, "fetched_at": 1.0})
    monkeypatch.setattr(auth, "load_credentials", lambda: (object(), mod.paths.AUTH_OK))
    monkeypatch.setattr(auth, "needs_reauth", lambda exc: isinstance(exc, FakeRefreshError)
                        and not exc.retryable)

    def revoked(creds):
        raise FakeRefreshError("invalid_grant: Token has been revoked")
    monkeypatch.setattr(api, "fetch_summary", revoked)
    assert mod.run_fetch() == 1
    saved = state.load_state()
    assert saved["auth"] == mod.paths.AUTH_REAUTH
    assert saved["count"] == 5 and saved["error"] is None

    def hiccup(creds):
        raise FakeRefreshError("server_error", retryable=True)
    state.save_state({**mod.paths.EMPTY_STATE, "count": 5, "fetched_at": 1.0})
    monkeypatch.setattr(api, "fetch_summary", hiccup)
    mod.run_fetch()
    saved = state.load_state()
    assert saved["auth"] == mod.paths.AUTH_OK and saved["error"] == "server_error"


def test_corrupt_token_file_needs_reauth(mod, secret, monkeypatch):
    """A token file that exists but does not parse must end as 'sign in'."""
    import types

    class FakeCredentials:
        @staticmethod
        def from_authorized_user_file(path, scopes=None):
            raise ValueError("Expecting value: line 1 column 1")

    fake = {
        "google": types.ModuleType("google"),
        "google.oauth2": types.ModuleType("google.oauth2"),
        "google.oauth2.credentials": types.ModuleType("google.oauth2.credentials"),
        "google_auth_httplib2": types.ModuleType("google_auth_httplib2"),
        "httplib2": types.ModuleType("httplib2"),
    }
    fake["google.oauth2.credentials"].Credentials = FakeCredentials
    fake["google_auth_httplib2"].Request = object
    for name, module in fake.items():
        monkeypatch.setitem(sys.modules, name, module)
    mod.paths.TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)
    mod.paths.TOKEN_PATH.write_text("garbage")
    assert auth.load_credentials() == (None, mod.paths.AUTH_REAUTH)
    assert mod.run_fetch() == 1
    assert state.load_state()["auth"] == mod.paths.AUTH_REAUTH


def test_needs_reauth_with_real_class(mod):
    pytest.importorskip("google.auth.exceptions")
    from google.auth.exceptions import RefreshError
    assert auth.needs_reauth(RefreshError("x"))
    assert not auth.needs_reauth(RefreshError("x", retryable=True))
    assert not auth.needs_reauth(OSError("x"))


def test_run_fetch_exits_when_locked(mod, monkeypatch):
    monkeypatch.setattr(state, "try_lock", lambda: None)
    assert mod.run_fetch() == 1
    assert not mod.paths.STATE_PATH.exists()


def test_error_text(mod):
    assert state.error_text(ValueError("a", {"b": 1})) == "a"
    assert state.error_text(ValueError()) == "ValueError"
    assert state.error_text(OSError(2, "No such file")) == "[Errno 2] No such file"
