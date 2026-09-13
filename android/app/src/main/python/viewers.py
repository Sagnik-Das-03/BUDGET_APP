"""Host-glue for the Android app's viewers - NOT part of the real backend
(app/), and never reachable over HTTP (server.py's read-only middleware
blocks every write route; this module has no route of its own at all). A
viewer only ever appears here via the manifest the desktop app publishes
(see backend/app/sync/reports.py's regenerate_viewer_manifest) - this phone
has no "add viewer" capability of its own, by design: onboarding a person
only ever happens on the desktop app.

Each viewer gets their own local SQLite file (db.py's existing per-user-file
convention, reused here for per-viewer instead - `viewer_<name>.db`),
refreshed by calling the REAL app.sync.engine.pull() - the exact same
Sheets-row-parsing and upsert-into-SQLAlchemy logic the desktop uses. Never
push() - nothing local ever changes (writes are blocked at the HTTP layer),
so there's nothing to push, and the Viewer-only credentials couldn't push
even if something tried to. Sheets API calls are already rate-limited
process-wide by app/sheets/adapter.py's with_retry().

MainActivity.kt's "Viewers" card calls list_viewers()/activate_viewer() only
- no add/remove. The background refresh loop (server.py) calls refresh_all()
on a timer.
"""
import env_setup  # noqa: F401 - side effect: sets env vars app.* reads, see its docstring

import json
import logging
from pathlib import Path
from typing import Optional

from app.config import BASE_DIR, settings
from app.db import create_empty_db, session_for, switch_active_db
from app.repositories.app_settings import SPREADSHEET_ID_KEY, AppSettingRepository
from app.sheets.adapter import GoogleSheetsService
from app.sync.engine import pull

logger = logging.getLogger("budget_dashboard.viewers")

VIEWERS_JSON_PATH = BASE_DIR / "viewers.json"
CREDENTIALS_PATH = BASE_DIR / "dashboard_credentials.json"


def _db_file_for(name: str) -> str:
    return f"viewer_{name}.db"


def _sheets_client() -> Optional[GoogleSheetsService]:
    if not CREDENTIALS_PATH.exists():
        return None
    return GoogleSheetsService(str(CREDENTIALS_PATH))


def _load_viewers() -> dict[str, str]:
    if not VIEWERS_JSON_PATH.exists():
        return {}
    try:
        return json.loads(VIEWERS_JSON_PATH.read_text())
    except (json.JSONDecodeError, OSError):
        return {}


def _save_viewers(viewers: dict[str, str]) -> None:
    VIEWERS_JSON_PATH.write_text(json.dumps(viewers, indent=2))


def list_viewers() -> list[str]:
    return sorted(_load_viewers().keys())


def list_viewers_json() -> str:
    """Same data as list_viewers(), pre-serialized - MainActivity.kt parses
    this with org.json rather than walking a Chaquopy PyObject list."""
    return json.dumps(list_viewers())


def refresh_manifest() -> None:
    """Pulls {name, spreadsheet_id} rows from the desktop-published manifest
    sheet and replaces the local viewer list wholesale - a viewer removed on
    desktop disappears here on the next refresh too, not just additions."""
    if not settings.viewer_manifest_spreadsheet_id:
        return
    sheets = _sheets_client()
    if sheets is None:
        return
    try:
        rows = sheets.get_rows(settings.viewer_manifest_spreadsheet_id, "Viewers")
    except Exception:
        logger.exception("Failed to read the viewer manifest")
        return
    viewers: dict[str, str] = {}
    for row in rows[1:]:  # row 0 is the "Name"/"Spreadsheet ID" header
        if len(row) >= 2 and row[0] and row[1]:
            viewers[row[0]] = row[1]
    _save_viewers(viewers)


def refresh_viewer_data(name: str) -> None:
    """Pulls one viewer's Transactions sheet into their own local SQLite
    file - via session_for(), NOT switch_active_db(), so refreshing in the
    background never disturbs whichever viewer is currently being served."""
    spreadsheet_id = _load_viewers().get(name)
    if not spreadsheet_id:
        raise ValueError(f"Unknown viewer {name!r} - call refresh_manifest() first")
    sheets = _sheets_client()
    if sheets is None:
        return
    db_file = _db_file_for(name)
    create_empty_db(db_file)  # idempotent - safe even if this viewer already has one
    raw_rows = sheets.get_rows(spreadsheet_id, "Transactions")
    with session_for(db_file) as session:
        # So /api/sync/config's google_spreadsheet_id/credentials_configured
        # reflect reality too - purely informational here (the read-only
        # frontend's subtitle only checks the read_only flag, never this),
        # but keeps this viewer's own database internally consistent.
        AppSettingRepository(session).set(SPREADSHEET_ID_KEY, spreadsheet_id)
        pull(session, sheets, spreadsheet_id, raw_rows)  # pull() itself commits


def activate_viewer(name: str) -> None:
    """Points every subsequent request (app/api/dashboard.py, app/api/
    transactions.py, via the normal get_session() dependency) at this
    viewer's local database - rendering is always from that local copy,
    never a live Sheets call per request."""
    if name not in _load_viewers():
        raise ValueError(f"Unknown viewer {name!r}")
    db_file = _db_file_for(name)
    create_empty_db(db_file)
    switch_active_db(db_file)


def refresh_all() -> None:
    """Called by server.py's background loop: manifest first (so a viewer
    added/removed on desktop is reflected before their data is touched),
    then each known viewer's data - one failure doesn't stop the others."""
    refresh_manifest()
    for name in list_viewers():
        try:
            refresh_viewer_data(name)
        except Exception:
            logger.exception("Failed to refresh viewer %r", name)
