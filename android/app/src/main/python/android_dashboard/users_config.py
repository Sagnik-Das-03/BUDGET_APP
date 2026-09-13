"""The list of Sheets this server can show - the Android equivalent of the
desktop app's user management (see backend/app/user_registry.py), adapted
to what a read-only viewer actually needs: not a registry of separate
per-user SQLite databases with logins, just a name and a spreadsheet ID,
since sharing a spreadsheet as Viewer is per-file, not per-credential (one
read-only service account - see sheets_reader.py - can be Viewer on any
number of people's spreadsheets independently).

"Admin" for this app is whoever holds the phone and gets past its biometric
lock (see MainActivity.kt's "Manage Viewers" screen) - there's no separate
admin login the way the desktop app has one, since only the phone's owner
can ever reach this code path (it has no HTTP endpoint; adding/removing a
viewer is a direct Chaquopy call from Kotlin, never reachable over the LAN).

Each viewer named here gets its own isolated slice of local_db.py's SQLite
cache (every table is keyed by user_name) - that's this app's version of
the desktop's "each user is a separate database": same storage, rows
namespaced by name instead of separate files, since there's no per-user
data to ever write here in the first place."""
import json
from pathlib import Path

# parent.parent, not parent - see auth.py's AUTH_CONFIG_PATH comment for why
# (this module lives inside the android_dashboard package, but
# users_config.json belongs next to server.py, one level up).
_HERE = Path(__file__).resolve().parent.parent
USERS_CONFIG_PATH = _HERE / "users_config.json"


def load_users() -> list[dict]:
    if not USERS_CONFIG_PATH.exists():
        return []
    return json.loads(USERS_CONFIG_PATH.read_text()).get("users", [])


def _save(users: list[dict]) -> None:
    USERS_CONFIG_PATH.write_text(json.dumps({"users": users}, indent=2))


def add_user(name: str, spreadsheet_id: str) -> None:
    name = name.strip()
    spreadsheet_id = spreadsheet_id.strip()
    if not name or not spreadsheet_id:
        raise ValueError("Name and spreadsheet ID are both required")
    users = load_users()
    if any(u["name"] == name for u in users):
        raise ValueError(f"{name!r} is already in the list")
    users.append({"name": name, "spreadsheet_id": spreadsheet_id})
    _save(users)


def remove_user(name: str) -> None:
    users = load_users()
    remaining = [u for u in users if u["name"] != name]
    if len(remaining) == len(users):
        raise ValueError(f"{name!r} not found")
    _save(remaining)


def load_users_json() -> str:
    """Same data as load_users(), pre-serialized - Kotlin parses this with
    org.json rather than walking a Chaquopy PyObject list of dicts."""
    return json.dumps(load_users())
