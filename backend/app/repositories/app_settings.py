from sqlalchemy import select
from sqlalchemy.orm import Session
from typing import Optional

from app.models import AppSetting

SYNC_INTERVAL_KEY = "sync_interval_seconds"
SHEET_SORT_DIRECTION_KEY = "sheet_sort_direction"  # "desc" (default, newest first) or "asc"
PERIOD_TAB_SORT_DIRECTION_KEY = "period_tab_sort_direction"  # "desc" (default) or "asc" - left-to-right order of dated tabs
# Per-user - each user's own Google Sheet, if any. Deliberately NOT read from
# the global .env GOOGLE_SPREADSHEET_ID at request time: that value is only
# ever used once, to migrate the original single-user setup's spreadsheet
# into ITS OWN user's row here (see scheduler._migrate_legacy_spreadsheet_id)
# - every other/new user starts with no spreadsheet configured, full stop,
# so switching to them never risks syncing their local data against someone
# else's real Google Sheet.
SPREADSHEET_ID_KEY = "spreadsheet_id"
# Per-user - path to THIS user's own uploaded service account key file (see
# app/api/sync.py's /credentials endpoint), under data/credentials/. Empty
# means "no key of their own" - scheduler falls back to the shared default
# from .env (GOOGLE_SERVICE_ACCOUNT_KEY_PATH) in that case, so the original
# single-user setup keeps working without anyone uploading anything.
CREDENTIALS_PATH_KEY = "credentials_path"


class AppSettingRepository:
    def __init__(self, session: Session):
        self.session = session

    def get(self, key: str) -> Optional[str]:
        row = self.session.get(AppSetting, key)
        return row.value if row else None

    def set(self, key: str, value: str) -> AppSetting:
        row = self.session.get(AppSetting, key)
        if row:
            row.value = value
        else:
            row = AppSetting(key=key, value=value)
            self.session.add(row)
        self.session.flush()
        return row

    def clear(self, key: str) -> bool:
        row = self.session.get(AppSetting, key)
        if not row:
            return False
        self.session.delete(row)
        self.session.flush()
        return True
