from datetime import timezone

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_session
from app.repositories.sync import SyncRepository
from app.sync import scheduler

router = APIRouter(prefix="/api/sync", tags=["sync"])


class IntervalIn(BaseModel):
    seconds: int = Field(ge=1)


class SortDirectionIn(BaseModel):
    descending: bool


@router.get("/status")
def status():
    return scheduler.get_status()


@router.get("/config")
def config():
    """Non-secret config for the Settings page - never returns the key path or
    credentials themselves, just whether they're configured."""
    return {
        "credentials_configured": settings.credentials_configured,
        "google_spreadsheet_id": settings.google_spreadsheet_id,
        "sync_interval_seconds": scheduler.get_interval(),
        "sync_interval_default": settings.sync_interval_seconds,
        "sync_interval_min": scheduler.MIN_INTERVAL_SECONDS,
        "sheet_sort_descending": scheduler.get_sort_descending(),
    }


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
