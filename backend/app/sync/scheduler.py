"""Background sync loop (spec section 18) - runs inside the same process as the web
UI, so a single `run.bat` gives you both. Exposes a small in-memory status object the
UI polls (spec section 19) and a manual trigger_now() for the "Sync Now" button/CLI."""
import logging
import threading
from datetime import datetime, timezone

from apscheduler.schedulers.background import BackgroundScheduler
from googleapiclient.errors import HttpError

from app.config import settings
from app.db import session_scope
from app.repositories.app_settings import SYNC_INTERVAL_KEY, AppSettingRepository
from app.repositories.categories import CategoryRepository
from app.repositories.accounts import AccountRepository
from app.sheets.adapter import GoogleSheetsService
from app.sync.engine import run_sync_cycle
from typing import Optional

MIN_INTERVAL_SECONDS = 15  # floor to avoid hammering the Sheets API from the UI

NEEDS_SPREADSHEET_ID_MSG = (
    "GOOGLE_SPREADSHEET_ID is not set, and this service account can't create its own "
    "spreadsheet - personal (non-Workspace) Google accounts give service accounts no "
    "Drive storage of their own, so file creation is refused. Fix: create a blank "
    "Google Sheet yourself, share it with {email} as Editor, then set "
    "GOOGLE_SPREADSHEET_ID to its ID (from the sheet's URL) in .env."
)

logger = logging.getLogger("budget_tracker.scheduler")

# Two separate locks, deliberately: _sync_lock guards "only one sync cycle at a
# time" and is held for the whole duration of run_once(); _status_lock guards only
# the tiny _status dict and is never held for longer than a dict read/update. A
# single shared lock here would deadlock - run_once() holds it for the sync, then
# calls _set_status() from the same thread, which would try to reacquire the same
# (non-reentrant) lock and block forever. That was a real bug that shipped and hung
# every sync-now call; keep these separate.
_sync_lock = threading.Lock()
_status_lock = threading.Lock()
_status = {
    "state": "not_configured",  # not_configured | idle | syncing | error
    "last_synced_at": None,
    "last_summary": None,
    "last_error": None,
}
_scheduler: Optional[BackgroundScheduler] = None
_active_spreadsheet_id: Optional[str] = None  # resolved lazily: settings value, or one this process created
_current_interval: int = settings.sync_interval_seconds  # overridden from DB (if set) in start()


def get_status() -> dict:
    with _status_lock:
        return dict(_status)


def _set_status(**kwargs) -> None:
    with _status_lock:
        _status.update(kwargs)


def _sheets_client() -> Optional[GoogleSheetsService]:
    if not settings.credentials_configured:
        return None
    return GoogleSheetsService(settings.google_service_account_key_path)


def _resolve_spreadsheet_id(sheets: GoogleSheetsService) -> str:
    """Uses GOOGLE_SPREADSHEET_ID from .env if set. Otherwise makes one best-effort
    attempt to create a new 'Budget Tracker' spreadsheet (works for Workspace-backed
    service accounts) - if that's refused (the common case for personal @gmail.com
    accounts, which give service accounts no Drive storage of their own), raises a
    clear, actionable error instead of retrying or hanging."""
    global _active_spreadsheet_id
    if settings.google_spreadsheet_id:
        return settings.google_spreadsheet_id
    if _active_spreadsheet_id:
        return _active_spreadsheet_id

    try:
        spreadsheet_id = sheets.create_spreadsheet("Budget Tracker")
    except HttpError as e:
        status = e.resp.status if getattr(e, "resp", None) else None
        if status == 403:
            raise RuntimeError(NEEDS_SPREADSHEET_ID_MSG.format(email=sheets.service_account_email)) from e
        raise

    if settings.owner_email:
        sheets.share_with(spreadsheet_id, settings.owner_email, role="writer")
    url = sheets.spreadsheet_url(spreadsheet_id)
    logger.warning(
        "Created new spreadsheet %r (%s). Add GOOGLE_SPREADSHEET_ID=%s to .env and "
        "restart so future runs reuse this sheet instead of creating another one.",
        spreadsheet_id, url, spreadsheet_id,
    )
    _active_spreadsheet_id = spreadsheet_id
    with session_scope() as session:
        from app.repositories.sync import SyncRepository
        SyncRepository(session).log(
            f"Created new spreadsheet: {url} - set GOOGLE_SPREADSHEET_ID={spreadsheet_id} in .env",
        )
    return spreadsheet_id


def run_once() -> dict:
    """Runs a single sync cycle synchronously and returns its summary. Safe to call
    from the scheduler, the CLI, or the 'Sync Now' API endpoint - only one runs at a
    time (guarded by _sync_lock) so concurrent triggers can't race each other."""
    if not settings.credentials_configured:
        _set_status(state="not_configured")
        return {"error": "Google credentials not configured yet - see docs/service_account_setup.md"}

    if not _sync_lock.acquire(blocking=False):
        return {"error": "sync already in progress"}
    try:
        _set_status(state="syncing")
        sheets = _sheets_client()
        spreadsheet_id = _resolve_spreadsheet_id(sheets)
        with session_scope() as session:
            CategoryRepository(session).ensure_defaults()
            AccountRepository(session).ensure_default()
            summary = run_sync_cycle(session, sheets, spreadsheet_id)
        ok = not summary.get("errors")
        _set_status(
            state="idle" if ok else "error",
            last_synced_at=datetime.now(timezone.utc).isoformat(),
            last_summary=dict(summary),
            last_error=None if ok else "; ".join(summary["errors"]),
        )
        return dict(summary)
    except Exception as e:
        logger.exception("sync cycle crashed")
        _set_status(state="error", last_error=str(e))
        return {"error": str(e)}
    finally:
        _sync_lock.release()


def get_interval() -> int:
    return _current_interval


def set_interval(seconds: int) -> int:
    """Overrides the sync interval at runtime - persists to the DB (so it survives
    restarts, unlike a .env change which needs one) and reschedules the live
    APScheduler job immediately, no restart required."""
    global _current_interval
    seconds = max(int(seconds), MIN_INTERVAL_SECONDS)
    with session_scope() as session:
        AppSettingRepository(session).set(SYNC_INTERVAL_KEY, str(seconds))
    _current_interval = seconds
    if _scheduler is not None:
        _scheduler.reschedule_job("sync_cycle", trigger="interval", seconds=seconds)
    logger.info("Sync interval changed to %ss", seconds)
    return seconds


def start() -> None:
    global _scheduler, _current_interval
    if _scheduler is not None:
        return
    if settings.credentials_configured:
        _set_status(state="idle")

    with session_scope() as session:
        override = AppSettingRepository(session).get(SYNC_INTERVAL_KEY)
    _current_interval = max(int(override), MIN_INTERVAL_SECONDS) if override else settings.sync_interval_seconds

    _scheduler = BackgroundScheduler(daemon=True)
    _scheduler.add_job(run_once, "interval", seconds=_current_interval,
                        id="sync_cycle", max_instances=1, coalesce=True, next_run_time=datetime.now())
    _scheduler.start()
    logger.info("Sync scheduler started (interval=%ss)", _current_interval)


def stop() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
