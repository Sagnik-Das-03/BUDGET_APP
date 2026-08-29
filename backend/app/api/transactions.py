from datetime import date as date_type

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import get_session
from app.models import Account, Category, Transaction, TransactionType
from app.repositories.accounts import AccountRepository
from app.repositories.categories import CategoryRepository
from app.repositories.transactions import TransactionRepository
from app.schemas import TransactionIn, TransactionOut
from typing import Optional

router = APIRouter(prefix="/api/transactions", tags=["transactions"])


def _to_out(txn: Transaction) -> TransactionOut:
    return TransactionOut(
        transaction_id=txn.transaction_id, date=txn.date, description=txn.description, amount=txn.amount,
        transaction_type=txn.transaction_type.value if hasattr(txn.transaction_type, "value") else txn.transaction_type,
        category=txn.category.name, account=txn.account.name, period_key=txn.period_key, notes=txn.notes,
        source=txn.source.value if hasattr(txn.source, "value") else txn.source,
        sync_status=txn.sync_status.value if hasattr(txn.sync_status, "value") else txn.sync_status,
        created_at=txn.created_at, updated_at=txn.updated_at,
    )


@router.get("", response_model=list[TransactionOut])
def list_transactions(
    year: Optional[int] = None, month: Optional[int] = None, category: Optional[str] = None,
    account: Optional[str] = None, type: Optional[str] = None,
    date_from: Optional[date_type] = None, date_to: Optional[date_type] = None,
    search: Optional[str] = None, session: Session = Depends(get_session),
):
    repo = TransactionRepository(session)
    cat = CategoryRepository(session).get_by_name(category) if category else None
    acct = AccountRepository(session).get_by_name(account) if account else None
    rows = repo.filter(
        year=year, month=month, category_id=cat.id if cat else None, account_id=acct.id if acct else None,
        transaction_type=type, date_from=date_from, date_to=date_to, search=search,
    )
    return [_to_out(t) for t in rows]


@router.post("", response_model=TransactionOut)
def create_transaction(payload: TransactionIn, session: Session = Depends(get_session)):
    cat_repo, acct_repo, tx_repo = CategoryRepository(session), AccountRepository(session), TransactionRepository(session)
    category = cat_repo.add(payload.category)
    account = acct_repo.get_or_create(payload.account)
    txn = tx_repo.create(
        date=payload.date, description=payload.description, amount=payload.amount,
        transaction_type=TransactionType(payload.transaction_type), category=category, account=account,
        notes=payload.notes,
    )
    session.commit()
    return _to_out(txn)


@router.delete("/pending")
def delete_all_pending(session: Session = Depends(get_session)):
    """Bulk-deletes every transaction currently in pending/error sync state -
    registered before /{transaction_id} so "pending" isn't swallowed as an id."""
    result = TransactionRepository(session).delete_all_pending()
    session.commit()
    return result


@router.put("/{transaction_id}", response_model=TransactionOut)
def update_transaction(transaction_id: str, payload: TransactionIn, session: Session = Depends(get_session)):
    cat_repo, acct_repo, tx_repo = CategoryRepository(session), AccountRepository(session), TransactionRepository(session)
    category = cat_repo.add(payload.category)
    account = acct_repo.get_or_create(payload.account)
    txn = tx_repo.update(
        transaction_id, date=payload.date, description=payload.description, amount=payload.amount,
        transaction_type=TransactionType(payload.transaction_type), category=category, account=account,
        notes=payload.notes,
    )
    if not txn:
        raise HTTPException(404, "Transaction not found")
    session.commit()
    return _to_out(txn)


@router.delete("/{transaction_id}")
def delete_transaction(transaction_id: str, session: Session = Depends(get_session)):
    txn = TransactionRepository(session).soft_delete(transaction_id)
    if not txn:
        raise HTTPException(404, "Transaction not found")
    session.commit()
    return {"ok": True}
