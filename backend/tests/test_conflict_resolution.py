from datetime import date

from app.models import SyncStatus, TransactionType
from app.repositories.accounts import AccountRepository
from app.repositories.categories import CategoryRepository
from app.repositories.transactions import TransactionRepository


def _make_synced_transaction(session):
    cat_repo, acct_repo, tx_repo = CategoryRepository(session), AccountRepository(session), TransactionRepository(session)
    category, account = cat_repo.get_by_name("Shopping"), acct_repo.get_or_create("Primary")
    txn = tx_repo.create(
        date=date(2026, 9, 10), description="Widget", amount=100.0,
        transaction_type=TransactionType.expense, category=category, account=account,
    )
    tx_repo.mark_synced(txn.transaction_id)  # establish a baseline as if a prior sync already succeeded
    session.commit()
    return txn, category, account


def test_both_sides_changing_to_different_values_is_flagged_as_conflict(session):
    txn, category, account = _make_synced_transaction(session)
    tx_repo = TransactionRepository(session)

    tx_repo.update(txn.transaction_id, amount=999.0)  # app-side edit since last sync
    session.commit()

    _, action = tx_repo.upsert_from_sheet(
        transaction_id=txn.transaction_id, date=txn.date, description=txn.description,
        amount=888.0, transaction_type="Expense", category=category, account=account,
        notes=None, deleted=False, row_hint=2,
    )
    session.commit()

    assert action == "conflict"
    reloaded = tx_repo.get_by_transaction_id(txn.transaction_id)
    assert reloaded.sync_status == SyncStatus.conflict
    assert reloaded.amount == 999.0  # app value untouched until a resolution is chosen
    assert reloaded.conflict_sheet_snapshot is not None


def test_both_sides_changing_to_the_same_value_is_not_a_conflict(session):
    txn, category, account = _make_synced_transaction(session)
    tx_repo = TransactionRepository(session)

    tx_repo.update(txn.transaction_id, amount=250.0)
    session.commit()

    _, action = tx_repo.upsert_from_sheet(
        transaction_id=txn.transaction_id, date=txn.date, description=txn.description,
        amount=250.0, transaction_type="Expense", category=category, account=account,
        notes=None, deleted=False, row_hint=2,
    )
    assert action == "updated"
    assert tx_repo.get_by_transaction_id(txn.transaction_id).sync_status == SyncStatus.synced


def test_resolve_conflict_keep_app(session):
    txn, category, account = _make_synced_transaction(session)
    tx_repo = TransactionRepository(session)
    tx_repo.update(txn.transaction_id, amount=999.0)
    session.commit()
    tx_repo.upsert_from_sheet(
        transaction_id=txn.transaction_id, date=txn.date, description=txn.description,
        amount=888.0, transaction_type="Expense", category=category, account=account,
        notes=None, deleted=False, row_hint=2,
    )
    session.commit()

    resolved = tx_repo.resolve_conflict(txn.transaction_id, "app")
    assert resolved.sync_status == SyncStatus.pending
    assert resolved.amount == 999.0
    assert resolved.conflict_sheet_snapshot is None


def test_resolve_conflict_keep_sheets(session):
    txn, category, account = _make_synced_transaction(session)
    tx_repo = TransactionRepository(session)
    tx_repo.update(txn.transaction_id, amount=999.0)
    session.commit()
    tx_repo.upsert_from_sheet(
        transaction_id=txn.transaction_id, date=txn.date, description=txn.description,
        amount=888.0, transaction_type="Expense", category=category, account=account,
        notes=None, deleted=False, row_hint=2,
    )
    session.commit()

    resolved = tx_repo.resolve_conflict(txn.transaction_id, "sheets")
    assert resolved.sync_status == SyncStatus.pending
    assert resolved.amount == 888.0
    assert resolved.conflict_sheet_snapshot is None


def test_resolve_conflict_keep_both(session):
    txn, category, account = _make_synced_transaction(session)
    tx_repo = TransactionRepository(session)
    tx_repo.update(txn.transaction_id, amount=999.0)
    session.commit()
    tx_repo.upsert_from_sheet(
        transaction_id=txn.transaction_id, date=txn.date, description=txn.description,
        amount=888.0, transaction_type="Expense", category=category, account=account,
        notes=None, deleted=False, row_hint=2,
    )
    session.commit()

    before_ids = set(tx_repo.all_transaction_ids())
    resolved = tx_repo.resolve_conflict(txn.transaction_id, "both")
    session.commit()

    # Original transaction keeps the app's value, same as "keep app".
    assert resolved.sync_status == SyncStatus.pending
    assert resolved.amount == 999.0
    assert resolved.conflict_sheet_snapshot is None

    # A new transaction was created carrying the sheet's value.
    new_ids = set(tx_repo.all_transaction_ids()) - before_ids
    assert len(new_ids) == 1
    duplicate = tx_repo.get_by_transaction_id(new_ids.pop())
    assert duplicate.amount == 888.0
    assert duplicate.description == txn.description
    assert duplicate.category_id == category.id
    assert duplicate.account_id == account.id


def test_resolve_conflict_keep_both_skips_duplicate_when_sheet_side_deleted(session):
    txn, category, account = _make_synced_transaction(session)
    tx_repo = TransactionRepository(session)
    tx_repo.update(txn.transaction_id, amount=999.0)
    session.commit()
    tx_repo.upsert_from_sheet(
        transaction_id=txn.transaction_id, date=txn.date, description=txn.description,
        amount=txn.amount, transaction_type="Expense", category=category, account=account,
        notes=None, deleted=True, row_hint=2,
    )
    session.commit()

    before_ids = set(tx_repo.all_transaction_ids())
    resolved = tx_repo.resolve_conflict(txn.transaction_id, "both")
    session.commit()

    assert resolved.amount == 999.0
    assert set(tx_repo.all_transaction_ids()) == before_ids  # nothing duplicated
