"""Background sync loop (spec section 18) - runs inside the same process as the web
UI, so a single `run.bat` gives you both. Exposes a small in-memory status object the
UI polls (spec section 19) and a manual trigger_now() for the "Sync Now" button/CLI."""
import logging
import threading
from datetime import datetime, timezone
from pathlib import Path

from apscheduler.schedulers.background import BackgroundScheduler

from app.config import settings
from app.db import session_scope
from app.repositories.app_settings import (
    CREDENTIALS_PATH_KEY, PERIOD_TAB_SORT_DIRECTION_KEY, SHEET_SORT_DIRECTION_KEY, SPREADSHEET_ID_KEY,
    SYNC_INTERVAL_KEY, AppSettingRepository,
)
from app.repositories.categories import CategoryRepository
from app.repositories.accounts import AccountRepository
from app.sheets.adapter import GoogleSheetsService
from app.sync import periods as periods_mod
from app.sync.engine import compact_and_sort, run_sync_cycle
from typing import Optional

MIN_INTERVAL_SECONDS = 15  # floor to avoid hammering the Sheets API from the UI

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
_current_interval: int = settings.sync_interval_seconds  # overridden from DB (if set) in start()
_current_sort_descending: bool = True  # overridden from DB (if set) in start()
_current_tab_sort_descending: bool = True  # overridden from DB (if set) in start()
# The ACTIVE USER's own spreadsheet id - never a shared/global fallback. Kept
# as a cache (like the settings above) refreshed by _load_settings_for_active_user(),
# which runs both at startup and every time the active user changes, so
# switching profiles can never leave one user's sync pointed at another
# user's real Google Sheet using stale, previously-loaded settings.
_current_spreadsheet_id: str = ""
# The ACTIVE USER's own uploaded service account key path, if they have one -
# same refresh discipline as the spreadsheet id above. Empty means "use the
# shared default from .env" (credentials_path_or_default() below), not "no
# credentials" - that's what keeps the original single-user setup working
# without anyone having to re-upload anything.
_current_credentials_path: str = ""


def get_status() -> dict:
    with _status_lock:
        return dict(_status)


def _set_status(**kwargs) -> None:
    with _status_lock:
        _status.update(kwargs)


def credentials_path_or_default() -> Optional[str]:
    """The active user's own key file if they've uploaded one, else the
    shared default from .env - None if neither exists."""
    if _current_credentials_path and Path(_current_credentials_path).exists():
        return _current_credentials_path
    if settings.google_service_account_key_path and Path(settings.google_service_account_key_path).exists():
        return settings.google_service_account_key_path
    return None


def has_own_credentials() -> bool:
    return bool(_current_credentials_path)


def is_credentials_configured() -> bool:
    return credentials_path_or_default() is not None


def _sheets_client() -> Optional[GoogleSheetsService]:
    path = credentials_path_or_default()
    if not path:
        return None
    return GoogleSheetsService(path)


def run_once() -> dict:
    """Runs a single sync cycle synchronously and returns its summary. Safe to call
    from the scheduler, the CLI, or the 'Sync Now' API endpoint - only one runs at a
    time (guarded by _sync_lock) so concurrent triggers can't race each other."""
    if not is_credentials_configured() or not _current_spreadsheet_id:
        _set_status(state="not_configured")
        return {"error": "Google Sheets isn't configured for this user - set a Spreadsheet ID in Settings."}

    if not _sync_lock.acquire(blocking=False):
        return {"error": "sync already in progress"}
    try:
        _set_status(state="syncing")
        sheets = _sheets_client()
        spreadsheet_id = _current_spreadsheet_id
        with session_scope() as session:
            CategoryRepository(session).ensure_defaults()
            AccountRepository(session).ensure_default()
            summary = run_sync_cycle(
                session, sheets, spreadsheet_id,
                sort_descending=_current_sort_descending, tab_sort_descending=_current_tab_sort_descending,
            )
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


