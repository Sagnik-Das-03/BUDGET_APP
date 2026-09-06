"""One-off cleanup: flight/train/intercity-bus bookings were being lumped
into "Transport" (meant for everyday local transport - autos, cabs) or, in a
couple of cases, even miscategorized under "Subscriptions" entirely (e.g.
"Flight Ticket", "Plane Ticket"). Splits them out into the new "Travel"
category so day-to-day commuting and actual trips can be budgeted and
analyzed separately.

Only touches transactions currently in Transport or Subscriptions whose
description matches a travel keyword - "Uber"/"UBER" (everyday local rides)
deliberately does NOT match and stays under Transport.

Safe to re-run: once moved to "Travel", a transaction no longer matches
SOURCE_CATEGORIES and won't be touched again.
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db import init_db, session_scope  # noqa: E402
from app.repositories.categories import CategoryRepository  # noqa: E402
from app.repositories.transactions import TransactionRepository  # noqa: E402

TRAVEL_RE = re.compile(
    r"flight|plane ticket|irctc|makemytrip|goibibo|\byatra\b|redbus|train ticket|railway|airline",
    re.IGNORECASE,
)
SOURCE_CATEGORIES = {"Transport", "Subscriptions"}


def run() -> dict:
    init_db()
    moved = []
    with session_scope() as session:
        cat_repo = CategoryRepository(session)
        cat_repo.ensure_defaults()
        travel = cat_repo.get_by_name("Travel")
        tx_repo = TransactionRepository(session)

        for txn in tx_repo.filter():
            if txn.category.name in SOURCE_CATEGORIES and TRAVEL_RE.search(txn.description):
                moved.append((txn.transaction_id, txn.description, txn.amount, txn.category.name))
                tx_repo.update(txn.transaction_id, category=travel)

    return {"moved_count": len(moved), "moved": moved}


if __name__ == "__main__":
    result = run()
    print(f"Moved {result['moved_count']} transactions to Travel:")
    for tid, desc, amt, from_cat in result["moved"]:
        print(f"  {tid}  {desc:<70}  {amt:>10.2f}  (was {from_cat})")
