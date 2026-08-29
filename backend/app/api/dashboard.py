from datetime import date as date_type

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.dashboard import calculations as calc
from app.db import get_session
from app.utils import period_key_for
from typing import Optional

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])

RANGE_FN = {
    "this_week": calc.range_this_week,
    "this_month": calc.range_this_month,
    "this_year": calc.range_this_year,
    "previous_year": calc.range_previous_year,
}


def _resolve_range(range_: str, date_from: Optional[date_type], date_to: Optional[date_type]):
    if range_ == "all_time":
        return None, None
    if range_ == "custom":
        return date_from, date_to
    fn = RANGE_FN.get(range_, calc.range_this_month)
    return fn()


@router.get("/summary")
def summary(range: str = "this_month", date_from: Optional[date_type] = None, date_to: Optional[date_type] = None,
            session: Session = Depends(get_session)):
    d_from, d_to = _resolve_range(range, date_from, date_to)
    return calc.totals(session, d_from, d_to)


@router.get("/by_category")
def by_category(range: str = "this_month", type: str = "Expense",
                 date_from: Optional[date_type] = None, date_to: Optional[date_type] = None,
                 session: Session = Depends(get_session)):
    d_from, d_to = _resolve_range(range, date_from, date_to)
    return calc.by_category(session, d_from, d_to, transaction_type=type)


@router.get("/trend")
def trend(granularity: str = Query("monthly", pattern="^(weekly|monthly|yearly)$"), limit: Optional[int] = None,
          session: Session = Depends(get_session)):
    if granularity == "weekly":
        return calc.weekly_trend(session, limit=limit or 12)
    if granularity == "yearly":
        return calc.yearly_trend(session)
    return calc.monthly_trend(session, limit=limit)


@router.get("/trend_for_range")
def trend_for_range(range: str = "this_year", date_from: Optional[date_type] = None,
                     date_to: Optional[date_type] = None, session: Session = Depends(get_session)):
    """Auto-picks the breakdown granularity for the given range - This Week -> daily,
    This Month -> weekly, This Year -> monthly, All Time -> yearly."""
    d_from, d_to = _resolve_range(range, date_from, date_to)
    return calc.trend_for_range(session, range, d_from, d_to)


@router.get("/monthly_breakdown")
def monthly_breakdown(session: Session = Depends(get_session)):
    return calc.monthly_breakdown(session)


@router.get("/category_drilldown")
def category_drilldown(range: str = "this_month", type: str = "Expense",
                        date_from: Optional[date_type] = None, date_to: Optional[date_type] = None,
                        session: Session = Depends(get_session)):
    d_from, d_to = _resolve_range(range, date_from, date_to)
    return calc.category_drilldown(session, d_from, d_to, transaction_type=type)


@router.get("/highlights")
def highlights(range: str = "this_month", date_from: Optional[date_type] = None,
               date_to: Optional[date_type] = None, session: Session = Depends(get_session)):
    d_from, d_to = _resolve_range(range, date_from, date_to)
    result = calc.highlights(session, d_from, d_to)
    result["comparison"] = calc.period_comparison(session, range, d_from, d_to)
    return result


@router.get("/budget_vs_actual")
def budget_vs_actual(period_key: Optional[str] = None, session: Session = Depends(get_session)):
    pk = period_key or period_key_for(date_type.today())
    return calc.budget_vs_actual(session, pk)


@router.get("/budget_alerts")
def budget_alerts(period_key: Optional[str] = None, threshold: float = 0.9, session: Session = Depends(get_session)):
    pk = period_key or period_key_for(date_type.today())
    return calc.budget_alerts(session, pk, warning_threshold=threshold)
