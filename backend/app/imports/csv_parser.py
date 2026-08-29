"""Parses bank-statement CSVs into candidate transactions.

Built against a real SBI email-statement export (18-row account/branch preamble,
a real header row buried inside it, multi-line quoted "Details" cells, separate
Debit/Credit columns, and a "Statement Summary" + disclaimer footer) - so this
doesn't assume a clean file. The header is located by scanning every row for
recognizable column names rather than assuming a fixed row number, and parsing
stops the moment a row's date cell fails to parse (i.e. the footer), rather than
assuming the transaction table's length. Other Indian bank exports commonly use
the same Date/Narration/Withdrawal/Deposit shape, which the header-matching
regexes also cover.
"""

import csv
import io
import re
from dataclasses import dataclass
from datetime import date as date_type, datetime
from typing import Optional

DATE_FORMATS = ["%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d", "%m/%d/%Y"]

DATE_HEADER_RE = re.compile(r"date", re.IGNORECASE)
DESC_HEADER_RE = re.compile(r"descri|detail|narration|particular", re.IGNORECASE)
DEBIT_HEADER_RE = re.compile(r"debit|withdrawal|wdl", re.IGNORECASE)
CREDIT_HEADER_RE = re.compile(r"credit|deposit", re.IGNORECASE)
AMOUNT_HEADER_RE = re.compile(r"^amount$", re.IGNORECASE)

# (pattern, category name) - matched against Expense-type descriptions only;
# Income-type rows always land in "Income" (see _guess_category). Category names
# match app.repositories.categories.DEFAULT_CATEGORIES; unmatched rows default
# to "Other" rather than inventing new category names the user didn't create.
CATEGORY_RULES: list[tuple[re.Pattern, str]] = [
    (re.compile(r"upi\s*lite", re.IGNORECASE), "Savings"),
    (re.compile(r"groww invest|\bsip\b|achdr", re.IGNORECASE), "SIP"),
    (re.compile(r"zomato", re.IGNORECASE), "Food-Order"),
    (re.compile(r"blinkit|swiggy instamart|zepto", re.IGNORECASE), "Quick-Commerce"),
    (re.compile(r"flipkart|amazon|myntra", re.IGNORECASE), "Shopping"),
    (re.compile(r"\brent\b", re.IGNORECASE), "RENT"),
    (re.compile(r"makemytrip|redbus|irctc|\buber\b|\bola\b", re.IGNORECASE), "Transport"),
    (re.compile(r"netflix|udemy|zee ente|openai|spotify|playstore|google.*mandat", re.IGNORECASE), "Subscriptions"),
    (re.compile(r"electricity|broadband|\bdth\b|gas bill|water bill", re.IGNORECASE), "Utilities"),
]


class CsvParseError(Exception):
    pass


@dataclass
class ParsedRow:
    row_key: str
    date: date_type
    description: str
    amount: float
    transaction_type: str  # "Income" | "Expense"
    category_guess: str


@dataclass
class ParseResult:
    rows: list[ParsedRow]
    skipped_rows: int
    detected_columns: dict[str, int]


def _decode(content: bytes) -> str:
    for enc in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            return content.decode(enc)
        except UnicodeDecodeError:
            continue
    return content.decode("utf-8", errors="replace")


def _try_parse_date(value: str) -> Optional[date_type]:
    value = value.strip()
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    return None


def _clean_description(raw: str) -> str:
    return re.sub(r"\s+", " ", raw).strip()


def _guess_category(description: str, transaction_type: str) -> str:
    if transaction_type == "Income":
        return "Income"
    for pattern, label in CATEGORY_RULES:
        if pattern.search(description):
            return label
    return "Other"


def _find_header(rows: list[list[str]]) -> tuple[int, dict[str, int]]:
    for i, row in enumerate(rows):
        cols: dict[str, int] = {}
        for j, cell in enumerate(row):
            cell = cell.strip()
            if not cell:
                continue
            if "date" not in cols and DATE_HEADER_RE.search(cell):
                cols["date"] = j
            elif "description" not in cols and DESC_HEADER_RE.search(cell):
                cols["description"] = j
            elif "debit" not in cols and DEBIT_HEADER_RE.search(cell):
                cols["debit"] = j
            elif "credit" not in cols and CREDIT_HEADER_RE.search(cell):
                cols["credit"] = j
            elif "amount" not in cols and AMOUNT_HEADER_RE.search(cell):
                cols["amount"] = j
        has_amount_cols = ("debit" in cols and "credit" in cols) or "amount" in cols
        if "date" in cols and "description" in cols and has_amount_cols:
            return i, cols
    raise CsvParseError(
        "Could not find a header row with Date/Description and Debit+Credit (or Amount) "
        "columns. This CSV format isn't recognized yet."
    )


def parse_csv(content: bytes) -> ParseResult:
    text = _decode(content)
    all_rows = list(csv.reader(io.StringIO(text)))
    if not all_rows:
        raise CsvParseError("The file is empty.")

    header_idx, cols = _find_header(all_rows)

    rows: list[ParsedRow] = []
    skipped = 0
    for n, row in enumerate(all_rows[header_idx + 1:]):
        if not row or all(not c.strip() for c in row):
            continue

        date_idx = cols["date"]
        date_cell = row[date_idx] if date_idx < len(row) else ""
        parsed_date = _try_parse_date(date_cell)
        if parsed_date is None:
            # First row whose date cell doesn't parse - the footer/disclaimer
            # block has begun. Stop rather than treating trailing noise as data.
            break

        desc_idx = cols["description"]
        description = _clean_description(row[desc_idx]) if desc_idx < len(row) else ""

        amount: Optional[float] = None
        txn_type: Optional[str] = None

        if "debit" in cols and "credit" in cols:
            debit_idx, credit_idx = cols["debit"], cols["credit"]
            debit_raw = row[debit_idx].strip().replace(",", "") if debit_idx < len(row) else ""
            credit_raw = row[credit_idx].strip().replace(",", "") if credit_idx < len(row) else ""
            try:
                if debit_raw:
                    amount, txn_type = float(debit_raw), "Expense"
                elif credit_raw:
                    amount, txn_type = float(credit_raw), "Income"
            except ValueError:
                pass
        elif "amount" in cols:
            amount_idx = cols["amount"]
            amount_raw = row[amount_idx].strip().replace(",", "") if amount_idx < len(row) else ""
            if amount_raw:
                try:
                    value = float(amount_raw)
                    amount, txn_type = abs(value), ("Income" if value >= 0 else "Expense")
                except ValueError:
                    pass

        if amount is None or amount <= 0 or not description:
            skipped += 1
            continue

        rows.append(ParsedRow(
            row_key=f"row-{n}",
            date=parsed_date,
            description=description,
            amount=round(amount, 2),
            transaction_type=txn_type,
            category_guess=_guess_category(description, txn_type),
        ))

    return ParseResult(rows=rows, skipped_rows=skipped, detected_columns=cols)
