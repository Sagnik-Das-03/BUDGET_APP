from app.sheets import mapping
from app.sync.engine import pull

SPREADSHEET_ID = "fake-id"


def test_parse_row_rejects_invalid_date():
    parsed, error = mapping.parse_row(2, ["", "not-a-date", "Coffee", "Shopping", "Primary", "100", "Expense", "", "", ""])
    assert parsed is None
    assert "date" in error.reason.lower()


def test_parse_row_rejects_invalid_amount():
    parsed, error = mapping.parse_row(2, ["", "2026-09-01", "Coffee", "Shopping", "Primary", "abc", "Expense", "", "", ""])
    assert parsed is None
    assert "amount" in error.reason.lower()


def test_parse_row_rejects_missing_description():
    parsed, error = mapping.parse_row(2, ["", "2026-09-01", "", "Shopping", "Primary", "100", "Expense", "", "", ""])
    assert parsed is None
    assert "description" in error.reason.lower()


def test_parse_row_rejects_bad_type():
    parsed, error = mapping.parse_row(2, ["", "2026-09-01", "Coffee", "Shopping", "Primary", "100", "Purchase", "", "", ""])
    assert parsed is None
    assert "Income or Expense" in error.reason


def test_parse_row_accepts_valid_row():
    parsed, error = mapping.parse_row(2, ["TXN-2026-000001", "2026-09-01", "Coffee", "Shopping", "Primary", "100", "Expense", "2026-09", "", ""])
    assert error is None
    assert parsed.amount == 100.0
    assert parsed.transaction_id == "TXN-2026-000001"


def test_pull_reports_invalid_rows_without_importing_them(session, sheets):
    sheets.ensure_sheet(SPREADSHEET_ID, "Transactions")
    good_row = mapping.to_row(
        transaction_id="TXN-2026-000001", date=__import__("datetime").date(2026, 9, 1),
        description="Coffee", category="Shopping", account="Primary", amount=100.0,
        transaction_type="Expense", period_key="2026-09", notes=None, deleted=False,
    )
    bad_row = ["", "not-a-date", "Broken", "Shopping", "Primary", "abc", "Expense", "", "", ""]
    sheets.clear_and_write(SPREADSHEET_ID, "Transactions", [mapping.HEADERS, good_row, bad_row])

    result = pull(session, sheets, SPREADSHEET_ID, sheets.get_rows(SPREADSHEET_ID, "Transactions"))
    session.commit()

    assert result["counts"]["created"] == 1
    assert result["counts"]["errors"] == 1

    from app.repositories.transactions import TransactionRepository
    all_txns = TransactionRepository(session).filter()
    assert len(all_txns) == 1
    assert all_txns[0].description == "Coffee"
