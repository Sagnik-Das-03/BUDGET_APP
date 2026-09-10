from datetime import date

from app.sheets import formatting, mapping
from app.sync import reports as reports_mod
from app.sync.engine import compact_and_sort

SPREADSHEET_ID = "fake-id"


def _row(tid, d, amount=100.0):
    return mapping.to_row(
        transaction_id=tid, date=d, description="txn", category="Shopping", account="Primary",
        amount=amount, transaction_type="Expense", period_key=f"{d.year:04d}-{d.month:02d}",
        notes=None, deleted=False,
    )


def test_removes_fully_blank_rows(sheets):
    sheets.ensure_sheet(SPREADSHEET_ID, "Transactions")
    blank = ["" for _ in mapping.HEADERS]
    rows = [_row("TXN-2026-000001", date(2026, 9, 1)), blank, _row("TXN-2026-000002", date(2026, 9, 2))]
    sheets.clear_and_write(SPREADSHEET_ID, "Transactions", [mapping.HEADERS] + rows)

    result = compact_and_sort(sheets, SPREADSHEET_ID)

    assert result["removed_blank"] == 1
    data_rows = sheets.get_rows(SPREADSHEET_ID, "Transactions")[1:]
    assert len(data_rows) == 2
    assert blank not in data_rows


def test_sorts_rows_by_date_descending(sheets):
    sheets.ensure_sheet(SPREADSHEET_ID, "Transactions")
    rows = [
        _row("TXN-2026-000001", date(2026, 9, 1)),
        _row("TXN-2026-000003", date(2026, 9, 10)),
        _row("TXN-2026-000002", date(2026, 9, 5)),
    ]
    sheets.clear_and_write(SPREADSHEET_ID, "Transactions", [mapping.HEADERS] + rows)

    result = compact_and_sort(sheets, SPREADSHEET_ID)

    assert result["reordered"] is True
    data_rows = sheets.get_rows(SPREADSHEET_ID, "Transactions")[1:]
    ids_in_order = [r[mapping.COL["Transaction ID"]] for r in data_rows]
    assert ids_in_order == ["TXN-2026-000003", "TXN-2026-000002", "TXN-2026-000001"]


def test_sorts_rows_ascending_when_requested(sheets):
    sheets.ensure_sheet(SPREADSHEET_ID, "Transactions")
    rows = [
        _row("TXN-2026-000001", date(2026, 9, 1)),
        _row("TXN-2026-000003", date(2026, 9, 10)),
        _row("TXN-2026-000002", date(2026, 9, 5)),
    ]
    sheets.clear_and_write(SPREADSHEET_ID, "Transactions", [mapping.HEADERS] + rows)

    result = compact_and_sort(sheets, SPREADSHEET_ID, descending=False)

    assert result["reordered"] is True
    data_rows = sheets.get_rows(SPREADSHEET_ID, "Transactions")[1:]
    ids_in_order = [r[mapping.COL["Transaction ID"]] for r in data_rows]
    assert ids_in_order == ["TXN-2026-000001", "TXN-2026-000002", "TXN-2026-000003"]


def test_keeps_a_row_with_an_unparseable_date_at_the_end_instead_of_dropping_it(sheets):
    sheets.ensure_sheet(SPREADSHEET_ID, "Transactions")
    bad_row = ["", "not-a-date", "Broken", "Shopping", "Primary", "100", "Expense", "", "", ""]
    rows = [_row("TXN-2026-000001", date(2026, 9, 5)), bad_row]
    sheets.clear_and_write(SPREADSHEET_ID, "Transactions", [mapping.HEADERS] + rows)

    result = compact_and_sort(sheets, SPREADSHEET_ID)

    data_rows = sheets.get_rows(SPREADSHEET_ID, "Transactions")[1:]
    assert len(data_rows) == 2  # kept, not dropped
    assert data_rows[-1] == bad_row  # sorted after every dated row
    assert result["removed_blank"] == 0


def test_no_op_when_already_compact_and_sorted(sheets):
    sheets.ensure_sheet(SPREADSHEET_ID, "Transactions")
    rows = [_row("TXN-2026-000002", date(2026, 9, 10)), _row("TXN-2026-000001", date(2026, 9, 1))]
    sheets.clear_and_write(SPREADSHEET_ID, "Transactions", [mapping.HEADERS] + rows)

    result = compact_and_sort(sheets, SPREADSHEET_ID)

    assert result == {"removed_blank": 0, "reordered": False}


