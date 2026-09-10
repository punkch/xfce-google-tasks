"""Google sign-in: the token file, the scope check and the refresh."""

import sys

from . import paths
from .state import atomic_write

SCOPES = ["https://www.googleapis.com/auth/tasks"]


def save_token(creds) -> None:
    atomic_write(paths.TOKEN_PATH, creds.to_json(), mode=0o600)


def load_credentials():
    """Return (creds, verdict). Refreshes an expired token (network)."""
    if not paths.SECRET_PATH.is_file():
        return None, paths.AUTH_NO_SECRET

    from google.oauth2.credentials import Credentials
    from google_auth_httplib2 import Request
    import httplib2

    try:
        # No scopes argument: it would hide the scopes saved in the file.
        # One open instead of a check first: a token deleted between the
        # two would give the wrong verdict.
        creds = Credentials.from_authorized_user_file(str(paths.TOKEN_PATH))
    except FileNotFoundError:
        return None, paths.AUTH_NO_TOKEN
    except (OSError, ValueError) as exc:
        # The file exists but is unusable. Only a new sign-in replaces it.
        print(f"{paths.TOKEN_PATH}: {exc}", file=sys.stderr)
        return None, paths.AUTH_REAUTH
    # Before the refresh: a 0.1.0 read-only token must not reach the API.
    if not creds.has_scopes(SCOPES):
        return None, paths.AUTH_REAUTH
    if creds.valid:
        return creds, paths.AUTH_OK
    if not (creds.expired and creds.refresh_token):
        return None, paths.AUTH_REAUTH
    creds.refresh(Request(httplib2.Http(timeout=paths.HTTP_TIMEOUT)))  # may raise RefreshError
    save_token(creds)
    return creds, paths.AUTH_OK


def needs_reauth(exc: BaseException) -> bool:
    """True for a RefreshError that a retry cannot fix.

    That is a revoked token, one that expired after 7 days in "Testing"
    status, or one without the new scope. AuthorizedHttp also refreshes
    during an API call, so the error can come out of a fetch as well.
    """
    try:
        from google.auth.exceptions import RefreshError
    except ImportError:
        return False
    return isinstance(exc, RefreshError) and not getattr(exc, "retryable", False)


def run_auth_flow():
    """Interactive sign-in. Opens a browser. Saves the token."""
    from google_auth_oauthlib.flow import InstalledAppFlow

    if not paths.SECRET_PATH.is_file():
        sys.exit(
            f"Missing {paths.USER_SECRET_PATH}\n"
            "Create an OAuth client (Desktop app) in Google Cloud Console,\n"
            "download the JSON and save it at that path. See README."
        )
    flow = InstalledAppFlow.from_client_secrets_file(str(paths.SECRET_PATH), SCOPES)
    creds = flow.run_local_server(port=0)
    save_token(creds)
    return creds
