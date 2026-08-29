from sqlalchemy import select
from sqlalchemy.orm import Session
from typing import Optional

from app.models import AppSetting

SYNC_INTERVAL_KEY = "sync_interval_seconds"


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
