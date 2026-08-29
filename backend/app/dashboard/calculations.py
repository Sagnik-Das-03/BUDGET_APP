"""All dashboard numbers come from here - pure DB queries, never a spreadsheet cell
(spec section 13). Used by both the in-app Dashboard API and sync/reports.py, so the
web UI and the generated sheet tabs can never disagree (spec feedback: 'keep everything in sync')."""
from datetime import date as date_type, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Category, Transaction, TransactionType
from app.repositories.budgets import BudgetRepository
from app.repositories.savings_goal import SavingsGoalRepository
from app.utils import day_key_for, period_key_for, week_key_for, year_key_for
from typing import Optional


def _base_query(date_from: Optional[date_type] = None, date_to: Optional[date_type] = None):
    stmt = select(Transaction).where(Transaction.deleted_at.is_(None))
    if date_from:
        stmt = stmt.where(Transaction.date >= date_from)
    if date_to:
        stmt = stmt.where(Transaction.date <= date_to)
    return stmt


def _categorize_expense(t: Transaction) -> str:
    """Buckets one expense-type transaction into 'expenses' (true consumption),
    'sip' (mutual-fund investments), or 'cash_savings' (pooled/household transfers
    and any other non-expense-counting category) - all three are mutually exclusive
    and sip+cash_savings both still count toward Net Savings/savings rate, they're
    just reported as separate line items rather than merged."""
    if t.category.counts_as_expense:
        return "expenses"
    if t.category.name == "SIP":
        return "sip"
    return "cash_savings"


def totals(session: Session, date_from: Optional[date_type] = None, date_to: Optional[date_type] = None) -> dict:
    """'expenses' is true consumption only. SIP and cash_savings (household/family
    transfers, or any other non-expense-counting category) are money that's still
    yours, reported as separate line items, but both are still excluded from
    'expenses' and therefore still counted in Net Savings and the savings rate."""
    txns = list(session.scalars(_base_query(date_from, date_to)))
    income = sum(t.amount for t in txns if t.transaction_type == TransactionType.income)
    buckets = {"expenses": 0.0, "sip": 0.0, "cash_savings": 0.0}
    for t in txns:
        if t.transaction_type == TransactionType.expense:
            buckets[_categorize_expense(t)] += t.amount
    net = income - buckets["expenses"]
    return {
        "income": round(income, 2), "expenses": round(buckets["expenses"], 2),
        "sip": round(buckets["sip"], 2), "cash_savings": round(buckets["cash_savings"], 2),
        "net": round(net, 2), "savings_rate": round(net / income, 4) if income else 0.0,
    }


def by_category(session: Session, date_from: Optional[date_type] = None, date_to: Optional[date_type] = None,
                 transaction_type: str = "Expense") -> list[dict]:
    txns = list(session.scalars(_base_query(date_from, date_to)))
    totals_map: dict[str, float] = {}
    color_map: dict[str, str] = {}
    for t in txns:
        if (t.transaction_type.value if hasattr(t.transaction_type, "value") else t.transaction_type) != transaction_type:
            continue
        name = t.category.name
        totals_map[name] = totals_map.get(name, 0.0) + t.amount
        color_map[name] = t.category.color_hex
    rows = [{"category": name, "total": round(total, 2), "color": color_map[name]}
            for name, total in totals_map.items()]
    rows.sort(key=lambda r: -r["total"])
    return rows


def _period_buckets(session: Session, key_fn, date_from: Optional[date_type], date_to: Optional[date_type]) -> dict:
    txns = list(session.scalars(_base_query(date_from, date_to)))
    buckets: dict[str, dict] = {}
    for t in txns:
        key = key_fn(t.date)
        b = buckets.setdefault(key, {"income": 0.0, "expenses": 0.0, "sip": 0.0, "cash_savings": 0.0})
        if t.transaction_type == TransactionType.income:
            b["income"] += t.amount
        else:
            b[_categorize_expense(t)] += t.amount
    return buckets


def daily_trend(session: Session, date_from: Optional[date_type] = None,
                 date_to: Optional[date_type] = None) -> list[dict]:
    buckets = _period_buckets(session, day_key_for, date_from, date_to)
    return [
        {"day": k, "income": round(buckets[k]["income"], 2), "expenses": round(buckets[k]["expenses"], 2),
         "net": round(buckets[k]["income"] - buckets[k]["expenses"], 2)}
        for k in sorted(buckets.keys())
    ]


def monthly_trend(session: Session, limit: Optional[int] = None,
                   date_from: Optional[date_type] = None, date_to: Optional[date_type] = None) -> list[dict]:
    buckets = _period_buckets(session, period_key_for, date_from, date_to)
    keys = sorted(buckets.keys())
    if limit:
        keys = keys[-limit:]
    return [
        {"period_key": k, "label": k, "income": round(buckets[k]["income"], 2),
         "expenses": round(buckets[k]["expenses"], 2),
         "net": round(buckets[k]["income"] - buckets[k]["expenses"], 2)}
        for k in keys
    ]


