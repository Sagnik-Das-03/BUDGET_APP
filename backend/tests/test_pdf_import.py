import pytest

from app.imports import pdf_parser

# Mirrors the real-world shape this parser was built against: an Indian Bank
# statement with no drawn table gridlines, a narration that wraps across
# several lines and sometimes across a page break before the next dated row
# begins, a table header repeated on every page, and an embedded hyphen in a
# narration (ATM "TRAN DATE -(MMDD)...") that must not be mistaken for an
# empty Debits/Credits cell. All names/accounts/refs below are placeholders.
STATEMENT_TEXT = "\n".join([
    "ACCOUNT STATEMENT",
    "Account Holder Name TEST USER",
    "Account Number 1234567890",
    "Date Transaction Details Debits Credits Balance",
    "01 Jun 2026 TESTBANK/TESTUSER/UPI/111111111111/Pay - INR 1,000.00 INR 1,000.00",
    "02 Jun 2026 Card Issuance Fee INR 177.00 - INR 823.00",
    "03 Jun 2026 WDL TFR UPI/DR/22222/MERCHANT NAME INR 164.45 - INR 658.55",
    "CONTINUED ON NEXT LINE",
    "Indian Bank | | 1/2",
    "Date Transaction Details Debits Credits Balance",
    "CONTINUED AFTER PAGE BREAK",
    "04 Jun 2026 TRAN DATE -(MMDD)0604TRAN TIME - INR 5,000.00 - INR 341.45",
    "Ending Balance INR 341.45",
    "Total INR 5,341.00 INR 1,000.00",
    "Indian Bank | | 2/2",
])


def _parse(monkeypatch) -> pdf_parser.ParseResult:
    monkeypatch.setattr(pdf_parser, "_extract_text", lambda content: STATEMENT_TEXT)
    return pdf_parser.parse_pdf(b"irrelevant-bytes")


def test_parses_all_four_transactions(monkeypatch):
    result = _parse(monkeypatch)
    assert len(result.rows) == 4
    assert result.skipped_rows == 0


def test_debit_credit_cells_map_to_expense_income(monkeypatch):
    result = _parse(monkeypatch)
    income = [r for r in result.rows if r.transaction_type == "Income"]
    expense = [r for r in result.rows if r.transaction_type == "Expense"]
    assert len(income) == 1 and income[0].amount == 1000.00
    assert len(expense) == 3


def test_description_wraps_across_lines_without_date(monkeypatch):
    result = _parse(monkeypatch)
    merchant = next(r for r in result.rows if "MERCHANT NAME" in r.description.upper())
    assert "CONTINUED ON NEXT LINE" in merchant.description.upper()
    assert "\n" not in merchant.description


def test_description_continues_across_page_break(monkeypatch):
    result = _parse(monkeypatch)
    # "CONTINUED AFTER PAGE BREAK" sits between the page footer and the next
    # dated line, so it's still part of the PREVIOUS (merchant) transaction's
    # narration, not dropped and not attached to the ATM transaction that
    # follows it.
    merchant = next(r for r in result.rows if "MERCHANT NAME" in r.description.upper())
    assert "CONTINUED AFTER PAGE BREAK" in merchant.description.upper()


def test_embedded_hyphen_in_narration_not_mistaken_for_empty_cell(monkeypatch):
    result = _parse(monkeypatch)
    atm = next(r for r in result.rows if "TRAN DATE" in r.description.upper())
    assert "-(MMDD)0604TRAN TIME" in atm.description
    assert atm.amount == 5000.00


def test_dates_parsed_as_dd_mon_yyyy(monkeypatch):
    result = _parse(monkeypatch)
    assert result.rows[0].date.isoformat() == "2026-06-01"


def test_header_and_footer_lines_are_not_transactions(monkeypatch):
    result = _parse(monkeypatch)
    joined = " ".join(r.description for r in result.rows).upper()
    assert "ENDING BALANCE" not in joined
    assert "TOTAL INR" not in joined
    assert "INDIAN BANK" not in joined
