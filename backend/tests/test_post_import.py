from app.imports import post_parser

# Mirrors the real-world shape this parser was built against: an India Post
# "My Transactions" statement whose text doesn't extract in visual reading
# order - each row's Dr./Cr. marker, its (sometimes two-line-wrapped)
# remarks, and its "date date amount balance" line interleave, e.g. the
# marker, then "BY CHEQUE", then the date/amount line, then "WITHDRAWAL".
# Account/branch details below are placeholders.
STATEMENT_TEXT = "\n".join([
    "||MY TRANSACTIONS",
    "Search Criteria",
    "Transaction Date From: 01-01-2025",
    "Transactions List - SBCHQ- TESTUSER - 000000000000",
    "Natur",
    "e Of",
    "Transaction Transaction Transactio Account",
    "Value Date Trans Amount",
    "Date Remarks n Type Balance",
    "action",
    "Dr.",
    "BY CHEQUE",
    "17-06-2026 17-06-2026 20,000.00 10,790.00",
    "WITHDRAWAL",
    "Cr.",
    "11-05-2026 11-05-2026 BY CASH DEPOSIT 15,000.00 30,790.00",
    "Cr.",
    "Consolidated",
    "31-03-2026 31-03-2026 790.00 5,790.00",
    "Interest Payment",
])


def _parse(monkeypatch) -> post_parser.ParseResult:
    monkeypatch.setattr(post_parser, "_extract_text", lambda content: STATEMENT_TEXT)
    return post_parser.parse_post_pdf(b"irrelevant-bytes")


def test_parses_all_three_transactions(monkeypatch):
    result = _parse(monkeypatch)
    assert len(result.rows) == 3
    assert result.skipped_rows == 0


def test_dr_cr_map_to_expense_income(monkeypatch):
    result = _parse(monkeypatch)
    expense = [r for r in result.rows if r.transaction_type == "Expense"]
    income = [r for r in result.rows if r.transaction_type == "Income"]
    assert len(expense) == 1 and expense[0].amount == 20000.00
    assert len(income) == 2


def test_remarks_wrapped_around_the_date_line_are_joined_in_order(monkeypatch):
    result = _parse(monkeypatch)
    cheque = next(r for r in result.rows if r.amount == 20000.00)
    assert cheque.description == "BY CHEQUE WITHDRAWAL"
    interest = next(r for r in result.rows if r.amount == 790.00)
    assert interest.description == "Consolidated Interest Payment"


def test_inline_remarks_on_the_date_line_itself(monkeypatch):
    result = _parse(monkeypatch)
    deposit = next(r for r in result.rows if r.amount == 15000.00)
    assert deposit.description == "BY CASH DEPOSIT"


def test_dates_parsed_as_dd_mm_yyyy(monkeypatch):
    result = _parse(monkeypatch)
    cheque = next(r for r in result.rows if r.amount == 20000.00)
    assert cheque.date.isoformat() == "2026-06-17"


def test_preamble_and_header_lines_are_not_transactions(monkeypatch):
    result = _parse(monkeypatch)
    joined = " ".join(r.description for r in result.rows).upper()
    assert "SEARCH CRITERIA" not in joined
    assert "ACCOUNT" not in joined