def run_compact_and_sort_once() -> dict:
    """Runs just the Sheet tidy-up pass (blank-row cleanup, date sort) on
    demand, without waiting for the next full sync cycle - for the "Clean
    Up & Sort Sheet Now" button in Settings. Shares _sync_lock with
    run_once() so it can't run concurrently with (or be raced by) a real
    pull/push cycle."""
    if not is_credentials_configured() or not _current_spreadsheet_id:
        return {"error": "Google Sheets isn't configured for this user - set a Spreadsheet ID in Settings."}
    if not _sync_lock.acquire(blocking=False):
        return {"error": "sync already in progress"}
    try:
        sheets = _sheets_client()
        return compact_and_sort(sheets, _current_spreadsheet_id, descending=_current_sort_descending)
    except Exception as e:
        logger.exception("manual sheet compaction crashed")
        return {"error": str(e)}
    finally:
        _sync_lock.release()


def run_reorder_tabs_once() -> dict:
    """Runs just the period-tab reordering pass on demand - for the
    "Reorder Tabs Now" button in Settings. Shares _sync_lock with
    run_once() so it can't run concurrently with (or be raced by) a real
    pull/push cycle."""
    if not is_credentials_configured() or not _current_spreadsheet_id:
        return {"error": "Google Sheets isn't configured for this user - set a Spreadsheet ID in Settings."}
    if not _sync_lock.acquire(blocking=False):
        return {"error": "sync already in progress"}
    try:
        sheets = _sheets_client()
        return periods_mod.reorder_period_tabs(sheets, _current_spreadsheet_id, descending=_current_tab_sort_descending)
    except Exception as e:
        logger.exception("manual tab reorder crashed")
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


def get_sort_descending() -> bool:
    return _current_sort_descending


def set_sort_descending(descending: bool) -> bool:
    """Overrides the Transactions tab's sort direction at runtime - persists
    to the DB so it survives restarts. Takes effect on the next sync/compact
    pass, not retroactively (it doesn't re-sort the sheet itself)."""
    global _current_sort_descending
    with session_scope() as session:
        AppSettingRepository(session).set(SHEET_SORT_DIRECTION_KEY, "desc" if descending else "asc")
    _current_sort_descending = descending
    logger.info("Sheet sort direction changed to %s", "descending (newest first)" if descending else "ascending (oldest first)")
    return descending


def get_tab_sort_descending() -> bool:
    return _current_tab_sort_descending


def set_tab_sort_descending(descending: bool) -> bool:
    """Overrides the dated (monthly period) tabs' left-to-right order at
    runtime - persists to the DB so it survives restarts. Takes effect on
    the next sync/reorder pass, not retroactively."""
    global _current_tab_sort_descending
    with session_scope() as session:
        AppSettingRepository(session).set(PERIOD_TAB_SORT_DIRECTION_KEY, "desc" if descending else "asc")
    _current_tab_sort_descending = descending
    logger.info("Period tab order changed to %s", "descending (newest first)" if descending else "ascending (oldest first)")
    return descending


def get_spreadsheet_id() -> str:
    return _current_spreadsheet_id


def set_spreadsheet_id(spreadsheet_id: str) -> str:
    """Sets (or clears, given "") the spreadsheet id for whichever user is
    CURRENTLY active - never any other user's. This is the only place a
    spreadsheet id is written outside the one-time legacy migration below."""
    global _current_spreadsheet_id
    spreadsheet_id = spreadsheet_id.strip()
    with session_scope() as session:
        repo = AppSettingRepository(session)
        if spreadsheet_id:
            repo.set(SPREADSHEET_ID_KEY, spreadsheet_id)
        else:
            repo.clear(SPREADSHEET_ID_KEY)
    _current_spreadsheet_id = spreadsheet_id
    _set_status(state="idle" if (is_credentials_configured() and spreadsheet_id) else "not_configured")
    logger.info("Spreadsheet id %s for the active user", "set" if spreadsheet_id else "cleared")
    return spreadsheet_id


