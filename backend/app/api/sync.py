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


@router.get("/logs")
def logs(limit: int = 100, session: Session = Depends(get_session)):
    entries = SyncRepository(session).recent_logs(limit)
    return [
        {"timestamp": e.timestamp.isoformat(), "level": e.level.value if hasattr(e.level, "value") else e.level,
         "message": e.message}
        for e in entries
    ]
