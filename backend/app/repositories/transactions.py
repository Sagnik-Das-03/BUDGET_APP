import json
from datetime import date as date_type, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Account, Category, SyncStatus, Transaction, TransactionSource, TransactionType
from app.utils import content_hash, next_transaction_id, period_key_for, utcnow
from typing import Optional


class TransactionRepository:
    def __init__(self, session: Session):
        self.session = session

    # ---------- lookups ----------

    def get_by_transaction_id(self, transaction_id: str) -> Optional[Transaction]:
        return self.session.scalar(select(Transaction).where(Transaction.transaction_id == transaction_id))

    def all_transaction_ids(self) -> list[str]:
        return list(self.session.scalars(select(Transaction.transaction_id)))

    def list_pending_sync(self) -> list[Transaction]:
        stmt = select(Transaction).where(
            Transaction.sync_status.in_([SyncStatus.pending, SyncStatus.error]),
            Transaction.deleted_at.is_(None),
        )
        return list(self.session.scalars(stmt))

    def list_conflicts(self) -> list[Transaction]:
        stmt = select(Transaction).where(Transaction.sync_status == SyncStatus.conflict)
        return list(self.session.scalars(stmt))

    def filter(
        self,
        *,
        year: Optional[int] = None,
        month: Optional[int] = None,
        period_key: Optional[str] = None,
        category_id: Optional[int] = None,
        account_id: Optional[int] = None,
        transaction_type: Optional[str] = None,
        date_from: Optional[date_type] = None,
        date_to: Optional[date_type] = None,
        search: Optional[str] = None,
        include_deleted: bool = False,
    ) -> list[Transaction]:
        stmt = select(Transaction)
        if not include_deleted:
            stmt = stmt.where(Transaction.deleted_at.is_(None))
        if period_key:
            stmt = stmt.where(Transaction.period_key == period_key)
        elif year and month:
            stmt = stmt.where(Transaction.period_key == f"{year:04d}-{month:02d}")
        elif year:
            stmt = stmt.where(Transaction.period_key.startswith(f"{year:04d}"))
        if category_id:
            stmt = stmt.where(Transaction.category_id == category_id)
        if account_id:
            stmt = stmt.where(Transaction.account_id == account_id)
        if transaction_type:
            stmt = stmt.where(Transaction.transaction_type == transaction_type)
        if date_from:
            stmt = stmt.where(Transaction.date >= date_from)
        if date_to:
            stmt = stmt.where(Transaction.date <= date_to)
        if search:
            like = f"%{search.strip()}%"
            stmt = stmt.where(Transaction.description.ilike(like))
        stmt = stmt.order_by(Transaction.date.desc(), Transaction.id.desc())
        return list(self.session.scalars(stmt))

    def all_active(self) -> list[Transaction]:
        return self.filter()

    # ---------- app-side writes (source="app") ----------

    def create(
        self,
        *,
        date: date_type,
        description: str,
        amount: float,
        transaction_type: TransactionType,
        category: Category,
        account: Account,
        notes: Optional[str] = None,
        source: TransactionSource = TransactionSource.app,
        transaction_id: Optional[str] = None,
    ) -> Transaction:
        tid = transaction_id or next_transaction_id(self.all_transaction_ids(), date.year)
        h = content_hash(
            date=date, description=description, amount=amount, transaction_type=transaction_type.value
            if isinstance(transaction_type, TransactionType) else transaction_type,
            category_name=category.name, account_name=account.name, notes=notes,
        )
        txn = Transaction(
            transaction_id=tid,
            date=date,
            description=description.strip(),
            amount=round(float(amount), 2),
            transaction_type=transaction_type,
            category_id=category.id,
            account_id=account.id,
            period_key=period_key_for(date),
            notes=notes,
            source=source,
            content_hash=h,
            sync_status=SyncStatus.pending,
        )
        self.session.add(txn)
        self.session.flush()
        return txn

    def update(
        self,
        transaction_id: str,
        *,
        date: Optional[date_type] = None,
        description: Optional[str] = None,
        amount: Optional[float] = None,
        transaction_type: Optional[TransactionType] = None,
        category: Optional[Category] = None,
        account: Optional[Account] = None,
        notes: Optional[str] = None,
    ) -> Optional[Transaction]:
        txn = self.get_by_transaction_id(transaction_id)
        if not txn:
            return None
        if date is not None:
            txn.date = date
            txn.period_key = period_key_for(date)
        if description is not None:
            txn.description = description.strip()
        if amount is not None:
            txn.amount = round(float(amount), 2)
        if transaction_type is not None:
            txn.transaction_type = transaction_type
        if category is not None:
            txn.category_id = category.id
        if account is not None:
            txn.account_id = account.id
        if notes is not None:
            txn.notes = notes

        txn.content_hash = content_hash(
            date=txn.date, description=txn.description, amount=txn.amount,
            transaction_type=txn.transaction_type.value if isinstance(txn.transaction_type, TransactionType) else txn.transaction_type,
            category_name=txn.category.name, account_name=txn.account.name, notes=txn.notes,
        )
        if txn.sync_status != SyncStatus.conflict:
            txn.sync_status = SyncStatus.pending
        self.session.flush()
        return txn

    def soft_delete(self, transaction_id: str) -> Optional[Transaction]:
        txn = self.get_by_transaction_id(transaction_id)
        if not txn:
            return None
        txn.deleted_at = utcnow()
        txn.sync_status = SyncStatus.pending
        self.session.flush()
        return txn

    # ---------- sync-side writes (source="google_sheets") ----------

    def upsert_from_sheet(
        self,
        *,
        transaction_id: str,
        date: date_type,
        description: str,
        amount: float,
        transaction_type: str,
        category: Category,
        account: Account,
        notes: Optional[str],
        deleted: bool,
        row_hint: Optional[int],
    ) -> tuple[Transaction, str]:
        """Reconciles one sheet row into the DB. Returns (transaction, action) where
        action is one of: created, updated, conflict, unchanged."""
        sheet_hash = content_hash(
            date=date, description=description, amount=amount, transaction_type=transaction_type,
            category_name=category.name, account_name=account.name, notes=notes,
        )
        now = utcnow()
        existing = self.get_by_transaction_id(transaction_id)

        if existing is None:
            txn = Transaction(
                transaction_id=transaction_id,
                date=date,
                description=description.strip(),
                amount=round(float(amount), 2),
                transaction_type=transaction_type,
                category_id=category.id,
                account_id=account.id,
                period_key=period_key_for(date),
                notes=notes,
                source=TransactionSource.google_sheets,
                row_hint=row_hint,
                content_hash=sheet_hash,
                last_synced_hash=sheet_hash,
                last_synced_at=now,
                sync_status=SyncStatus.synced,
                deleted_at=now if deleted else None,
            )
            self.session.add(txn)
            self.session.flush()
            return txn, "created"

        existing.row_hint = row_hint
        app_changed = existing.content_hash != (existing.last_synced_hash or "")
        sheet_changed = sheet_hash != (existing.last_synced_hash or "")
        sheet_deleted_changed = deleted != (existing.deleted_at is not None)

        if not sheet_changed and not sheet_deleted_changed:
            self.session.flush()
            return existing, "unchanged"

        if not app_changed:
            existing.date = date
            existing.description = description.strip()
            existing.amount = round(float(amount), 2)
            existing.transaction_type = transaction_type
            existing.category_id = category.id
            existing.account_id = account.id
            existing.period_key = period_key_for(date)
            existing.notes = notes
            existing.deleted_at = now if deleted else None
            existing.content_hash = sheet_hash
            existing.last_synced_hash = sheet_hash
            existing.last_synced_at = now
            existing.sync_status = SyncStatus.synced
            self.session.flush()
            return existing, "updated"

        # both sides changed since last sync
        if sheet_hash == existing.content_hash and deleted == (existing.deleted_at is not None):
            # converged on the same value independently - not a real conflict
            existing.last_synced_hash = sheet_hash
            existing.last_synced_at = now
            existing.sync_status = SyncStatus.synced
            self.session.flush()
            return existing, "updated"

        existing.sync_status = SyncStatus.conflict
        existing.conflict_sheet_snapshot = json.dumps({
            "date": date.isoformat(),
            "description": description,
            "amount": round(float(amount), 2),
            "transaction_type": transaction_type,
            "category": category.name,
            "account": account.name,
            "notes": notes,
            "deleted": deleted,
        })
        self.session.flush()
        return existing, "conflict"

    def mark_synced(self, transaction_id: str) -> None:
        txn = self.get_by_transaction_id(transaction_id)
        if not txn:
            return
        txn.last_synced_hash = txn.content_hash
        txn.last_synced_at = utcnow()
        txn.sync_status = SyncStatus.synced
        self.session.flush()

    def mark_error(self, transaction_id: str) -> None:
        txn = self.get_by_transaction_id(transaction_id)
        if txn and txn.sync_status != SyncStatus.conflict:
            txn.sync_status = SyncStatus.error
            self.session.flush()

    def resolve_conflict(self, transaction_id: str, keep: str) -> Optional[Transaction]:
        """keep = 'app' or 'sheets'."""
        txn = self.get_by_transaction_id(transaction_id)
        if not txn or txn.sync_status != SyncStatus.conflict:
            return txn
        if keep == "sheets" and txn.conflict_sheet_snapshot:
            snap = json.loads(txn.conflict_sheet_snapshot)
            cat = self.session.scalar(select(Category).where(Category.name == snap["category"]))
            acct = self.session.scalar(select(Account).where(Account.name == snap["account"]))
            txn.date = date_type.fromisoformat(snap["date"])
            txn.description = snap["description"]
            txn.amount = snap["amount"]
            txn.transaction_type = snap["transaction_type"]
            txn.notes = snap["notes"]
            txn.period_key = period_key_for(txn.date)
            txn.deleted_at = utcnow() if snap.get("deleted") else None
            if cat:
                txn.category_id = cat.id
            if acct:
                txn.account_id = acct.id
            txn.content_hash = content_hash(
                date=txn.date, description=txn.description, amount=txn.amount,
                transaction_type=txn.transaction_type, category_name=snap["category"],
                account_name=snap["account"], notes=txn.notes,
            )
        # "keep app": content_hash already reflects the app's current values - just clear the flag
        txn.conflict_sheet_snapshot = None
        txn.sync_status = SyncStatus.pending
        self.session.flush()
        return txn
