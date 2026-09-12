import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import get_session
from app.models import SavedView
from app.repositories.saved_views import SavedViewRepository
from app.schemas import SavedViewIn, SavedViewOut

router = APIRouter(prefix="/api/saved_views", tags=["saved_views"])


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
    deleted = SavedViewRepository(session).delete(view_id)
    session.commit()
    if not deleted:
        raise HTTPException(404, "View not found")
    return {"deleted": True}
