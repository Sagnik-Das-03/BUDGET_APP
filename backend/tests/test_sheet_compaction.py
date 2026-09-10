from datetime import date

from app.repositories.categories import CategoryRepository
from app.sheets import mapping
from app.sync import reports as reports_mod
from app.sync.engine import compact_and_sort

SPREADSHEET_ID = "fake-id"


def _row(tid, d, amount=100.0):
    return mapping.to_row(
        transaction_id=tid, date=d, description="txn", category="Shopping", account="Primary",
        amount=amount, transaction_type="Expense", period_key=f"{d.year:04d}-{d.month:02d}",
        notes=None, deleted=False,
    )


def test_removes_fully_blank_rows(session, sheets):
    sheets.ensure_sheet(SPREADSHEET_ID, "Transactions")
    blank = ["" for _ in mapping.HEADERS]
    rows = [_row("TXN-2026-000001", date(2026, 9, 1)), blank, _row("TXN-2026-000002", date(2026, 9, 2))]
    sheets.clear_and_write(SPREADSHEET_ID, "Transactions", [mapping.HEADERS] + rows)

    result = compact_and_sort(session, sheets, SPREADSHEET_ID)

    assert result["removed_blank"] == 1
    data_rows = sheets.get_rows(SPREADSHEET_ID, "Transactions")[1:]
    assert len(data_rows) == 2
    assert blank not in data_rows


def test_sorts_rows_by_date_descending(session, sheets):
    sheets.ensure_sheet(SPREADSHEET_ID, "Transactions")
    rows = [
        _row("TXN-2026-000001", date(2026, 9, 1)),
        _row("TXN-2026-000003", date(2026, 9, 10)),
        _row("TXN-2026-000002", date(2026, 9, 5)),
    ]
    sheets.clear_and_write(SPREADSHEET_ID, "Transactions", [mapping.HEADERS] + rows)

    result = compact_and_sort(session, sheets, SPREADSHEET_ID)

    assert result["reordered"] is True
    data_rows = sheets.get_rows(SPREADSHEET_ID, "Transactions")[1:]
    ids_in_order = [r[mapping.COL["Transaction ID"]] for r in data_rows]
    assert ids_in_order == ["TXN-2026-000003", "TXN-2026-000002", "TXN-2026-000001"]


def test_keeps_a_row_with_an_unparseable_date_at_the_end_instead_of_dropping_it(session, sheets):
    sheets.ensure_sheet(SPREADSHEET_ID, "Transactions")
    bad_row = ["", "not-a-date", "Broken", "Shopping", "Primary", "100", "Expense", "", "", ""]
    rows = [_row("TXN-2026-000001", date(2026, 9, 5)), bad_row]
    sheets.clear_and_write(SPREADSHEET_ID, "Transactions", [mapping.HEADERS] + rows)

    result = compact_and_sort(session, sheets, SPREADSHEET_ID)

    data_rows = sheets.get_rows(SPREADSHEET_ID, "Transactions")[1:]
    assert len(data_rows) == 2  # kept, not dropped
    assert data_rows[-1] == bad_row  # sorted after every dated row
    assert result["removed_blank"] == 0


def test_no_op_when_already_compact_and_sorted(session, sheets):
    sheets.ensure_sheet(SPREADSHEET_ID, "Transactions")
    rows = [_row("TXN-2026-000002", date(2026, 9, 10)), _row("TXN-2026-000001", date(2026, 9, 1))]
    sheets.clear_and_write(SPREADSHEET_ID, "Transactions", [mapping.HEADERS] + rows)

    result = compact_and_sort(session, sheets, SPREADSHEET_ID)

    assert result == {"removed_blank": 0, "reordered": False}


def test_empty_sheet_is_a_no_op(session, sheets):
    sheets.ensure_sheet(SPREADSHEET_ID, "Transactions")
    sheets.clear_and_write(SPREADSHEET_ID, "Transactions", [mapping.HEADERS])

    result = compact_and_sort(session, sheets, SPREADSHEET_ID)
    assert result == {"removed_blank": 0, "reordered": False}


def test_category_color_rules_do_not_accumulate_across_repeated_calls(session, sheets):
    """Regression test: conditional format rules have no "replace all" call -
    adding the category color-tint set on every sync without first clearing
    the old set would double (then triple, ...) the rule count forever."""
    sheet_id = sheets.ensure_sheet(SPREADSHEET_ID, "Transactions")
    category_count = len(CategoryRepository(session).list(include_inactive=True))

    reports_mod.format_transactions_header(session, sheets, SPREADSHEET_ID)
    first_count = sheets.get_conditional_format_count(SPREADSHEET_ID, sheet_id)
    reports_mod.format_transactions_header(session, sheets, SPREADSHEET_ID)
    second_count = sheets.get_conditional_format_count(SPREADSHEET_ID, sheet_id)

    assert first_count == category_count
    assert second_count == category_count