def test_formatting_is_reapplied_even_when_nothing_needs_reordering(sheets, monkeypatch):
    """Regression test: format_transactions_header() (header bold, column
    alignment, plain-number format, black text color) used to run only
    inside the same "if removed or reordered" branch as the content
    rewrite - so a sheet that's already compact and sorted never had its
    formatting refreshed at all, e.g. text color forced back to black."""
    sheets.ensure_sheet(SPREADSHEET_ID, "Transactions")
    rows = [_row("TXN-2026-000002", date(2026, 9, 10)), _row("TXN-2026-000001", date(2026, 9, 1))]
    sheets.clear_and_write(SPREADSHEET_ID, "Transactions", [mapping.HEADERS] + rows)

    calls = []
    monkeypatch.setattr(reports_mod, "format_transactions_header", lambda *a, **k: calls.append(1))

    result = compact_and_sort(sheets, SPREADSHEET_ID)

    assert result == {"removed_blank": 0, "reordered": False}  # confirms this is the "nothing to do" path
    assert calls == [1]


def test_clears_leftover_tint_even_when_nothing_needs_reordering(sheets):
    """Regression test: the full-tab rewrite (which used to be the only path
    that cleared conditional formats) is skipped entirely when the sheet is
    already compact and sorted - so a sheet in that state would never have
    its leftover row color-tint swept away. Clearing conditional formats
    must happen independent of whether removed/reordered ended up True."""
    sheet_id = sheets.ensure_sheet(SPREADSHEET_ID, "Transactions")
    rows = [_row("TXN-2026-000002", date(2026, 9, 10)), _row("TXN-2026-000001", date(2026, 9, 1))]
    sheets.clear_and_write(SPREADSHEET_ID, "Transactions", [mapping.HEADERS] + rows)
    sheets.batch_format(SPREADSHEET_ID, [{
        "addConditionalFormatRule": {
            "rule": {"ranges": [{"sheetId": sheet_id, "startRowIndex": 1, "endRowIndex": 5000,
                                  "startColumnIndex": 0, "endColumnIndex": len(mapping.HEADERS)}],
                      "booleanRule": {"condition": {"type": "CUSTOM_FORMULA", "values": [{"userEnteredValue": "=TRUE"}]},
                                      "format": {"backgroundColor": {"red": 1, "green": 0, "blue": 0}}}},
            "index": 0,
        }
    }])
    assert sheets.get_conditional_format_count(SPREADSHEET_ID, sheet_id) == 1

    result = compact_and_sort(sheets, SPREADSHEET_ID)

    assert result == {"removed_blank": 0, "reordered": False}  # confirms this is the "nothing to do" path
    assert sheets.get_conditional_format_count(SPREADSHEET_ID, sheet_id) == 0


def test_empty_sheet_is_a_no_op(sheets):
    sheets.ensure_sheet(SPREADSHEET_ID, "Transactions")
    sheets.clear_and_write(SPREADSHEET_ID, "Transactions", [mapping.HEADERS])

    result = compact_and_sort(sheets, SPREADSHEET_ID)
    assert result == {"removed_blank": 0, "reordered": False}


def test_cells_stay_white_no_conditional_formats_are_added(sheets):
    sheet_id = sheets.ensure_sheet(SPREADSHEET_ID, "Transactions")

    reports_mod.format_transactions_header(sheets, SPREADSHEET_ID)

    assert sheets.get_conditional_format_count(SPREADSHEET_ID, sheet_id) == 0


def test_clears_any_leftover_conditional_formatting_from_before(sheets):
    """Regression test: this tab briefly tinted rows by category via
    conditional format rules. format_transactions_header() must still sweep
    those away on an already-synced sheet, not just skip adding new ones."""
    sheet_id = sheets.ensure_sheet(SPREADSHEET_ID, "Transactions")
    sheets.batch_format(SPREADSHEET_ID, [
        formatting.column_alignment_request(sheet_id, 1, 5000, mapping.COL["Amount"], "RIGHT"),
    ])
    # Simulate a leftover tint rule directly, bypassing the (now removed) code that used to add one.
    sheets.batch_format(SPREADSHEET_ID, [{
        "addConditionalFormatRule": {
            "rule": {"ranges": [{"sheetId": sheet_id, "startRowIndex": 1, "endRowIndex": 5000,
                                  "startColumnIndex": 0, "endColumnIndex": len(mapping.HEADERS)}],
                      "booleanRule": {"condition": {"type": "CUSTOM_FORMULA", "values": [{"userEnteredValue": "=TRUE"}]},
                                      "format": {"backgroundColor": {"red": 1, "green": 0, "blue": 0}}}},
            "index": 0,
        }
    }])
    assert sheets.get_conditional_format_count(SPREADSHEET_ID, sheet_id) == 1

    reports_mod.format_transactions_header(sheets, SPREADSHEET_ID)

    assert sheets.get_conditional_format_count(SPREADSHEET_ID, sheet_id) == 0