def trend_for_range(session: Session, range_: str, date_from: Optional[date_type],
                     date_to: Optional[date_type]) -> dict:
    """One call that picks the natural breakdown granularity for whatever range is
    selected - This Week -> daily, This Month -> weekly, This Year -> monthly,
    All Time/custom -> yearly. Powers the Dashboard's trend chart and stats."""
    if range_ == "this_week":
        return {"granularity": "daily", "rows": daily_trend(session, date_from, date_to)}
    if range_ == "this_month":
        return {"granularity": "weekly", "rows": weekly_trend(session, date_from=date_from, date_to=date_to, limit=None)}
    if range_ == "this_year":
        return {"granularity": "monthly", "rows": monthly_trend(session, date_from=date_from, date_to=date_to)}
    return {"granularity": "yearly", "rows": yearly_trend(session)}


def monthly_breakdown(session: Session) -> list[dict]:
    """Like monthly_trend(), but with SIP and cash_savings (family/household
    transfers) broken out as their own columns instead of folded into Net Savings -
    both still count toward the savings rate, they're just shown separately."""
    buckets = _period_buckets(session, period_key_for, None, None)
    out = []
    for k in sorted(buckets.keys()):
        b = buckets[k]
        net = b["income"] - b["expenses"]
        out.append({
            "period_key": k, "income": round(b["income"], 2), "expenses": round(b["expenses"], 2),
            "sip": round(b["sip"], 2), "cash_savings": round(b["cash_savings"], 2),
            "net": round(net, 2), "savings_rate": round(net / b["income"], 4) if b["income"] else 0.0,
        })
    return out


def weekly_trend(session: Session, limit: Optional[int] = 12, date_from: Optional[date_type] = None,
                  date_to: Optional[date_type] = None) -> list[dict]:
    buckets = _period_buckets(session, week_key_for, date_from, date_to)
    keys = sorted(buckets.keys())
    if limit:
        keys = keys[-limit:]
    return [
        {"week_key": k, "income": round(buckets[k]["income"], 2), "expenses": round(buckets[k]["expenses"], 2),
         "net": round(buckets[k]["income"] - buckets[k]["expenses"], 2)}
        for k in keys
    ]


def yearly_trend(session: Session) -> list[dict]:
    buckets = _period_buckets(session, year_key_for, None, None)
    keys = sorted(buckets.keys())
    return [
        {"year": k, "income": round(buckets[k]["income"], 2), "expenses": round(buckets[k]["expenses"], 2),
         "net": round(buckets[k]["income"] - buckets[k]["expenses"], 2)}
        for k in keys
    ]


def category_drilldown(session: Session, date_from: Optional[date_type] = None, date_to: Optional[date_type] = None,
                        transaction_type: str = "Expense") -> list[dict]:
    """Two-level tree (category -> its individual transactions) for the drill-down
    panel and for chart forms that want hierarchy (sunburst). Reuses by_category()'s
    totals so the two can never disagree."""
    txns = list(session.scalars(_base_query(date_from, date_to)))
    by_cat: dict[str, dict] = {}
    for t in txns:
        ttype = t.transaction_type.value if hasattr(t.transaction_type, "value") else t.transaction_type
        if ttype != transaction_type:
            continue
        node = by_cat.setdefault(t.category.name, {
            "name": t.category.name, "color": t.category.color_hex, "value": 0.0, "children": [],
        })
        node["value"] += t.amount
        node["children"].append({
            "name": t.description, "value": round(t.amount, 2), "date": t.date.isoformat(),
            "transaction_id": t.transaction_id,
        })
    result = list(by_cat.values())
    for node in result:
        node["value"] = round(node["value"], 2)
        node["children"].sort(key=lambda c: -c["value"])
    result.sort(key=lambda n: -n["value"])
    return result


def highlights(session: Session, date_from: Optional[date_type] = None, date_to: Optional[date_type] = None) -> dict:
    """Extra header metrics beyond the core KPIs: top spending category,
    transaction count, and average daily spend over the range."""
    cats = by_category(session, date_from, date_to, transaction_type="Expense")
    txns = list(session.scalars(_base_query(date_from, date_to)))
    t = totals(session, date_from, date_to)
    if date_from and date_to:
        days = (date_to - date_from).days + 1
    else:
        dates = [tx.date for tx in txns]
        days = (max(dates) - min(dates)).days + 1 if dates else 1
    return {
        "top_category": cats[0] if cats else None,
        "transaction_count": len(txns),
        "avg_daily_spend": round(t["expenses"] / days, 2) if days else 0.0,
        "days": days,
    }


