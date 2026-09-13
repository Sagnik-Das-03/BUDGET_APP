import json
import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import get_session
from app.models import SavedView
from app.repositories.saved_views import SavedViewRepository
from app.schemas import SavedViewIn, SavedViewOut
from app.sheets.adapter import GoogleSheetsService
from app.sync import scheduler

router = APIRouter(prefix="/api/saved_views", tags=["saved_views"])
logger = logging.getLogger("budget_tracker.saved_views")


def _to_out(view: SavedView) -> SavedViewOut:
    return SavedViewOut(id=view.id, name=view.name, filters=json.loads(view.filters), created_at=view.created_at)


@router.get("", response_model=list[SavedViewOut])
def list_views(session: Session = Depends(get_session)):
    return [_to_out(v) for v in SavedViewRepository(session).list()]


@router.post("", response_model=SavedViewOut)
def create_view(payload: SavedViewIn, session: Session = Depends(get_session)):
    view = SavedViewRepository(session).create(payload.name, json.dumps(payload.filters))
    session.commit()
    return _to_out(view)


@router.delete("/{view_id}")
def delete_view(view_id: int, session: Session = Depends(get_session)):
    repo = SavedViewRepository(session)
    view = repo.get(view_id)
    if not view:
        raise HTTPException(404, "View not found")
    name, sheet_gid = view.name, view.sheet_gid

    repo.delete(view_id)
    session.commit()

    # Best-effort - the view itself is already gone either way; Sheets being
    # unreachable right now (or never configured) just leaves an orphaned
    # tab behind, a cosmetic issue not worth failing/retrying this delete over.
    if sheet_gid is not None:
        try:
            path = scheduler.credentials_path_or_default()
            spreadsheet_id = scheduler.get_spreadsheet_id()
            if path and spreadsheet_id:
                GoogleSheetsService(path).delete_sheet(spreadsheet_id, sheet_gid)
        except Exception:
            logger.exception("Failed to delete saved view %r's Sheets tab (gid=%s)", name, sheet_gid)

    return {"deleted": True}
