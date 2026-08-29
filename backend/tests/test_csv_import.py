import pytest

from app.imports.csv_parser import CsvParseError, parse_csv

# Mirrors the real-world shape this parser was built against: an SBI email
# statement with an 18-row account/branch preamble before the real header,
# multi-line quoted "Details" cells, separate Debit/Credit columns, and a
# "Statement Summary" + disclaimer footer after the transactions.
SBI_STYLE_CSV = (
    '"Mr. TEST USER\n'
    'test@example.com","Some Bank",,,,\n'
    'Date of Statement  :  01-01-2026,Branch Code  :  1234,,,,\n'
    '"Clear Balance  :  1,000.00CR",Branch Name  :  TEST BRANCH,,,,\n'
    'Statement From  :  01-04-2025  to  31-03-2026,,,,,\n'
    'Date,Details,Ref No/Cheque No,Debit,Credit,Balance\n'
    '02/04/2025," DEP TFR   UPI/CR/12345/SOMEONE/SBIN/someone\n'
    ' 19/me   0097735162098 AT TEST BRANCH",,,6000.00,8546.26\n'
    '02/04/2025," WDL TFR   UPI/DR/67890/ZOMATO L/ICIC/zomato\n'
    ' /Paym   0097693162093 AT TEST BRANCH",,164.45,,4935.81\n'
    '06/04/2025," WDL TFR   UPI/DR/11111/UPILITE   \n'
    ' 0095809162097 AT TEST BRANCH",,1000.00,,3935.81\n'
    ',,,,,\n'
    'Statement Summary : 01-04-2025  To  31-03-2026,,,,,\n'
    'Brought Forward,Dr Count,Cr Count,Total Debits,Total Credits,Closing Balance\n'
    '"0.00CR",2,1,"1,164.45","6,000.00","4,835.55CR",,,,,\n'
    ',,,,,\n'
    '"Please do not share your ATM, PIN, OTP with anyone.",,,,,\n'
).encode("utf-8")


def test_parses_all_transaction_rows_and_stops_at_footer():
    result = parse_csv(SBI_STYLE_CSV)
    assert len(result.rows) == 3
    assert result.skipped_rows == 0


def test_handles_multiline_quoted_description():
    result = parse_csv(SBI_STYLE_CSV)
    zomato = next(r for r in result.rows if "ZOMATO" in r.description.upper())
    assert "\n" not in zomato.description
    assert "ZOMATO" in zomato.description


def test_debit_credit_columns_map_to_expense_income():
    result = parse_csv(SBI_STYLE_CSV)
    income = [r for r in result.rows if r.transaction_type == "Income"]
    expense = [r for r in result.rows if r.transaction_type == "Expense"]
    assert len(income) == 1
    assert income[0].amount == 6000.00
    assert len(expense) == 2


def test_income_rows_always_categorized_as_income():
    result = parse_csv(SBI_STYLE_CSV)
    income = [r for r in result.rows if r.transaction_type == "Income"][0]
    assert income.category_guess == "Income"


def test_category_guessing_matches_known_merchants():
    result = parse_csv(SBI_STYLE_CSV)
    zomato = next(r for r in result.rows if "ZOMATO" in r.description.upper())
    upilite = next(r for r in result.rows if "UPILITE" in r.description.upper())
    assert zomato.category_guess == "Food-Order"
    assert upilite.category_guess == "Savings"


def test_dates_parsed_as_dd_mm_yyyy():
    result = parse_csv(SBI_STYLE_CSV)
    assert result.rows[0].date.isoformat() == "2025-04-02"


def test_raises_when_no_header_found():
    with pytest.raises(CsvParseError):
        parse_csv(b"just,some,random,text\nwith,no,transaction,columns\n")


def test_amount_only_csv_uses_sign_for_type():
    csv_bytes = (
        "Date,Description,Amount\n"
        "01/05/2025,Salary,50000\n"
        "02/05/2025,Groceries,-1200.50\n"
    ).encode("utf-8")
    result = parse_csv(csv_bytes)
    assert len(result.rows) == 2
    salary, groceries = result.rows
    assert salary.transaction_type == "Income" and salary.amount == 50000
    assert groceries.transaction_type == "Expense" and groceries.amount == 1200.50