def _pct_delta(current: float, previous: float) -> Optional[float]:
    if previous == 0:
        return None
    return round((current - previous) / abs(previous), 4)


def period_comparison(session: Session, range_: str, date_from: Optional[date_type],
                       date_to: Optional[date_type]) -> Optional[dict]:
    """Compares the current range's totals to the immediately preceding range of
    the same kind (previous week/month/year). None for all_time/custom, which have
    no natural 'previous period'."""
    prev_range = {
        "this_week": lambda: range_this_week(date_from - timedelta(days=7)) if date_from else None,
        "this_month": lambda: _range_previous_month(date_from) if date_from else None,
        "this_year": lambda: range_previous_year(date_from) if date_from else None,
    }.get(range_)
    if not prev_range:
        return None
    prev = prev_range()
    if not prev:
        return None
    cur = totals(session, date_from, date_to)
    prv = totals(session, *prev)
    return {
        "income_delta_pct": _pct_delta(cur["income"], prv["income"]),
        "expenses_delta_pct": _pct_delta(cur["expenses"], prv["expenses"]),
        "net_delta_pct": _pct_delta(cur["net"], prv["net"]),
        "previous_range": {"date_from": prev[0].isoformat(), "date_to": prev[1].isoformat()},
    }


def _range_previous_month(current_start: date_type) -> tuple[date_type, date_type]:
    prev_last_day = current_start - timedelta(days=1)
    return period_start(period_key_for(prev_last_day)), prev_last_day


def budget_vs_actual(session: Session, period_key: str) -> list[dict]:
    budget_repo = BudgetRepository(session)
    goals = budget_repo.for_period(period_key)
    actuals = {row["category"]: row["total"] for row in by_category(
        session, date_from=period_start(period_key), date_to=period_end(period_key), transaction_type="Expense")}
    categories = set(goals) | set(actuals)
    return sorted(
        [{"category": c, "goal": goals.get(c, 0.0), "actual": actuals.get(c, 0.0)} for c in categories],
        key=lambda r: r["category"],
    )


def savings_goal_progress(session: Session, period_key: str, warning_threshold: float = 0.7) -> Optional[dict]:
    """Progress toward a Net Savings goal for the period - unlike budget_alerts()
    (where more spend is bad), here more is good: 'met' at >=100% of goal, 'behind'
    below warning_threshold (default 70%), 'warning' in between. Returns None if no
    goal is set for this period."""
    goal_repo = SavingsGoalRepository(session)
    goal = goal_repo.for_period(period_key)
    if goal is None or goal <= 0:
        return None
    actual = totals(session, period_start(period_key), period_end(period_key))["net"]
    pct = actual / goal
    status = "met" if pct >= 1.0 else "warning" if pct >= warning_threshold else "behind"
    return {"goal": goal, "actual": round(actual, 2), "pct": round(pct, 4), "status": status}


def budget_alerts(session: Session, period_key: str, warning_threshold: float = 0.9) -> list[dict]:
    """Categories with a goal set (goal > 0) that have hit warning_threshold (default
    90%) or gone over it this period. Only categories with an actual goal are
    considered - one with no goal set can't be 'over budget'."""
    rows = budget_vs_actual(session, period_key)
    alerts = []
    for row in rows:
        if row["goal"] <= 0:
            continue
        pct = row["actual"] / row["goal"]
        if pct < warning_threshold:
            continue
        alerts.append({
            "category": row["category"], "goal": row["goal"], "actual": row["actual"],
            "pct": round(pct, 4), "status": "critical" if pct >= 1.0 else "warning",
        })
    alerts.sort(key=lambda r: -r["pct"])
    return alerts


def period_start(period_key: str) -> date_type:
    year, month = period_key.split("-")
    return date_type(int(year), int(month), 1)


def period_end(period_key: str) -> date_type:
    year, month = int(period_key.split("-")[0]), int(period_key.split("-")[1])
    if month == 12:
        return date_type(year, 12, 31)
    return date_type(year, month + 1, 1) - timedelta(days=1)


# ---------- time-range presets (spec section 15) ----------

def range_this_week(today: Optional[date_type] = None) -> tuple[date_type, date_type]:
    today = today or date_type.today()
    start = today - timedelta(days=today.weekday())
    return start, start + timedelta(days=6)


def range_this_month(today: Optional[date_type] = None) -> tuple[date_type, date_type]:
    today = today or date_type.today()
    return period_start(period_key_for(today)), period_end(period_key_for(today))


def range_this_year(today: Optional[date_type] = None) -> tuple[date_type, date_type]:
    today = today or date_type.today()
    return date_type(today.year, 1, 1), date_type(today.year, 12, 31)


def range_previous_year(today: Optional[date_type] = None) -> tuple[date_type, date_type]:
    today = today or date_type.today()
    return date_type(today.year - 1, 1, 1), date_type(today.year - 1, 12, 31)
