"""The Android host's LAN password - set from MainActivity.kt's "LAN
Password" card, never over HTTP (the HTTP server is exactly what this
password protects). Same PBKDF2-HMAC-SHA256, salted scheme as the desktop
app's own per-user passwords (backend/app/user_registry.py), stored as
"<salt hex>:<digest hex>". Wired into the real backend's auth gate via
app.auth.set_password_provider() at server startup (see server.py) - the
provider contract is a verify function, not a password getter, since a
one-way hash can never hand back the plaintext to compare elsewhere.

The username in the browser's Basic Auth prompt is never checked - this is
a single-owner phone, so only the password matters."""
import env_setup  # noqa: F401 - side effect: sets env vars app.* reads, see its docstring

import hashlib
import hmac
import json
import secrets
from pathlib import Path
from typing import Optional

from app.config import BASE_DIR

AUTH_CONFIG_PATH = BASE_DIR / "auth_config.json"
_PBKDF2_ITERATIONS = 200_000


def _hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, _PBKDF2_ITERATIONS)
    return f"{salt.hex()}:{digest.hex()}"


def _verify(password: str, stored: str) -> bool:
    salt_hex, _, digest_hex = stored.partition(":")
    if not salt_hex or not digest_hex:
        return False
    salt = bytes.fromhex(salt_hex)
    expected = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, _PBKDF2_ITERATIONS)
    return hmac.compare_digest(expected.hex(), digest_hex)


def _read_hash() -> Optional[str]:
    if not AUTH_CONFIG_PATH.exists():
        return None
    try:
        return json.loads(AUTH_CONFIG_PATH.read_text()).get("password_hash")
    except (json.JSONDecodeError, OSError):
        return None


def is_password_set() -> bool:
    return bool(_read_hash())


def set_password(password: str) -> None:
    if not password:
        raise ValueError("Password cannot be empty")
    AUTH_CONFIG_PATH.write_text(json.dumps({"password_hash": _hash_password(password)}))


def check_password(submitted: str) -> Optional[bool]:
    """The provider function registered with app.auth.set_password_provider -
    None means no password set yet (caller should fail closed), else
    whether `submitted` matches."""
    stored = _read_hash()
    if stored is None:
        return None
    return _verify(submitted, stored)
