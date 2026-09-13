"""HTTP Basic Auth for the whole app - the standard 'basic way' to protect a
single-user localhost tool: the browser's native username/password prompt,
checked against AUTH_USERNAME/AUTH_PASSWORD in .env. Off by default (neither
set) so an existing setup isn't locked out by upgrading.

The Android host (android/app/src/main/python/server.py) needs a DIFFERENT
policy on top of the same mechanism: a password set/changed at any time from
the native app's UI (not baked into .env at build time), stored as a salted
hash rather than plaintext, and fails CLOSED (rejects everything) rather
than defaulting off - it's reachable by anything on the LAN, not just
localhost. set_password_provider() below lets it plug that in without a
separate auth code path: when a provider is registered, require_auth asks
it to verify the SUBMITTED password on every request (never asks it for
"the current password" - a one-way hash can't produce that, only check
against it) instead of consulting the static settings.auth_username/
auth_password, which is never touched and keeps working exactly as before
when no provider is registered."""
import secrets
from typing import Callable, Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials

from app.config import settings

security = HTTPBasic(auto_error=False)

# fn(submitted_password) -> None if no password has been set yet (fails
# closed with 503), else True/False for whether it matched.
_password_provider: Optional[Callable[[str], Optional[bool]]] = None


def set_password_provider(fn: Optional[Callable[[str], Optional[bool]]]) -> None:
    global _password_provider
    _password_provider = fn


def require_auth(credentials: HTTPBasicCredentials = Depends(security)) -> None:
    if _password_provider is not None:
        submitted = credentials.password if credentials is not None else ""
        result = _password_provider(submitted)
        if result is None:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="No password set yet")
        if not result:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized",
                headers={"WWW-Authenticate": "Basic"},
            )
        return

    if not settings.auth_enabled:
        return
    valid = credentials is not None and (
        secrets.compare_digest(credentials.username, settings.auth_username)
        and secrets.compare_digest(credentials.password, settings.auth_password)
    )
    if not valid:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized",
            headers={"WWW-Authenticate": "Basic"},
        )
