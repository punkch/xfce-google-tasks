"""Token files and the scope check (0.2.0 needs the read-write scope)."""

import datetime as dt
import json

import pytest

from gtasks_panel import auth

FULL = "https://www.googleapis.com/auth/tasks"
READONLY = "https://www.googleapis.com/auth/tasks.readonly"


def write_token(mod, scopes, expiry=None):
    data = {"token": "x", "refresh_token": "r", "client_id": "c",
            "client_secret": "s", "scopes": scopes}
    if expiry:
        data["expiry"] = expiry
    mod.paths.TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)
    mod.paths.TOKEN_PATH.write_text(json.dumps(data))


def tomorrow():
    now = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)
    return (now + dt.timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ")


def test_scope_is_read_write():
    assert auth.SCOPES == [FULL]


def test_a_missing_secret_has_its_own_verdict(mod):
    assert auth.load_credentials() == (None, mod.paths.AUTH_NO_SECRET)


def test_a_missing_token_has_its_own_verdict(mod, secret):
    """No file check first: the open itself says the token is not there."""
    pytest.importorskip("google.oauth2.credentials")
    assert auth.load_credentials() == (None, mod.paths.AUTH_NO_TOKEN)


def test_readonly_token_needs_reauth(mod, secret):
    """A 0.1.0 token has no write scope.

    The file has no expiry, so google-auth marks it expired. The check must
    come before the refresh, or this test would go to the network.
    """
    pytest.importorskip("google.oauth2.credentials")
    write_token(mod, [READONLY])
    assert auth.load_credentials() == (None, mod.paths.AUTH_REAUTH)


def test_full_scope_token_is_used(mod, secret):
    pytest.importorskip("google.oauth2.credentials")
    write_token(mod, [FULL], expiry=tomorrow())
    creds, verdict = auth.load_credentials()
    assert verdict == mod.paths.AUTH_OK
    assert creds.has_scopes([FULL])


def test_save_token_writes_a_private_file(mod):
    class FakeCreds:
        def to_json(self):
            return '{"token": "x"}'

    auth.save_token(FakeCreds())
    assert mod.paths.TOKEN_PATH.read_text() == '{"token": "x"}'
    assert oct(mod.paths.TOKEN_PATH.stat().st_mode & 0o777) == "0o600"
