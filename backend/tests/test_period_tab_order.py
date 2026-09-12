from app.sync.periods import reorder_period_tabs

SPREADSHEET_ID = "fake-id"


def _titles(sheets):
    return [s.title for s in sheets.get_sheets(SPREADSHEET_ID)]


def test_orders_dated_tabs_newest_first_by_default(sheets):
    for title in ["Transactions", "Dashboard", "2026-04", "2026-05", "2026-06",
                  "Weekly Summary", "Yearly Summary", "Monthly Breakdown", "2025-12", "2026-01"]:
        sheets.ensure_sheet(SPREADSHEET_ID, title)

    result = reorder_period_tabs(sheets, SPREADSHEET_ID)

    assert result["reordered"] is True
    assert _titles(sheets) == [
        "Transactions", "Dashboard", "2026-06", "2026-05", "2026-04", "2026-01", "2025-12",
        "Monthly Breakdown", "Weekly Summary", "Yearly Summary",
    ]


def test_orders_dated_tabs_oldest_first_when_requested(sheets):
    for title in ["Transactions", "Dashboard", "2026-06", "2026-04", "2026-05"]:
        sheets.ensure_sheet(SPREADSHEET_ID, title)

    result = reorder_period_tabs(sheets, SPREADSHEET_ID, descending=False)

    assert result["reordered"] is True
    assert _titles(sheets) == ["Transactions", "Dashboard", "2026-04", "2026-05", "2026-06"]


def test_no_op_when_already_in_order(sheets):
    for title in ["Transactions", "Dashboard", "2026-06", "2026-05", "2026-04",
                  "Monthly Breakdown", "Weekly Summary", "Yearly Summary"]:
        sheets.ensure_sheet(SPREADSHEET_ID, title)

    result = reorder_period_tabs(sheets, SPREADSHEET_ID)

    assert result == {"reordered": False}


def test_leaves_a_custom_unrecognized_tab_at_the_end(sheets):
    for title in ["Transactions", "Dashboard", "My Notes", "2026-05", "2026-04"]:
        sheets.ensure_sheet(SPREADSHEET_ID, title)

    result = reorder_period_tabs(sheets, SPREADSHEET_ID)

    assert result["reordered"] is True
    titles = _titles(sheets)
    assert titles == ["Transactions", "Dashboard", "2026-05", "2026-04", "My Notes"]
