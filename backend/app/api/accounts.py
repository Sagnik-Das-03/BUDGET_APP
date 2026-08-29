from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import get_session
from app.repositories.accounts import AccountRepository
from app.schemas import AccountIn, AccountOut

router = APIRouter(prefix="/api/accounts", tags=["accounts"])


@router.get("", response_model=list[AccountOut])
def list_accounts(include_inactive: bool = False, session: Session = Depends(get_session)):
    return AccountRepository(session).list(include_inactive=include_inactive)


@router.post("", response_model=AccountOut)
def add_account(payload: AccountIn, session: Session = Depends(get_session)):
    acct = AccountRepository(session).get_or_create(payload.name, payload.account_type)
    session.commit()
    return acct


@router.delete("/{account_id}")
def deactivate_account(account_id: int, session: Session = Depends(get_session)):
    acct = AccountRepository(session).deactivate(account_id)
    if not acct:
        raise HTTPException(404, "Account not found")
    session.commit()
    return {"ok": True}
