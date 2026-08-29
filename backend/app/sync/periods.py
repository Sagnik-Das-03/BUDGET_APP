import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import MonthlyPeriod, Transaction
from app.sheets.adapter import GoogleSheetsService
from app.utils import month_label_for
from typing import Optional

PERIOD_RE = re.compile(r"^\d{4}-\d{2}$")

RESERVED_SHEET_NAMES = {"Transactions", "Dashboard", "Monthly Breakdown", "Weekly Summary", "Yearly Summary"}


def ensure_period(session: Session, period_key: str, *, discovered_from_sheet: bool = False,
                   sheet_gid: Optional[int] = None) -> MonthlyPeriod:
    existing = session.scalar(select(MonthlyPeriod).where(MonthlyPeriod.period_key == period_key))
    if existing:
        if sheet_gid is not None:
            existing.sheet_gid = sheet_gid
        return existing
    period = MonthlyPeriod(
        period_key=period_key, label=month_label_for(period_key),
        discovered_from_sheet=discovered_from_sheet, sheet_gid=sheet_gid,
    )
    session.add(period)
    session.flush()
    return period


def ensure_periods_for_transactions(session: Session) -> list[str]:
    """Registers a MonthlyPeriod for every period_key present in the transaction data
    (any year, past or future) - satisfies 'works indefinitely across years' (spec section 7)."""
    period_keys = sorted({p for p, in session.execute(select(Transaction.period_key).distinct())})
    for pk in period_keys:
        ensure_period(session, pk)
    return period_keys


def discover_sheet_periods(session: Session, sheets: GoogleSheetsService, spreadsheet_id: str) -> list[str]:
    """Registers any YYYY-MM tab a user created by hand directly in Sheets, so the app
    doesn't try to (re-)create a duplicate for it (spec section 8)."""
    discovered = []
    for sheet_info in sheets.get_sheets(spreadsheet_id):
        title = sheet_info.title
        if title in RESERVED_SHEET_NAMES or not PERIOD_RE.match(title):
            continue
        existing = session.scalar(select(MonthlyPeriod).where(MonthlyPeriod.period_key == title))
        if not existing:
            ensure_period(session, title, discovered_from_sheet=True, sheet_gid=sheet_info.sheet_id)
            discovered.append(title)
        elif existing.sheet_gid != sheet_info.sheet_id:
            existing.sheet_gid = sheet_info.sheet_id
    return discovered
