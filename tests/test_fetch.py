"""fetch_summary and run_fetch with a fake googleapiclient service."""

import datetime as dt
import sys

import pytest


class FakeRequest:
    def __init__(self, pages):
        self.pages = pages

    def execute(self):
        return self.pages[0]


class FakeCollection:
    def __init__(self, pages_by_key):
        self.pages_by_key = pages_by_key
        self.calls = []

    def list(self, **kwargs):
        self.calls.append(kwargs)
        key = kwargs.get("tasklist", "lists")
        return FakeRequest(list(self.pages_by_key[key]))

    def list_next(self, request, response):
        if len(request.pages) > 1:
            return FakeRequest(request.pages[1:])
        return None


class FakeService:
    def __init__(self, lists, tasks):
        self._lists = FakeCollection({"lists": lists})
        self._tasks = FakeCollection(tasks)

    def tasklists(self):
        return self._lists

    def tasks(self):
        return self._tasks


@pytest.fixture
def fetch(mod):
    return mod.fetch_summary


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
    assert service._lists.calls[0]["fields"] == "items(id,title),nextPageToken"
    assert service._tasks.calls[0]["showCompleted"] is False


def test_deadline(fetch, monkeypatch, mod):
    service = FakeService(lists=[{"items": [{"id": "a", "title": "A"}]}],
                          tasks={"a": [{"items": []}]})
    clock = iter([0, 100])
    monkeypatch.setattr(mod.time, "monotonic", lambda: next(clock))
    with pytest.raises(TimeoutError):
        fetch(None, service=service, deadline=60)


def test_run_fetch_records_error_and_keeps_count(mod, monkeypatch):
    mod.save_state({**mod.EMPTY_STATE, "count": 5, "fetched_at": 1.0})
    monkeypatch.setattr(mod, "load_credentials", lambda: (object(), mod.AUTH_OK))

    def fail(creds):
        raise OSError("Network unreachable")
    monkeypatch.setattr(mod, "fetch_summary", fail)
    assert mod.run_fetch() == 1
    state = mod.load_state()
    assert state["count"] == 5
    assert state["error"] == "Network unreachable"
    assert state["error_at"] > state["fetched_at"]


def test_run_fetch_success_clears_error(mod, monkeypatch):
    mod.save_state({**mod.EMPTY_STATE, "error": "old", "error_at": 2.0})
    monkeypatch.setattr(mod, "load_credentials", lambda: (object(), mod.AUTH_OK))
    monkeypatch.setattr(mod, "fetch_summary",
                        lambda creds: {"count": 2, "overdue": 0, "lists": [["L", 2]]})
    assert mod.run_fetch() == 0
    state = mod.load_state()
    assert state["count"] == 2 and state["error"] is None
    assert state["fetched_at"] > state["error_at"]
    assert state["auth"] == mod.AUTH_OK


def test_run_fetch_reauth_marks_state(mod, monkeypatch):
    monkeypatch.setattr(mod, "load_credentials", lambda: (None, mod.AUTH_REAUTH))
    assert mod.run_fetch() == 1
    assert mod.load_state()["auth"] == mod.AUTH_REAUTH


class FakeRefreshError(Exception):
    def __init__(self, msg, retryable=False):
        super().__init__(msg)
        self.retryable = retryable


def test_run_fetch_refresh_error_during_api_call(mod, monkeypatch):
    mod.save_state({**mod.EMPTY_STATE, "count": 5, "fetched_at": 1.0})
    monkeypatch.setattr(mod, "load_credentials", lambda: (object(), mod.AUTH_OK))
    monkeypatch.setattr(mod, "needs_reauth", lambda exc: isinstance(exc, FakeRefreshError)
                        and not exc.retryable)

    def revoked(creds):
        raise FakeRefreshError("invalid_grant: Token has been revoked")
    monkeypatch.setattr(mod, "fetch_summary", revoked)
    assert mod.run_fetch() == 1
    state = mod.load_state()
    assert state["auth"] == mod.AUTH_REAUTH
    assert state["count"] == 5 and state["error"] is None

    def hiccup(creds):
        raise FakeRefreshError("server_error", retryable=True)
    mod.save_state({**mod.EMPTY_STATE, "count": 5, "fetched_at": 1.0})
    monkeypatch.setattr(mod, "fetch_summary", hiccup)
    mod.run_fetch()
    state = mod.load_state()
    assert state["auth"] == mod.AUTH_OK and state["error"] == "server_error"


def test_corrupt_token_file_needs_reauth(mod, monkeypatch):
    """A token file that exists but does not parse must end as 'sign in'."""
    import types

    class FakeCredentials:
        @staticmethod
        def from_authorized_user_file(path, scopes):
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
    mod.USER_SECRET_PATH.parent.mkdir(parents=True)
    mod.USER_SECRET_PATH.write_text("{}")
    mod.TOKEN_PATH.parent.mkdir(parents=True)
    mod.TOKEN_PATH.write_text("garbage")
    assert mod.load_credentials() == (None, mod.AUTH_REAUTH)
    assert mod.run_fetch() == 1
    assert mod.load_state()["auth"] == mod.AUTH_REAUTH


def test_needs_reauth_with_real_class(mod):
    pytest.importorskip("google.auth.exceptions")
    from google.auth.exceptions import RefreshError
    assert mod.needs_reauth(RefreshError("x"))
    assert not mod.needs_reauth(RefreshError("x", retryable=True))
    assert not mod.needs_reauth(OSError("x"))


def test_run_fetch_exits_when_locked(mod, monkeypatch):
    monkeypatch.setattr(mod, "try_lock", lambda: None)
    assert mod.run_fetch() == 1
    assert not mod.STATE_PATH.exists()


def test_error_text(mod):
    assert mod.error_text(ValueError("a", {"b": 1})) == "a"
    assert mod.error_text(ValueError()) == "ValueError"
    assert mod.error_text(OSError(2, "No such file")) == "[Errno 2] No such file"
