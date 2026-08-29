import json
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import LogLevel, SyncLog, SyncMeta
from app.utils import utcnow
from typing import Optional


class SyncRepository:
    def __init__(self, session: Session):
        self.session = session

    def get_meta(self, spreadsheet_id: str, sheet_name: str) -> Optional[SyncMeta]:
        return self.session.scalar(
            select(SyncMeta).where(SyncMeta.spreadsheet_id == spreadsheet_id, SyncMeta.sheet_name == sheet_name)
        )

    def touch_meta(self, spreadsheet_id: str, sheet_name: str, *, sheet_gid: Optional[int] = None,
                    row_count: Optional[int] = None) -> SyncMeta:
        meta = self.get_meta(spreadsheet_id, sheet_name)
        if not meta:
            meta = SyncMeta(spreadsheet_id=spreadsheet_id, sheet_name=sheet_name)
            self.session.add(meta)
        meta.last_synced_at = utcnow()
        if sheet_gid is not None:
            meta.sheet_gid = sheet_gid
        if row_count is not None:
            meta.last_row_count = row_count
        self.session.flush()
        return meta

    def log(self, message: str, level: LogLevel = LogLevel.info, details: Optional[dict] = None) -> SyncLog:
        entry = SyncLog(message=message, level=level, details=json.dumps(details) if details else None)
        self.session.add(entry)
        self.session.flush()
        return entry

    def recent_logs(self, limit: int = 100) -> list[SyncLog]:
        stmt = select(SyncLog).order_by(SyncLog.timestamp.desc()).limit(limit)
        return list(self.session.scalars(stmt))

    def last_sync_at(self) -> Optional[datetime]:
        stmt = select(SyncMeta.last_synced_at).order_by(SyncMeta.last_synced_at.desc()).limit(1)
        return self.session.scalar(stmt)
