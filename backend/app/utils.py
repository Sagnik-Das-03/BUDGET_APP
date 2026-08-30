import hashlib
import re
from datetime import date as date_type, datetime, timezone
from typing import Optional


def utcnow() -> datetime:
    """Naive UTC timestamp (matches the naive DateTime columns/server_default=func.now())
    without datetime.utcnow(), which is deprecated as of Python 3.12."""
    return datetime.now(timezone.utc).replace(tzinfo=None)

TXN_ID_RE = re.compile(r"^TXN-(\d{4})-(\d{6})$")


def content_hash(*, date: date_type, description: str, amount: float, transaction_type: str,
                  category_name: str, account_name: str, notes: Optional[str], deleted: bool = False) -> str:
    """Hash of the fields that are mirrored into the sheet - used to detect real changes
    on either side without caring about internal-only fields (row_hint, timestamps, etc.).
    Includes `deleted` so a delete-only change (nothing else about the transaction differs)
    still causes content_hash to diverge from last_synced_hash - without it, the sync
    engine's "did the app side actually change" check couldn't see a plain deletion, and a
    pull() landing before the deletion was pushed would silently revert it (deleted_at
    reset to None) because the sheet's stale "not deleted" state looked unchanged."""
    parts = [
        date.isoformat(),
        (description or "").strip(),
        f"{round(float(amount), 2):.2f}",
        transaction_type,
        category_name,
        account_name,
        (notes or "").strip(),
        "DELETED" if deleted else "",
    ]
    payload = "|".join(parts).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def period_key_for(d: date_type) -> str:
    return f"{d.year:04d}-{d.month:02d}"


def month_label_for(period_key: str) -> str:
    year, month = period_key.split("-")
    month_names = ["January", "February", "March", "April", "May", "June",
                   "July", "August", "September", "October", "November", "December"]
    return f"{month_names[int(month) - 1]} {year}"


def day_key_for(d: date_type) -> str:
    return d.isoformat()


def week_key_for(d: date_type) -> str:
    iso = d.isocalendar()
    return f"{iso[0]:04d}-W{iso[1]:02d}"


def year_key_for(d: date_type) -> str:
    return f"{d.year:04d}"


def next_transaction_id(existing_ids: list[str], year: int) -> str:
    """existing_ids: all transaction_id values currently in the DB (any year)."""
    max_seq = 0
    prefix = f"TXN-{year:04d}-"
    for tid in existing_ids:
        m = TXN_ID_RE.match(tid)
        if m and tid.startswith(prefix):
            max_seq = max(max_seq, int(m.group(2)))
    return f"{prefix}{max_seq + 1:06d}"


def is_valid_transaction_id(value: str) -> bool:
    return bool(TXN_ID_RE.match(value or ""))
