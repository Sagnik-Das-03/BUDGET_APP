"""Parses a raw Transactions-tab row into a transaction, mirroring
backend/app/sheets/mapping.py's parse_row/HEADERS/COL. Copied rather than
imported so this whole android_dashboard/ folder has zero dependency on the
backend/ package - it's meant to be copied wholesale into the Android
project later, without dragging backend/app's SQLAlchemy/Pydantic-heavy
tree along for the ride. Keep the column layout below in sync with
mapping.py's HEADERS if that ever changes."""
import re
from dataclasses import dataclass
from datetime import date as date_type, datetime
from typing import Optional

HEADERS = ["Transaction ID", "Date", "Description", "Category", "Account", "Amount",
           "Type", "Month", "Notes", "Deleted"]
COL = {name: i for i, name in enumerate(HEADERS)}

VALID_TYPES = {"Income", "Expense"}
_DATE_FORMATS = ["%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%d-%m-%Y"]
_CURRENCY_PREFIX = re.compile(r"(?:₹|rs\.?|inr)\s*", re.IGNORECASE)


@dataclass
class Txn:
    date: date_type
    category: str
    amount: float
    transaction_type: str
    deleted: bool


def _cell(raw: list[str], idx: int) -> str:
    return raw[idx].strip() if idx < len(raw) and raw[idx] is not None else ""


def _parse_date(value: str) -> Optional[date_type]:
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    return None


def _parse_amount(value: str) -> Optional[float]:
    cleaned = _CURRENCY_PREFIX.sub("", value, count=1).replace(",", "").strip()
    if not cleaned:
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def parse_row(raw: list[str]) -> Optional[Txn]:
    """None for a row that can't be parsed as a real transaction (blank,
    malformed) - silently skipped rather than raised, since a stray bad row
    shouldn't take down the whole dashboard view."""
    date_str = _cell(raw, COL["Date"])
    parsed_date = _parse_date(date_str) if date_str else None
    if parsed_date is None:
        return None

    amount_str = _cell(raw, COL["Amount"])
    parsed_amount = _parse_amount(amount_str) if amount_str else None
    if parsed_amount is None or parsed_amount <= 0:
        return None

    txn_type = _cell(raw, COL["Type"])
    if txn_type not in VALID_TYPES:
        return None

    deleted = _cell(raw, COL["Deleted"]).upper() in ("TRUE", "YES", "1")
    category = _cell(raw, COL["Category"]) or "Other"

    return Txn(date=parsed_date, category=category, amount=abs(parsed_amount),
               transaction_type=txn_type, deleted=deleted)
