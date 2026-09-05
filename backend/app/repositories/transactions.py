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
        """Deliberately does NOT filter out deleted_at rows - a soft-deleted
        transaction still needs its deletion pushed to Sheets (mapping.to_row
        already encodes deleted_at as the Deleted column). Excluding them here
        was a bug: it meant no deletion ever reached Sheets, regardless of the
        sync interval - deletes stayed local-only forever."""
        stmt = select(Transaction).where(Transaction.sync_status.in_([SyncStatus.pending, SyncStatus.error]))
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
        category_ids: Optional[list[int]] = None,
        category_exclude: bool = False,
        account_ids: Optional[list[int]] = None,
        account_exclude: bool = False,
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
        if category_ids:
            cond = Transaction.category_id.in_(category_ids)
            stmt = stmt.where(~cond if category_exclude else cond)
        if account_ids:
            cond = Transaction.account_id.in_(account_ids)
            stmt = stmt.where(~cond if account_exclude else cond)
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

    def find_duplicates(self, *, date: date_type, amount: float, transaction_type: str) -> list[Transaction]:
        """Same date + type + amount (to the paisa) as an existing active transaction -
        used by CSV import to flag likely-already-entered rows before they're committed."""
        stmt = select(Transaction).where(
            Transaction.date == date,
            Transaction.transaction_type == transaction_type,
            Transaction.deleted_at.is_(None),
        )
        candidates = list(self.session.scalars(stmt))
        return [t for t in candidates if abs(t.amount - amount) < 0.01]

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
            deleted=txn.deleted_at is not None,
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
        # Recompute content_hash including the new deleted state - without this,
        # a pull() that runs before this deletion gets pushed would see an
        # unchanged content_hash, conclude "the app side didn't really change",
        # and revert deleted_at back to None from the sheet's still-stale row.
        txn.content_hash = content_hash(
            date=txn.date, description=txn.description, amount=txn.amount,
            transaction_type=txn.transaction_type.value if isinstance(txn.transaction_type, TransactionType) else txn.transaction_type,
            category_name=txn.category.name, account_name=txn.account.name, notes=txn.notes,
            deleted=True,
        )
        self.session.flush()
        return txn

    def bulk_soft_delete(self, transaction_ids: list[str]) -> int:
        """Soft-deletes each id, same as calling soft_delete() once per id.
        Returns how many ids actually matched a transaction - can be less than
        len(transaction_ids) if some no longer exist (e.g. already hard-deleted
        by delete_all_pending, or the id was simply wrong)."""
        count = 0
        for tid in transaction_ids:
            txn = self.soft_delete(tid)
            if txn is not None:
                count += 1
        return count

    def list_trash(self) -> list[Transaction]:
        stmt = select(Transaction).where(Transaction.deleted_at.is_not(None)).order_by(Transaction.deleted_at.desc())
        return list(self.session.scalars(stmt))

    def restore(self, transaction_id: str) -> Optional[Transaction]:
        txn = self.get_by_transaction_id(transaction_id)
        if not txn or txn.deleted_at is None:
            return None
        txn.deleted_at = None
        txn.content_hash = content_hash(
            date=txn.date, description=txn.description, amount=txn.amount,
            transaction_type=txn.transaction_type.value if isinstance(txn.transaction_type, TransactionType) else txn.transaction_type,
            category_name=txn.category.name, account_name=txn.account.name, notes=txn.notes,
            deleted=False,
        )
        if txn.sync_status != SyncStatus.conflict:
            txn.sync_status = SyncStatus.pending
        self.session.flush()
        return txn

    def bulk_restore(self, transaction_ids: list[str]) -> int:
        count = 0
        for tid in transaction_ids:
            if self.restore(tid) is not None:
                count += 1
        return count

    def permanent_delete(self, transaction_id: str) -> str:
        """Hard-deletes a trashed transaction. Returns 'deleted', 'not_found',
        'not_trashed', or 'blocked' (soft-deleted but its deletion hasn't
        synced to Sheets yet - hard-deleting now would drop that pending push,
        same risk delete_all_pending guards against for never-synced rows)."""
        txn = self.get_by_transaction_id(transaction_id)
        if not txn:
            return "not_found"
        if txn.deleted_at is None:
            return "not_trashed"
        if txn.last_synced_at is not None and txn.sync_status != SyncStatus.synced:
            return "blocked"
        self.session.delete(txn)
        self.session.flush()
        return "deleted"

    def bulk_permanent_delete(self, transaction_ids: list[str]) -> dict:
        deleted = blocked = not_found = 0
        for tid in transaction_ids:
            result = self.permanent_delete(tid)
            if result == "deleted":
                deleted += 1
            elif result == "blocked":
                blocked += 1
            else:
                not_found += 1
        return {"deleted": deleted, "blocked": blocked, "not_found": not_found}

    def delete_all_pending(self) -> dict:
        """Bulk-deletes every active transaction currently sitting in pending/error
        sync state - e.g. to discard a bad CSV import before it ever reaches Sheets.
        A row that was never synced (last_synced_at is None) is hard-deleted: there's
        nothing on the Sheets side to reconcile, so soft-deleting it would just queue
        a pointless "deleted" row to be appended to the sheet on the next sync. A row
        that WAS synced before (edited since, hence pending again) is soft-deleted as
        usual, so the deletion still propagates to Sheets on the next sync."""
        stmt = select(Transaction).where(
            Transaction.sync_status.in_([SyncStatus.pending, SyncStatus.error]),
            Transaction.deleted_at.is_(None),
        )
        rows = list(self.session.scalars(stmt))
        hard_deleted = 0
        soft_deleted = 0
        for txn in rows:
            if txn.last_synced_at is None:
                self.session.delete(txn)
                hard_deleted += 1
            else:
                txn.deleted_at = utcnow()
                soft_deleted += 1
        self.session.flush()
        return {"hard_deleted": hard_deleted, "soft_deleted": soft_deleted, "total": hard_deleted + soft_deleted}

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
            category_name=category.name, account_name=account.name, notes=notes, deleted=deleted,
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
        # deleted is folded into both hashes (see content_hash's docstring), so this
        # comparison alone already covers a deleted-only change on either side - no
        # separate "did deleted change" flag needed, and comparing the sheet against
        # the app's CURRENT deleted flag (rather than its last-synced one) would wrongly
        # flag a not-yet-pushed local delete as a sheet-side change on every pull.
        sheet_changed = sheet_hash != (existing.last_synced_hash or "")

        if not sheet_changed:
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
        if sheet_hash == existing.content_hash:
            # converged on the same value independently (deleted included) - not a real conflict
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
                account_name=snap["account"], notes=txn.notes, deleted=txn.deleted_at is not None,
            )
        # "keep app": content_hash already reflects the app's current values - just clear the flag
        txn.conflict_sheet_snapshot = None
        txn.sync_status = SyncStatus.pending
        self.session.flush()
        return txn