def _migrate_legacy_spreadsheet_id(session) -> None:
    """One-time: the original single-user setup's spreadsheet id lived in
    .env (GOOGLE_SPREADSHEET_ID), global to the whole process. It's migrated
    into that SAME user's own per-user setting here, exactly once (only if
    they don't already have one of their own), and NEVER applied to any
    other user - a brand new profile (demo, admin, ...) always starts with
    sync unconfigured, full stop, so switching into one can't silently sync
    its local data against someone else's real Google Sheet."""
    from app.db import DEFAULT_USERNAME
    from app.user_registry import registry
    if registry.get_active() != DEFAULT_USERNAME or not settings.google_spreadsheet_id:
        return
    repo = AppSettingRepository(session)
    if repo.get(SPREADSHEET_ID_KEY) is None:
        repo.set(SPREADSHEET_ID_KEY, settings.google_spreadsheet_id)
        logger.info("Migrated legacy GOOGLE_SPREADSHEET_ID into %r's own settings", DEFAULT_USERNAME)


def get_credentials_path() -> str:
    return _current_credentials_path


def set_credentials_path(path: str) -> None:
    """Records the ACTIVE user's own credentials file path - the caller
    (app/api/sync.py's /credentials endpoint) is responsible for actually
    validating and writing the key file itself; this just persists the
    pointer to it, same discipline as set_spreadsheet_id()."""
    global _current_credentials_path
    with session_scope() as session:
        AppSettingRepository(session).set(CREDENTIALS_PATH_KEY, path)
    _current_credentials_path = path
    _set_status(state="idle" if (is_credentials_configured() and _current_spreadsheet_id) else "not_configured")
    logger.info("Own credentials set for the active user")


def clear_credentials_path() -> None:
    """Reverts the active user to the shared default credentials (.env),
    if any - does NOT delete the uploaded key file itself, just stops
    pointing at it, in case they want to switch back later."""
    global _current_credentials_path
    with session_scope() as session:
        AppSettingRepository(session).clear(CREDENTIALS_PATH_KEY)
    _current_credentials_path = ""
    _set_status(state="idle" if (is_credentials_configured() and _current_spreadsheet_id) else "not_configured")
    logger.info("Reverted the active user to the shared default credentials")


def _load_settings_for_active_user() -> None:
    global _current_interval, _current_sort_descending, _current_tab_sort_descending
    global _current_spreadsheet_id, _current_credentials_path
    with session_scope() as session:
        _migrate_legacy_spreadsheet_id(session)
        repo = AppSettingRepository(session)
        interval_override = repo.get(SYNC_INTERVAL_KEY)
        sort_override = repo.get(SHEET_SORT_DIRECTION_KEY)
        tab_sort_override = repo.get(PERIOD_TAB_SORT_DIRECTION_KEY)
        spreadsheet_id = repo.get(SPREADSHEET_ID_KEY)
        credentials_path = repo.get(CREDENTIALS_PATH_KEY)
    _current_interval = max(int(interval_override), MIN_INTERVAL_SECONDS) if interval_override else settings.sync_interval_seconds
    _current_sort_descending = sort_override != "asc"
    _current_tab_sort_descending = tab_sort_override != "asc"
    _current_spreadsheet_id = spreadsheet_id or ""
    _current_credentials_path = credentials_path or ""
    _set_status(state="idle" if (is_credentials_configured() and _current_spreadsheet_id) else "not_configured")


def reload_for_active_user() -> None:
    """Re-reads every per-user sync setting (interval, sort directions,
    spreadsheet id) from whichever user is now active and reschedules the
    interval job to match. Called right after switch_active_db() so a
    profile switch can never leave sync running on stale settings loaded
    from the PREVIOUS user - the spreadsheet id above all."""
    _load_settings_for_active_user()
    if _scheduler is not None:
        _scheduler.reschedule_job("sync_cycle", trigger="interval", seconds=_current_interval)
    logger.info(
        "Sync settings reloaded for the active user (spreadsheet %s)",
        "configured" if _current_spreadsheet_id else "not configured",
    )


def start() -> None:
    global _scheduler
    if _scheduler is not None:
        return
    _load_settings_for_active_user()

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
