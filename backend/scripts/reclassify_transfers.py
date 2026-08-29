"""One-off cleanup: the legacy sheet lumped real mutual-fund SIP purchases and
family transfers ("Sent to Mom", "Sent to Sagnik", "SENT TO HOME") into the same
"SIP" category. Splits the transfers out into the new "Savings" category (per the
user's decision: historical transfers default to Savings, not Gift) while leaving
genuine SIP-fund transactions where they are. Both categories are already flagged
counts_as_expense=False, so this only affects labeling/browsing, not totals - but
it's needed for accurate per-category numbers and lets future entries choose
between Savings (pooled/still-yours) and Gift (one-way, counts as a real expense).

Safe to re-run: transactions already in "Savings" are skipped.
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db import init_db, session_scope  # noqa: E402
from app.repositories.categories import CategoryRepository  # noqa: E402
from app.repositories.transactions import TransactionRepository  # noqa: E402

TRANSFER_RE = re.compile(r"sent to", re.IGNORECASE)


def run() -> dict:
    init_db()
    moved = []
    with session_scope() as session:
        cat_repo = CategoryRepository(session)
        cat_repo.ensure_defaults()
        savings = cat_repo.get_by_name("Savings")
        tx_repo = TransactionRepository(session)

        for txn in tx_repo.filter():
            if txn.category.name == "SIP" and TRANSFER_RE.search(txn.description):
                tx_repo.update(txn.transaction_id, category=savings)
                moved.append((txn.transaction_id, txn.description, txn.amount))

    return {"moved_count": len(moved), "moved": moved}


if __name__ == "__main__":
    result = run()
    print(f"Moved {result['moved_count']} transactions from SIP -> Savings:")
    for tid, desc, amt in result["moved"]:
        print(f"  {tid}  {desc:<40}  {amt:>10.2f}")
