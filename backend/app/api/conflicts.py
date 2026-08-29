import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import get_session
from app.repositories.transactions import TransactionRepository
from app.schemas import ConflictResolution

router = APIRouter(prefix="/api/conflicts", tags=["conflicts"])


@router.get("")
def list_conflicts(session: Session = Depends(get_session)):
    rows = TransactionRepository(session).list_conflicts()
    out = []
    for t in rows:
        out.append({
            "transaction_id": t.transaction_id,
            "app_value": {
                "date": t.date.isoformat(), "description": t.description, "amount": t.amount,
                "transaction_type": t.transaction_type.value if hasattr(t.transaction_type, "value") else t.transaction_type,
                "category": t.category.name, "account": t.account.name, "notes": t.notes,
            },
            "sheet_value": json.loads(t.conflict_sheet_snapshot) if t.conflict_sheet_snapshot else None,
        })
    return out


@router.post("/{transaction_id}/resolve")
def resolve(transaction_id: str, payload: ConflictResolution, session: Session = Depends(get_session)):
    if payload.keep not in ("app", "sheets"):
        raise HTTPException(400, 'keep must be "app" or "sheets"')
    txn = TransactionRepository(session).resolve_conflict(transaction_id, payload.keep)
    if not txn:
        raise HTTPException(404, "Transaction not found")
    session.commit()
    return {"ok": True}
