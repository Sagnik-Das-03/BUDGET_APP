"""LAN password for the read-only server, set from the native Android app
(MainActivity.kt's password screen calls set_password()/is_password_set()
directly through Chaquopy - never over HTTP, since the HTTP server is what
the password protects). Same PBKDF2-HMAC-SHA256, salted scheme as the
desktop app's own per-user passwords (backend/app/user_registry.py), stored
as "<salt hex>:<digest hex>" - but unlike that registry, "no password set"
here fails CLOSED (server.py's middleware refuses every request) rather than
open, since this server is reachable by anything on the LAN, not just
localhost.

The username in the browser's Basic Auth prompt is never checked - this is
a single-owner app, so only the password (kept on the phone, in the app)
matters."""
import hashlib
import hmac
import json
import secrets
from pathlib import Path
from typing import Optional

# parent.parent, not parent: this module lives inside the android_dashboard
# package, but auth_config.json belongs next to server.py (one level up,
# same directory as dashboard_credentials.json/users_config.json) - both in
# the canonical copy here and in the Android-bundled copy under
# android/app/src/main/python/, where server.py is a TOP-LEVEL module
# (Chaquopy calls Python.getModule("server")) sitting beside this package,
# not inside it. Keeping that one level consistent between the two copies is
# exactly what makes this module's default path correct in both.
_HERE = Path(__file__).resolve().parent.parent
AUTH_CONFIG_PATH = _HERE / "auth_config.json"
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


def verify_password(password: str) -> bool:
    stored = _read_hash()
    return stored is not None and _verify(password, stored)
