"""HTTP Basic Auth for the whole app - the standard 'basic way' to protect a
single-user localhost tool: the browser's native username/password prompt,
checked against AUTH_USERNAME/AUTH_PASSWORD in .env. Off by default (neither
set) so an existing setup isn't locked out by upgrading."""
import secrets

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials

from app.config import settings

security = HTTPBasic(auto_error=False)


def require_auth(credentials: HTTPBasicCredentials = Depends(security)) -> None:
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
