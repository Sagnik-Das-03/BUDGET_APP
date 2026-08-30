from datetime import date

from app.models import SyncStatus, TransactionType
from app.repositories.accounts import AccountRepository
from app.repositories.categories import CategoryRepository
from app.repositories.transactions import TransactionRepository
from app.sheets import mapping
from app.sync import engine as engine_mod
from app.sync.engine import pull, push, run_sync_cycle

SPREADSHEET_ID = "fake-id"


def test_pull_is_idempotent_on_repeated_calls(session, sheets):
    sheets.ensure_sheet(SPREADSHEET_ID, "Transactions")
    row = mapping.to_row(
        transaction_id="TXN-2026-000001", date=date(2026, 9, 1), description="Coffee",
        category="Shopping", account="Primary", amount=250.0, transaction_type="Expense",
        period_key="2026-09", notes=None, deleted=False,
    )
    sheets.clear_and_write(SPREADSHEET_ID, "Transactions", [mapping.HEADERS, row])

    result1 = pull(session, sheets, SPREADSHEET_ID, sheets.get_rows(SPREADSHEET_ID, "Transactions"))
    session.commit()
    result2 = pull(session, sheets, SPREADSHEET_ID, sheets.get_rows(SPREADSHEET_ID, "Transactions"))
    session.commit()

    tx_repo = TransactionRepository(session)
    all_txns = tx_repo.filter()
    assert len(all_txns) == 1
    assert result1["counts"]["created"] == 1
    assert result2["counts"]["unchanged"] == 1
    assert result2["counts"].get("created", 0) == 0


def test_push_does_not_duplicate_when_retried_after_partial_failure(session, sheets):
    """Simulates: push appended the row to Sheets successfully, then the process
    crashed before mark_synced()/commit() landed. The next cycle's pull-then-push
    must converge without appending a second copy (spec section 22)."""
    cat_repo, acct_repo, tx_repo = CategoryRepository(session), AccountRepository(session), TransactionRepository(session)
    category, account = cat_repo.get_by_name("Shopping"), acct_repo.get_or_create("Primary")

    txn = tx_repo.create(
        date=date(2026, 9, 5), description="Groceries", amount=500.0,
        transaction_type=TransactionType.expense, category=category, account=account,
    )
    session.commit()

    sheets.ensure_sheet(SPREADSHEET_ID, "Transactions")
    sheets.clear_and_write(SPREADSHEET_ID, "Transactions", [mapping.HEADERS])

    # simulate the crash: the row landed in Sheets, but mark_synced() never ran
    row = mapping.to_row(
        transaction_id=txn.transaction_id, date=txn.date, description=txn.description,
        category=category.name, account=account.name, amount=txn.amount,
        transaction_type=txn.transaction_type.value, period_key=txn.period_key, notes=None, deleted=False,
    )
    sheets.append_rows(SPREADSHEET_ID, "Transactions", [row])
    assert tx_repo.get_by_transaction_id(txn.transaction_id).sync_status == SyncStatus.pending

    # next cycle: pull reconciles (sheet already matches app content -> converges to synced)
    raw_rows = sheets.get_rows(SPREADSHEET_ID, "Transactions")
    pull_result = pull(session, sheets, SPREADSHEET_ID, raw_rows)
    session.commit()
    push_result = push(session, sheets, SPREADSHEET_ID, pull_result["id_to_row_number"])
    session.commit()

    data_rows = sheets.get_rows(SPREADSHEET_ID, "Transactions")[1:]
    matching = [r for r in data_rows if r and r[0] == txn.transaction_id]
    assert len(matching) == 1, "transaction must appear exactly once in the sheet, not duplicated"
    assert tx_repo.get_by_transaction_id(txn.transaction_id).sync_status == SyncStatus.synced
    assert push_result["appended"] == 0


def test_run_sync_cycle_skips_report_regeneration_when_nothing_changed(session, sheets, monkeypatch):
    """Regression test: report regeneration used to fire on every cycle regardless
    of whether anything changed, which is what was blowing through the Sheets API's
    60-writes-per-minute-per-user quota on quiet cycles with nothing to report."""
    calls = []
    monkeypatch.setattr(engine_mod.reports_mod, "regenerate_all", lambda *a, **k: calls.append(1))

    run_sync_cycle(session, sheets, SPREADSHEET_ID)  # empty sheet, empty DB - nothing to sync

    assert calls == []


def test_run_sync_cycle_runs_report_regeneration_when_something_changed(session, sheets, monkeypatch):
    calls = []
    monkeypatch.setattr(engine_mod.reports_mod, "regenerate_all", lambda *a, **k: calls.append(1) or {"stub": True})

    cat_repo, acct_repo, tx_repo = CategoryRepository(session), AccountRepository(session), TransactionRepository(session)
    category, account = cat_repo.get_by_name("Shopping"), acct_repo.get_or_create("Primary")
    tx_repo.create(date=date(2026, 9, 1), description="Coffee", amount=100.0,
                    transaction_type=TransactionType.expense, category=category, account=account)
    session.commit()

    run_sync_cycle(session, sheets, SPREADSHEET_ID)  # the new pending transaction should get pushed

    assert calls == [1]


def test_deleting_an_already_synced_transaction_pushes_the_deletion(session, sheets):
    """Regression test: list_pending_sync() used to filter out deleted_at rows,
    which meant a deletion never reached Sheets no matter how many sync cycles
    ran - it stayed local-only forever. Deleting a transaction, then syncing,
    must flip its row's Deleted column to TRUE in the sheet."""
    cat_repo, acct_repo, tx_repo = CategoryRepository(session), AccountRepository(session), TransactionRepository(session)
    category, account = cat_repo.get_by_name("Shopping"), acct_repo.get_or_create("Primary")

    txn = tx_repo.create(date=date(2026, 9, 10), description="Subscription", amount=199.0,
                          transaction_type=TransactionType.expense, category=category, account=account)
    session.commit()

    sheets.ensure_sheet(SPREADSHEET_ID, "Transactions")
    sheets.clear_and_write(SPREADSHEET_ID, "Transactions", [mapping.HEADERS])

    # first sync cycle: pushes the new transaction, gets it onto the sheet as synced
    raw_rows = sheets.get_rows(SPREADSHEET_ID, "Transactions")
    pull_result = pull(session, sheets, SPREADSHEET_ID, raw_rows)
    session.commit()
    push(session, sheets, SPREADSHEET_ID, pull_result["id_to_row_number"])
    session.commit()
    assert tx_repo.get_by_transaction_id(txn.transaction_id).sync_status == SyncStatus.synced

    # user deletes it in the app
    tx_repo.soft_delete(txn.transaction_id)
    session.commit()
    assert tx_repo.get_by_transaction_id(txn.transaction_id).sync_status == SyncStatus.pending

    # next sync cycle: the deletion must reach the sheet
    raw_rows = sheets.get_rows(SPREADSHEET_ID, "Transactions")
    pull_result = pull(session, sheets, SPREADSHEET_ID, raw_rows)
    session.commit()
    push_result = push(session, sheets, SPREADSHEET_ID, pull_result["id_to_row_number"])
    session.commit()

    assert push_result["updated"] == 1
    data_rows = sheets.get_rows(SPREADSHEET_ID, "Transactions")[1:]
    row = next(r for r in data_rows if r and r[0] == txn.transaction_id)
    assert row[mapping.COL["Deleted"]] == "TRUE"
    assert tx_repo.get_by_transaction_id(txn.transaction_id).sync_status == SyncStatus.synced
