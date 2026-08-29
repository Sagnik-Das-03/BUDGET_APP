"""Column <-> field mapping and row validation (spec section 6 layout, section 23
schema validation) for the single canonical `Transactions` tab."""
from dataclasses import dataclass
from datetime import date as date_type, datetime
from typing import Optional

HEADERS = ["Transaction ID", "Date", "Description", "Category", "Account", "Amount",
           "Type", "Month", "Notes", "Deleted"]
COL = {name: i for i, name in enumerate(HEADERS)}

VALID_TYPES = {"Income", "Expense"}
_DATE_FORMATS = ["%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%d-%m-%Y"]


@dataclass
class ParsedRow:
    row_number: int
    transaction_id: Optional[str]
    date: date_type
    description: str
    category: str
    account: str
    amount: float
    transaction_type: str
    notes: Optional[str]
    deleted: bool


@dataclass
class RowError:
    row_number: int
    transaction_id: Optional[str]
    reason: str


def _cell(raw: list[str], idx: int) -> str:
    return raw[idx].strip() if idx < len(raw) and raw[idx] is not None else ""


def _parse_date(value: str) -> Optional[date_type]:
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    return None


def parse_row(row_number: int, raw: list[str]) -> tuple[Optional[ParsedRow], Optional[RowError]]:
    tid = _cell(raw, COL["Transaction ID"]) or None

    date_str = _cell(raw, COL["Date"])
    parsed_date = _parse_date(date_str) if date_str else None
    if parsed_date is None:
        return None, RowError(row_number, tid, f"Invalid or missing date: {date_str!r}")

    description = _cell(raw, COL["Description"])
    if not description:
        return None, RowError(row_number, tid, "Missing description")

    amount_str = _cell(raw, COL["Amount"])
    try:
        amount = abs(float(amount_str.replace(",", ""))) if amount_str else 0.0
    except ValueError:
        return None, RowError(row_number, tid, f"Invalid amount: {amount_str!r}")
    if amount <= 0:
        return None, RowError(row_number, tid, "Amount must be a positive number")

    txn_type = _cell(raw, COL["Type"])
    if txn_type not in VALID_TYPES:
        return None, RowError(row_number, tid, f"Type must be Income or Expense, got {txn_type!r}")

    category = _cell(raw, COL["Category"]) or "Other"
    account = _cell(raw, COL["Account"]) or "Primary"
    notes = _cell(raw, COL["Notes"]) or None
    deleted = _cell(raw, COL["Deleted"]).upper() in ("TRUE", "YES", "1")

    return ParsedRow(
        row_number=row_number, transaction_id=tid, date=parsed_date, description=description,
        category=category, account=account, amount=amount, transaction_type=txn_type,
        notes=notes, deleted=deleted,
    ), None


def to_row(*, transaction_id: str, date: date_type, description: str, category: str, account: str,
           amount: float, transaction_type: str, period_key: str, notes: Optional[str], deleted: bool) -> list[str]:
    return [
        transaction_id, date.isoformat(), description, category, account,
        f"{amount:.2f}", transaction_type, period_key, notes or "", "TRUE" if deleted else "",
    ]
