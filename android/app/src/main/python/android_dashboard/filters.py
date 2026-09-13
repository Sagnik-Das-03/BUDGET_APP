"""Transaction list filtering for the read-only Transactions page - mirrors
backend/app/repositories/transactions.py's TransactionRepository.filter()
semantics (same query params, same category/account include-vs-exclude and
date/search behavior) but operating on a plain list[Txn] instead of a SQL
query, since there's no SQLAlchemy session here."""
from datetime import date as date_type
from typing import Optional

from android_dashboard.parsing import Txn


def filter_transactions(
    txns: list[Txn], *,
    year: Optional[int] = None, month: Optional[int] = None,
    category: Optional[list[str]] = None, category_exclude: bool = False,
    account: Optional[list[str]] = None, account_exclude: bool = False,
    transaction_type: Optional[str] = None,
    date_from: Optional[date_type] = None, date_to: Optional[date_type] = None,
    search: Optional[str] = None,
) -> list[Txn]:
    rows = [t for t in txns if not t.deleted]

    if year and month:
        rows = [t for t in rows if t.date.year == year and t.date.month == month]
    elif year:
        rows = [t for t in rows if t.date.year == year]

    if category:
        wanted = set(category)
        rows = [t for t in rows if (t.category in wanted) != category_exclude]
    if account:
        wanted = set(account)
        rows = [t for t in rows if (t.account in wanted) != account_exclude]
    if transaction_type:
        rows = [t for t in rows if t.transaction_type == transaction_type]
    if date_from:
        rows = [t for t in rows if t.date >= date_from]
    if date_to:
        rows = [t for t in rows if t.date <= date_to]
    if search:
        needle = search.strip().lower()
        rows = [t for t in rows if needle in t.description.lower()]

    # No re-sort needed: local_db.py's load() already returns rows newest
    # first (date desc, rowid desc, matching the desktop's own ordering),
    # and every filter above is a plain list comprehension that preserves
    # relative order.
    return rows
