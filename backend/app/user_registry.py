import json
import re
from pathlib import Path
from typing import Optional

from app.config import BASE_DIR

REGISTRY_PATH = BASE_DIR / "data" / "users_registry.json"
_USERNAME_RE = re.compile(r"^[A-Za-z0-9_-]{1,32}$")


class UserRegistry:
    """Maps a username to its own SQLite file (user-level isolation - each
    user is a completely separate database, not rows scoped by a user_id).
    Backed by a small JSON file rather than a database table, since it has to
    be readable before any database engine exists yet (it's what decides
    which file that engine points at)."""

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

    def exists(self, username: str) -> bool:
        return any(u["username"] == username for u in self.list_users())

    @staticmethod
    def validate_username(username: str) -> None:
        if not _USERNAME_RE.match(username):
            raise ValueError("Username must be 1-32 letters, digits, underscores or hyphens")

    def add_user(self, username: str, db_file: str) -> None:
        self.validate_username(username)
        data = self._load()
        if any(u["username"] == username for u in data["users"]):
            raise ValueError(f"User {username!r} already exists")
        data["users"].append({"username": username, "db_file": db_file})
        if not data.get("active"):
            data["active"] = username
        self._save(data)

    def set_active(self, username: str) -> None:
        data = self._load()
        if not any(u["username"] == username for u in data["users"]):
            raise ValueError(f"User {username!r} not found")
        data["active"] = username
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
