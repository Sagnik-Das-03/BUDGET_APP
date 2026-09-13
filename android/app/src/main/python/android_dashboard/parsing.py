"""Parses raw Sheet rows into transactions and config, mirroring
backend/app/sheets/mapping.py's parse_row/HEADERS/COL and backend/app/sync/
reports.py's regenerate_config_tab. Copied rather than imported so this
whole android_dashboard/ folder has zero dependency on the backend/
package - it's meant to be copied wholesale into the Android project later,
without dragging backend/app's SQLAlchemy/Pydantic-heavy tree along for the
ride. Keep these in sync with those two files if either ever changes shape."""
import re
from dataclasses import dataclass, field
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
    transaction_id: str
    date: date_type
    description: str
    category: str
    amount: float
    transaction_type: str
    deleted: bool
    # Not used by calculations.py (which only cares about date/category/
    # amount/type) but needed for the Transactions/filters page - account is
    # a filter facet there, notes is just displayed.
    account: str = ""
    notes: Optional[str] = None


@dataclass
class CategoryMeta:
    color: str = "#898781"
    counts_as_expense: bool = True
    is_essential: bool = False


@dataclass
class BudgetGoal:
    category: str
    period_key: Optional[str]  # None = recurring monthly default
    goal_amount: float


@dataclass
class Config:
    categories: dict[str, CategoryMeta] = field(default_factory=dict)
    budgets: list[BudgetGoal] = field(default_factory=list)
    savings_goals: list[BudgetGoal] = field(default_factory=list)  # category unused for these

    def meta(self, category: str) -> CategoryMeta:
        return self.categories.get(category, CategoryMeta())


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
    description = _cell(raw, COL["Description"])
    transaction_id = _cell(raw, COL["Transaction ID"])
    account = _cell(raw, COL["Account"]) or "Primary"
    notes = _cell(raw, COL["Notes"]) or None

    return Txn(transaction_id=transaction_id, date=parsed_date, description=description, category=category,
               amount=abs(parsed_amount), transaction_type=txn_type, deleted=deleted, account=account, notes=notes)


def parse_config(rows: list[list[str]]) -> Config:
    """Parses the "Config" tab (backend/app/sync/reports.py's
    regenerate_config_tab) - three sections in one sheet, each introduced by
    a title row then a header row. Unlike Transactions, this tab isn't a
    single fixed-width table, so this scans for each section by its title
    rather than assuming fixed row numbers - the safer approach any time a
    sheet mixes multiple tables in one tab."""
    config = Config()
    section = None
    for row in rows:
        first = row[0].strip() if row else ""
        if first == "Categories":
            section = "categories"
            continue
        if first.startswith("Budgets"):
            section = "budgets"
            continue
        if first.startswith("Savings Goal"):
            section = "savings_goal"
            continue
        if first in ("Category", "Period", "App Configuration") or not first:
            continue  # header row or blank/title row - not data

        if section == "categories" and len(row) >= 4:
            config.categories[row[0]] = CategoryMeta(
                color=row[1] or "#898781",
                counts_as_expense=row[2].strip().upper() == "TRUE",
                is_essential=row[3].strip().upper() == "TRUE",
            )
        elif section == "budgets" and len(row) >= 3:
            try:
                amount = float(row[2])
            except ValueError:
                continue
            config.budgets.append(BudgetGoal(category=row[0], period_key=row[1] or None, goal_amount=amount))
        elif section == "savings_goal" and len(row) >= 2:
            try:
                amount = float(row[1])
            except ValueError:
                continue
            config.savings_goals.append(BudgetGoal(category="", period_key=row[0] or None, goal_amount=amount))

    return config
