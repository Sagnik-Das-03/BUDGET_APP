import hashlib
import hmac
import json
import re
import secrets
from pathlib import Path
from typing import Optional

from app.config import BASE_DIR

REGISTRY_PATH = BASE_DIR / "data" / "users_registry.json"
_USERNAME_RE = re.compile(r"^[A-Za-z0-9_-]{1,32}$")
_PBKDF2_ITERATIONS = 200_000
ADMIN_USERNAME = "admin"


def _hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, _PBKDF2_ITERATIONS)
    return f"{salt.hex()}:{digest.hex()}"


def _verify_password(password: str, stored: str) -> bool:
    salt_hex, _, digest_hex = stored.partition(":")
    if not salt_hex or not digest_hex:
        return False
    salt = bytes.fromhex(salt_hex)
    expected = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, _PBKDF2_ITERATIONS)
    return hmac.compare_digest(expected.hex(), digest_hex)


class UserRegistry:
    """Maps a username to its own SQLite file (user-level isolation - each
    user is a completely separate database, not rows scoped by a user_id).
    Backed by a small JSON file rather than a database table, since it has to
    be readable before any database engine exists yet (it's what decides
    which file that engine points at).

    Each entry may carry a `password_hash` (PBKDF2-HMAC-SHA256, salted - never
    the plaintext password, never a fixed/global salt). A user created without
    a password has no `password_hash` key at all and `verify_password` treats
    that as "no password required yet" - this is a personal, single-machine
    app being retrofitted with per-profile passwords, not a fresh multi-tenant
    system, so already-existing profiles must keep working exactly as before
    until their owner deliberately sets a password via Settings."""

    def __init__(self, path: Path = REGISTRY_PATH):
        self.path = path

    def _load(self) -> dict:
        if not self.path.exists():
            return {"active": None, "users": []}
        return json.loads(self.path.read_text())

    def _save(self, data: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(data, indent=2))

    def list_users(self) -> list[dict]:
        return self._load()["users"]

    def get_active(self) -> Optional[str]:
        return self._load().get("active")

    def get_db_file(self, username: str) -> Optional[str]:
        for u in self.list_users():
            if u["username"] == username:
                return u["db_file"]
        return None

    def get_user(self, username: str) -> Optional[dict]:
        return next((u for u in self.list_users() if u["username"] == username), None)

    def exists(self, username: str) -> bool:
        return any(u["username"] == username for u in self.list_users())

    def has_password(self, username: str) -> bool:
        u = self.get_user(username)
        return bool(u and u.get("password_hash"))

    def verify_password(self, username: str, password: str) -> bool:
        """True if the password matches, OR if this user has no password set
        yet at all - see the class docstring for why "no password" verifies
        as open rather than as a hard failure."""
        u = self.get_user(username)
        if not u:
            return False
        if not u.get("password_hash"):
            return True
        return _verify_password(password, u["password_hash"])

    def set_password(self, username: str, password: str) -> None:
        data = self._load()
        for u in data["users"]:
            if u["username"] == username:
                u["password_hash"] = _hash_password(password)
                self._save(data)
                return
        raise ValueError(f"User {username!r} not found")

    @staticmethod
    def validate_username(username: str) -> None:
        if not _USERNAME_RE.match(username):
            raise ValueError("Username must be 1-32 letters, digits, underscores or hyphens")

    def add_user(self, username: str, db_file: str, password: Optional[str] = None) -> None:
        self.validate_username(username)
        data = self._load()
        if any(u["username"] == username for u in data["users"]):
            raise ValueError(f"User {username!r} already exists")
        entry = {"username": username, "db_file": db_file}
        if password:
            entry["password_hash"] = _hash_password(password)
        data["users"].append(entry)
        if not data.get("active"):
            data["active"] = username
        self._save(data)

    def set_active(self, username: str) -> None:
        data = self._load()
        if not any(u["username"] == username for u in data["users"]):
            raise ValueError(f"User {username!r} not found")
        data["active"] = username
        self._save(data)

    def remove_user(self, username: str) -> None:
        data = self._load()
        if not any(u["username"] == username for u in data["users"]):
            raise ValueError(f"User {username!r} not found")
        data["users"] = [u for u in data["users"] if u["username"] != username]
        if data.get("active") == username:
            data["active"] = data["users"][0]["username"] if data["users"] else None
        self._save(data)

    def ensure_bootstrapped(self, default_username: str, default_db_filename: str) -> None:
        """First-run migration: if the registry doesn't exist yet, register
        the classic single-user database file under `default_username`
        WITHOUT moving, renaming, or otherwise touching that file - the
        pre-existing database becomes user #1 as-is."""
        if self.path.exists():
            return
        self._save({"active": default_username, "users": [{"username": default_username, "db_file": default_db_filename}]})


registry = UserRegistry()
