from datetime import date

from app.models import TransactionType
from app.repositories.accounts import AccountRepository
from app.repositories.categories import CategoryRepository
from app.repositories.transactions import TransactionRepository


def test_category_add_and_deactivate(session):
    repo = CategoryRepository(session)
    cat = repo.add("Pets", "#123456")
    assert cat.name == "Pets"
    assert cat in repo.list()

    repo.deactivate(cat.id)
    assert cat not in repo.list()
    assert cat in repo.list(include_inactive=True)


def test_transaction_create_update_soft_delete(session):
    cat_repo, acct_repo, tx_repo = CategoryRepository(session), AccountRepository(session), TransactionRepository(session)
    category = cat_repo.get_by_name("Shopping")
    account = acct_repo.get_or_create("Primary")

    txn = tx_repo.create(
        date=date(2026, 9, 1), description="Test purchase", amount=100.0,
        transaction_type=TransactionType.expense, category=category, account=account,
    )
    assert txn.transaction_id.startswith("TXN-2026-")
    assert txn.sync_status.value == "pending"

    updated = tx_repo.update(txn.transaction_id, amount=150.0)
    assert updated.amount == 150.0
    assert updated.content_hash != txn.last_synced_hash  # never synced yet

    tx_repo.soft_delete(txn.transaction_id)
    assert tx_repo.get_by_transaction_id(txn.transaction_id).deleted_at is not None
    assert txn.transaction_id not in [t.transaction_id for t in tx_repo.filter()]


def test_delete_all_pending_hard_deletes_never_synced_rows(session):
    cat_repo, acct_repo, tx_repo = CategoryRepository(session), AccountRepository(session), TransactionRepository(session)
    category, account = cat_repo.get_by_name("Shopping"), acct_repo.get_or_create("Primary")

    txn = tx_repo.create(date=date(2026, 9, 1), description="Bad import row", amount=100.0,
                          transaction_type=TransactionType.expense, category=category, account=account)
    assert txn.last_synced_at is None  # never synced

    result = tx_repo.delete_all_pending()
    assert result == {"hard_deleted": 1, "soft_deleted": 0, "total": 1}
    # hard-deleted, not just soft-deleted - gone even from an include_deleted query
    assert tx_repo.get_by_transaction_id(txn.transaction_id) is None


def test_delete_all_pending_soft_deletes_previously_synced_rows(session):
    cat_repo, acct_repo, tx_repo = CategoryRepository(session), AccountRepository(session), TransactionRepository(session)
    category, account = cat_repo.get_by_name("Shopping"), acct_repo.get_or_create("Primary")

    txn = tx_repo.create(date=date(2026, 9, 1), description="Edited after syncing", amount=100.0,
                          transaction_type=TransactionType.expense, category=category, account=account)
    tx_repo.mark_synced(txn.transaction_id)
    tx_repo.update(txn.transaction_id, amount=150.0)  # edit -> back to pending, but now has last_synced_at
    assert txn.sync_status.value == "pending"
    assert txn.last_synced_at is not None

    result = tx_repo.delete_all_pending()
    assert result == {"hard_deleted": 0, "soft_deleted": 1, "total": 1}
    # soft-deleted so the deletion can still propagate to Sheets - row still exists, just marked deleted
    still_there = tx_repo.get_by_transaction_id(txn.transaction_id)
    assert still_there is not None
    assert still_there.deleted_at is not None


def test_delete_all_pending_ignores_synced_rows(session):
    cat_repo, acct_repo, tx_repo = CategoryRepository(session), AccountRepository(session), TransactionRepository(session)
    category, account = cat_repo.get_by_name("Shopping"), acct_repo.get_or_create("Primary")

    txn = tx_repo.create(date=date(2026, 9, 1), description="Already synced", amount=100.0,
                          transaction_type=TransactionType.expense, category=category, account=account)
    tx_repo.mark_synced(txn.transaction_id)

    result = tx_repo.delete_all_pending()
    assert result == {"hard_deleted": 0, "soft_deleted": 0, "total": 0}
    assert tx_repo.get_by_transaction_id(txn.transaction_id).deleted_at is None


def test_transaction_ids_increment_per_year(session):
    cat_repo, acct_repo, tx_repo = CategoryRepository(session), AccountRepository(session), TransactionRepository(session)
    category, account = cat_repo.get_by_name("Shopping"), acct_repo.get_or_create("Primary")

    t1 = tx_repo.create(date=date(2026, 1, 1), description="A", amount=10, transaction_type=TransactionType.expense,
                         category=category, account=account)
    t2 = tx_repo.create(date=date(2026, 1, 2), description="B", amount=20, transaction_type=TransactionType.expense,
                         category=category, account=account)
    t3 = tx_repo.create(date=date(2027, 1, 1), description="C", amount=30, transaction_type=TransactionType.expense,
                         category=category, account=account)

    assert t1.transaction_id == "TXN-2026-000001"
    assert t2.transaction_id == "TXN-2026-000002"
    assert t3.transaction_id == "TXN-2027-000001"  # new year restarts the sequence
