from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import SavedView


class SavedViewRepository:
    def __init__(self, session: Session):
        self.session = session

    def list(self) -> list[SavedView]:
        return list(self.session.scalars(select(SavedView).order_by(SavedView.created_at)))

    def get(self, view_id: int) -> Optional[SavedView]:
        return self.session.get(SavedView, view_id)

    def create(self, name: str, filters_json: str) -> SavedView:
        view = SavedView(name=name, filters=filters_json)
        self.session.add(view)
        self.session.flush()
        return view

    def delete(self, view_id: int) -> bool:
        view = self.get(view_id)
        if not view:
            return False
        self.session.delete(view)
        self.session.flush()
        return True
