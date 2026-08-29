from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Account
from typing import Optional


class AccountRepository:
    def __init__(self, session: Session):
        self.session = session

    def list(self, include_inactive: bool = False) -> list[Account]:
        stmt = select(Account).order_by(Account.name)
        if not include_inactive:
            stmt = stmt.where(Account.is_active.is_(True))
        return list(self.session.scalars(stmt))

    def get_by_name(self, name: str) -> Optional[Account]:
        return self.session.scalar(select(Account).where(Account.name == name))

    def get_or_create(self, name: str, account_type: str = "General") -> Account:
        acct = self.get_by_name(name)
        if acct:
            return acct
        acct = Account(name=name, account_type=account_type, is_active=True)
        self.session.add(acct)
        self.session.flush()
        return acct

    def deactivate(self, account_id: int) -> Optional[Account]:
        acct = self.session.get(Account, account_id)
        if not acct:
            return None
        acct.is_active = False
        self.session.flush()
        return acct

    def ensure_default(self) -> Account:
        return self.get_or_create("Primary", "General")
