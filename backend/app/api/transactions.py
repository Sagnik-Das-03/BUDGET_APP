from datetime import date as date_type

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db import get_session
from app.models import Account, Category, SyncStatus, Transaction, TransactionType
from app.repositories.accounts import AccountRepository
from app.repositories.categories import CategoryRepository
from app.repositories.transactions import TransactionRepository
from app.schemas import BulkCreateIn, BulkDeleteIn, TransactionIn, TransactionOut, TransactionTrashOut
from typing import List, Optional

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


def _to_trash_out(txn: Transaction) -> TransactionTrashOut:
    can_permanently_delete = txn.last_synced_at is None or txn.sync_status == SyncStatus.synced
    return TransactionTrashOut(
        **_to_out(txn).model_dump(),
        deleted_at=txn.deleted_at,
        can_permanently_delete=can_permanently_delete,
    )


@router.get("", response_model=list[TransactionOut])
def list_transactions(
    year: Optional[int] = None, month: Optional[int] = None,
    category: Optional[List[str]] = Query(None), category_exclude: bool = False,
    account: Optional[List[str]] = Query(None), account_exclude: bool = False,
    type: Optional[str] = None,
    date_from: Optional[date_type] = None, date_to: Optional[date_type] = None,
    search: Optional[str] = None, session: Session = Depends(get_session),
):
    repo = TransactionRepository(session)
    cat_repo = CategoryRepository(session)
    acct_repo = AccountRepository(session)
    category_ids = [c.id for c in (cat_repo.get_by_name(n) for n in category) if c] if category else None
    account_ids = [a.id for a in (acct_repo.get_by_name(n) for n in account) if a] if account else None
    rows = repo.filter(
        year=year, month=month, category_ids=category_ids, category_exclude=category_exclude,
        account_ids=account_ids, account_exclude=account_exclude,
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


@router.post("/bulk", response_model=list[TransactionOut])
def bulk_create_transactions(payload: BulkCreateIn, session: Session = Depends(get_session)):
    cat_repo, acct_repo, tx_repo = CategoryRepository(session), AccountRepository(session), TransactionRepository(session)
    created = []
    for row in payload.transactions:
        category = cat_repo.add(row.category)
        account = acct_repo.get_or_create(row.account)
        created.append(tx_repo.create(
            date=row.date, description=row.description, amount=row.amount,
            transaction_type=TransactionType(row.transaction_type), category=category, account=account,
            notes=row.notes,
        ))
    session.commit()
    return [_to_out(t) for t in created]


@router.post("/bulk_delete")
def bulk_delete_transactions(payload: BulkDeleteIn, session: Session = Depends(get_session)):
    count = TransactionRepository(session).bulk_soft_delete(payload.transaction_ids)
    session.commit()
    return {"deleted_count": count}


@router.get("/trash", response_model=list[TransactionTrashOut])
def list_trash(session: Session = Depends(get_session)):
    rows = TransactionRepository(session).list_trash()
    return [_to_trash_out(t) for t in rows]


@router.post("/bulk_restore")
def bulk_restore_transactions(payload: BulkDeleteIn, session: Session = Depends(get_session)):
    count = TransactionRepository(session).bulk_restore(payload.transaction_ids)
    session.commit()
    return {"restored_count": count}


@router.post("/bulk_permanent_delete")
def bulk_permanent_delete_transactions(payload: BulkDeleteIn, session: Session = Depends(get_session)):
    result = TransactionRepository(session).bulk_permanent_delete(payload.transaction_ids)
    session.commit()
    return result


@router.post("/{transaction_id}/restore", response_model=TransactionOut)
def restore_transaction(transaction_id: str, session: Session = Depends(get_session)):
    txn = TransactionRepository(session).restore(transaction_id)
    if not txn:
        raise HTTPException(404, "Transaction not found in trash")
    session.commit()
    return _to_out(txn)


@router.delete("/{transaction_id}/permanent")
def permanent_delete_transaction(transaction_id: str, session: Session = Depends(get_session)):
    result = TransactionRepository(session).permanent_delete(transaction_id)
    if result == "not_found":
        raise HTTPException(404, "Transaction not found")
    if result == "not_trashed":
        raise HTTPException(400, "Transaction is not in trash - delete it first")
    if result == "blocked":
        raise HTTPException(409, "This deletion hasn't synced to Google Sheets yet - wait for the next sync before permanently deleting")
    session.commit()
    return {"ok": True}


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
