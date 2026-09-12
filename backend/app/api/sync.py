import json
from datetime import timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.config import BASE_DIR, settings
from app.db import get_session
from app.repositories.sync import SyncRepository
from app.sync import scheduler
from app.user_registry import registry

router = APIRouter(prefix="/api/sync", tags=["sync"])

CREDENTIALS_DIR = BASE_DIR / "data" / "credentials"


class IntervalIn(BaseModel):
    seconds: int = Field(ge=1)


class SortDirectionIn(BaseModel):
    descending: bool


class SpreadsheetIdIn(BaseModel):
    spreadsheet_id: str = Field(default="", max_length=200)


class CredentialsIn(BaseModel):
    # The raw contents of a downloaded service account JSON key file, pasted
    # or uploaded client-side - never a file path (each user's own key has
    # to actually be transferred to the server, not just referenced, since
    # it belongs to them and not to wherever this process happens to run).
    credentials_json: str = Field(min_length=1, max_length=20_000)


@router.get("/status")
def status():
    return scheduler.get_status()


@router.get("/config")
def config():
    """Non-secret config for the Settings page - never returns the key
    content or file path themselves, just whether credentials are configured
    and whose (this user's own upload, or the shared .env default). The
    spreadsheet id is per-user (whoever is currently active), NOT the global
    .env value - see app/sync/scheduler.py for why that distinction matters."""
    return {
        "credentials_configured": scheduler.is_credentials_configured(),
        "has_own_credentials": scheduler.has_own_credentials(),
        "google_spreadsheet_id": scheduler.get_spreadsheet_id(),
        "sync_interval_seconds": scheduler.get_interval(),
        "sync_interval_default": settings.sync_interval_seconds,
        "sync_interval_min": scheduler.MIN_INTERVAL_SECONDS,
        "sheet_sort_descending": scheduler.get_sort_descending(),
        "period_tab_sort_descending": scheduler.get_tab_sort_descending(),
    }


@router.post("/spreadsheet_id")
def set_spreadsheet_id(payload: SpreadsheetIdIn):
    """Sets (or, given an empty string, clears) the Google Sheet this user
    syncs to. Per-user, not global - see app/sync/scheduler.py."""
    effective = scheduler.set_spreadsheet_id(payload.spreadsheet_id)
    return {"google_spreadsheet_id": effective}


@router.post("/credentials")
def upload_credentials(payload: CredentialsIn):
    """Saves a service account key file for the CURRENTLY ACTIVE user only,
    under data/credentials/<username>.json, and points that user's own
    setting at it. Validated as a real service account key (not just any
    JSON) before being written - a malformed file would otherwise fail
    confusingly deep inside the Sheets client on the next sync attempt."""
    try:
        parsed = json.loads(payload.credentials_json)
    except json.JSONDecodeError as e:
        raise HTTPException(400, f"Not valid JSON: {e}") from e
    if not isinstance(parsed, dict) or parsed.get("type") != "service_account":
        raise HTTPException(400, "Not a service account key file (missing \"type\": \"service_account\")")
    for field in ("client_email", "private_key", "project_id"):
        if not parsed.get(field):
            raise HTTPException(400, f"Not a service account key file (missing {field!r})")

    username = registry.get_active()
    if not username:
        raise HTTPException(409, "No active user")
    CREDENTIALS_DIR.mkdir(parents=True, exist_ok=True)
    path = CREDENTIALS_DIR / f"{username}.json"
    path.write_text(payload.credentials_json)

    scheduler.set_credentials_path(str(path))
    return {"configured": True, "client_email": parsed["client_email"]}


@router.delete("/credentials")
def clear_credentials():
    """Reverts the active user to the shared .env default credentials, if
    any - does not delete their uploaded key file, just stops using it."""
    scheduler.clear_credentials_path()
    return {"configured": scheduler.is_credentials_configured()}


@router.post("/interval")
def set_interval(payload: IntervalIn):
    """Overrides the sync interval immediately, no restart needed - persists to
    the DB so it survives one, and is separate from SYNC_INTERVAL_SECONDS in
    .env (which is just the fallback default when no override has been set)."""
    effective = scheduler.set_interval(payload.seconds)
    return {"sync_interval_seconds": effective}


@router.post("/now")
def sync_now():
    return scheduler.run_once()


@router.post("/sort_direction")
def set_sort_direction(payload: SortDirectionIn):
    """Sets which direction the Transactions tab is kept sorted in on every
    sync (and by the "Clean Up & Sort Sheet Now" button) - newest first
    (descending, the default) or oldest first (ascending)."""
    effective = scheduler.set_sort_descending(payload.descending)
    return {"sheet_sort_descending": effective}


@router.post("/compact")
def compact_sheet_now():
    """Cleans up blank rows and re-sorts the Transactions tab by date
    (newest first) immediately, without waiting for the next scheduled
    sync - this normally already happens as part of every sync cycle."""
    return scheduler.run_compact_and_sort_once()


@router.post("/tab_order_direction")
def set_tab_order_direction(payload: SortDirectionIn):
    """Sets which direction the dated (monthly period) tabs are kept
    ordered in, left to right, on every sync - newest first (descending,
    the default) or oldest first (ascending)."""
    effective = scheduler.set_tab_sort_descending(payload.descending)
    return {"period_tab_sort_descending": effective}


@router.post("/reorder_tabs")
def reorder_tabs_now():
    """Re-sorts the dated tabs' left-to-right order immediately, without
    waiting for the next scheduled sync - this normally already happens as
    part of every sync cycle."""
    return scheduler.run_reorder_tabs_once()


@router.get("/logs")
def logs(limit: int = 100, session: Session = Depends(get_session)):
    entries = SyncRepository(session).recent_logs(limit)
    return [
        # SyncLog.timestamp comes back from SQLite's CURRENT_TIMESTAMP as a
        # naive datetime - it IS UTC, but with no "Z"/offset marker, so the
        # frontend's `new Date(...)` would otherwise assume it's already
        # local time and display it unconverted, off by the browser's UTC
        # offset. Attaching UTC tzinfo here makes the ISO string explicit.
        {"timestamp": e.timestamp.replace(tzinfo=timezone.utc).isoformat(),
         "level": e.level.value if hasattr(e.level, "value") else e.level, "message": e.message}
        for e in entries
    ]
