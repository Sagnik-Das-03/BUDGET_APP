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


def _previous_range_bounds(range_: str, date_from: Optional[date_type]) -> Optional[tuple[date_type, date_type]]:
    """The immediately preceding range of the same kind (previous week/month/year) -
    shared by period_comparison() and category_trends(). None for all_time/custom,
    which have no natural 'previous period' to compare against."""
    if not date_from:
        return None
    fn = {
        "this_week": lambda: range_this_week(date_from - timedelta(days=7)),
        "this_month": lambda: _range_previous_month(date_from),
        "this_year": lambda: range_previous_year(date_from),
    }.get(range_)
    return fn() if fn else None


def period_comparison(session: Session, range_: str, date_from: Optional[date_type],
                       date_to: Optional[date_type]) -> Optional[dict]:
    """Compares the current range's totals to the immediately preceding range of
    the same kind (previous week/month/year). None for all_time/custom, which have
    no natural 'previous period'."""
    prev = _previous_range_bounds(range_, date_from)
    if not prev:
        return None
    cur = totals(session, date_from, date_to)
    prv = totals(session, *prev)
    return {
        "income_delta_pct": _pct_delta(cur["income"], prv["income"]),
        "expenses_delta_pct": _pct_delta(cur["expenses"], prv["expenses"]),
        # Net can be zero or negative (a losing week/month is a real, valid
        # state) unlike Income/Expenses which are almost always comfortably
        # positive - a PERCENTAGE change against a near-zero or negative
        # baseline blows up into a meaningless number (e.g. a previous net of
        # -Rs 1,000 swinging to +Rs 58,000 isn't a real "5,939% increase",
        # it's a swing from a loss to a gain). net_delta_abs (a plain rupee
        # difference) is well-defined no matter the sign of either side, so
        # the frontend uses that instead of net_delta_pct for this one.
        "net_delta_pct": _pct_delta(cur["net"], prv["net"]),
        "net_delta_abs": round(cur["net"] - prv["net"], 2),
        "previous_range": {"date_from": prev[0].isoformat(), "date_to": prev[1].isoformat()},
    }


def category_trends(session: Session, range_: str, date_from: Optional[date_type],
                     date_to: Optional[date_type], transaction_type: str = "Expense") -> list[dict]:
    """Per-category version of period_comparison() - how much more/less each
    category moved vs. the immediately preceding range of the same kind.
    Empty for all_time/custom, which have no natural 'previous period'.
    Sorted by absolute rupee swing (not percentage) so a category that went
    from Rs 50 to Rs 150 (a huge 200% jump, but trivial in real money) doesn't
    outrank one that went from Rs 20,000 to Rs 24,000 (a modest 20% jump that
    actually moved the budget).

    For Expense trends, categories with counts_as_expense=False (SIP, Savings)
    are excluded entirely - the same distinction the Expenses KPI, essential/
    discretionary split, and anomaly detection already draw. A bigger SIP
    contribution isn't "spending moving in the wrong direction" - it doesn't
    belong in a spending-trends comparison at all."""
    prev = _previous_range_bounds(range_, date_from)
    if not prev:
        return []
    cur_rows = by_category(session, date_from, date_to, transaction_type=transaction_type)
    prv_rows = by_category(session, *prev, transaction_type=transaction_type)
    if transaction_type == "Expense":
        real_expense_names = {
            c.name for c in session.scalars(select(Category).where(Category.counts_as_expense.is_(True)))
        }
        cur_rows = [r for r in cur_rows if r["category"] in real_expense_names]
        prv_rows = [r for r in prv_rows if r["category"] in real_expense_names]
    cur = {r["category"]: r["total"] for r in cur_rows}
    prv = {r["category"]: r["total"] for r in prv_rows}
    rows = []
    for name in set(cur) | set(prv):
        c, p = cur.get(name, 0.0), prv.get(name, 0.0)
        rows.append({
            "category": name, "current": round(c, 2), "previous": round(p, 2),
            "delta_abs": round(c - p, 2), "delta_pct": _pct_delta(c, p),
        })
    rows.sort(key=lambda r: -abs(r["delta_abs"]))
    return rows


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


def detect_anomalies(session: Session, date_from: Optional[date_type], date_to: Optional[date_type],
                      min_multiple: float = 2.0, min_absolute_gap: float = 100.0,
                      min_history: int = 3, limit: int = 5) -> list[dict]:
    """Flags individual expense transactions in [date_from, date_to] that are
    unusually large relative to that category's OWN historical average
    (computed only from transactions strictly before date_from, so a category
    can't inflate its own baseline by including the very spike being
    flagged). Deliberately a plain statistical heuristic, not a model call -
    this is meant to render passively on every Dashboard load, and a local
    LLM call is far too slow (seconds to a minute) for that. A category needs
    at least min_history prior transactions before it gets a baseline at
    all, so a category with one or two data points can't flag everything in
    it as "unusual" relative to itself.

    Categories with counts_as_expense=False (SIP, Savings) are excluded
    entirely - those are money that's still yours (invested or saved), the
    same distinction _categorize_expense() draws for the KPIs, so a bigger
    SIP contribution is good news, not something to red-flag as unusual
    overspending."""
    history_stmt = select(Transaction).where(
        Transaction.deleted_at.is_(None), Transaction.transaction_type == TransactionType.expense,
    )
    if date_from:
        history_stmt = history_stmt.where(Transaction.date < date_from)
    amounts_by_category: dict[str, list[float]] = {}
    for t in session.scalars(history_stmt):
        if not t.category.counts_as_expense:
            continue
        amounts_by_category.setdefault(t.category.name, []).append(t.amount)
    baselines = {
        name: sum(amounts) / len(amounts)
        for name, amounts in amounts_by_category.items() if len(amounts) >= min_history
    }

    anomalies = []
    for t in session.scalars(_base_query(date_from, date_to)):
        if t.transaction_type != TransactionType.expense or not t.category.counts_as_expense:
            continue
        baseline = baselines.get(t.category.name)
        if not baseline or baseline <= 0:
            continue
        multiple = t.amount / baseline
        if multiple >= min_multiple and (t.amount - baseline) >= min_absolute_gap:
            anomalies.append({
                "transaction_id": t.transaction_id, "date": t.date.isoformat(), "description": t.description,
                "category": t.category.name, "amount": round(t.amount, 2),
                "category_avg": round(baseline, 2), "multiple": round(multiple, 2),
            })
    anomalies.sort(key=lambda a: -a["multiple"])
    return anomalies[:limit]


def category_volatility(session: Session, months: int = 6, min_months: int = 3) -> list[dict]:
    """Classifies each expense category as stable/moderate/volatile by the
    coefficient of variation (stdev / mean) of its monthly totals over the
    last `months` FULLY-ELAPSED calendar months (the current, in-progress
    month is excluded so its necessarily-partial total doesn't read as a
    sudden drop). A category needs at least `min_months` of those months with
    any spending at all before it's judged - one or two data points can't
    say anything about consistency. A low CoV (stable) is a good candidate
    for a tight fixed budget goal; a high CoV (volatile) swings too much
    month to month for a single number to mean much - it needs a bigger
    cushion or shouldn't be budgeted as a fixed amount at all."""
    this_month_start = period_start(period_key_for(date_type.today()))
    window_start = this_month_start
    for _ in range(months):
        window_start = period_start(period_key_for(window_start - timedelta(days=1)))
    window_end = this_month_start - timedelta(days=1)

    per_cat_month: dict[str, dict[str, float]] = {}
    for t in session.scalars(_base_query(window_start, window_end)):
        if t.transaction_type != TransactionType.expense or not t.category.counts_as_expense:
            continue
        bucket = per_cat_month.setdefault(t.category.name, {})
        pk = period_key_for(t.date)
        bucket[pk] = bucket.get(pk, 0.0) + t.amount

    results = []
    for cat, month_totals in per_cat_month.items():
        values = list(month_totals.values())
        if len(values) < min_months:
            continue
        mean = sum(values) / len(values)
        variance = sum((v - mean) ** 2 for v in values) / len(values)
        stdev = variance ** 0.5
        cov = stdev / mean if mean else 0.0
        status = "volatile" if cov >= 0.5 else "moderate" if cov >= 0.2 else "stable"
        results.append({
            "category": cat, "months_observed": len(values), "avg_monthly": round(mean, 2),
            "stdev": round(stdev, 2), "coefficient_of_variation": round(cov, 4), "status": status,
        })
    results.sort(key=lambda r: -r["coefficient_of_variation"])
    return results


_DAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def spending_pattern(session: Session, date_from: Optional[date_type] = None,
                      date_to: Optional[date_type] = None) -> dict:
    """Where expense spending concentrates within a week (which day of the
    week) and within a month (which third of it) - a purely descriptive
    breakdown, no threshold or judgment involved. Can surface a 'weekend
    spender' pattern or spending naturally front-loaded early in the month
    (rent/bills on the 1st) that a category-only view wouldn't show."""
    by_dow = {name: 0.0 for name in _DAY_NAMES}
    by_third = {"1st (days 1-10)": 0.0, "2nd (days 11-20)": 0.0, "3rd (days 21+)": 0.0}
    total = 0.0
    for t in session.scalars(_base_query(date_from, date_to)):
        if t.transaction_type != TransactionType.expense:
            continue
        total += t.amount
        by_dow[_DAY_NAMES[t.date.weekday()]] += t.amount
        third_key = "1st (days 1-10)" if t.date.day <= 10 else "2nd (days 11-20)" if t.date.day <= 20 else "3rd (days 21+)"
        by_third[third_key] += t.amount

    return {
        "by_day_of_week": [
            {"day": d, "total": round(by_dow[d], 2), "pct": round(by_dow[d] / total, 4) if total else 0.0}
            for d in _DAY_NAMES
        ],
        "by_month_third": [
            {"label": k, "total": round(v, 2), "pct": round(v / total, 4) if total else 0.0}
            for k, v in by_third.items()
        ],
    }


def essential_vs_discretionary(session: Session, date_from: Optional[date_type] = None,
                                date_to: Optional[date_type] = None) -> dict:
    """Splits real expense spending (counts_as_expense=True categories only -
    SIP/Savings are excluded the same way the Expenses KPI already excludes
    them) into essential (Category.is_essential=True - Rent/Utilities/etc by
    default) vs discretionary. is_essential is a user-editable judgment call
    (see Settings, and DEFAULT_CATEGORIES' seeded starting guess), not
    something this function determines on its own. Also breaks each side down
    by category (sorted by amount) so the UI can show which categories
    actually make up "essential" vs "discretionary", not just the two totals."""
    essential_by_cat: dict[str, float] = {}
    discretionary_by_cat: dict[str, float] = {}
    for t in session.scalars(_base_query(date_from, date_to)):
        if t.transaction_type != TransactionType.expense or not t.category.counts_as_expense:
            continue
        bucket = essential_by_cat if t.category.is_essential else discretionary_by_cat
        bucket[t.category.name] = bucket.get(t.category.name, 0.0) + t.amount

    essential = sum(essential_by_cat.values())
    discretionary = sum(discretionary_by_cat.values())
    total = essential + discretionary

    def _rows(by_cat: dict[str, float]) -> list[dict]:
        return sorted(
            ({"category": name, "total": round(v, 2)} for name, v in by_cat.items()),
            key=lambda r: -r["total"],
        )

    return {
        "essential": round(essential, 2), "discretionary": round(discretionary, 2),
        "essential_pct": round(essential / total, 4) if total else 0.0,
        "discretionary_pct": round(discretionary / total, 4) if total else 0.0,
        "essential_categories": _rows(essential_by_cat),
        "discretionary_categories": _rows(discretionary_by_cat),
    }


def savings_streak(session: Session, as_of: Optional[date_type] = None) -> dict:
    """How many consecutive FULLY-ELAPSED months (most recent first, the
    current in-progress month excluded so a half-finished month doesn't
    falsely end a streak) have had a positive net - built on the same
    monthly_breakdown() data as the Dashboard's monthly savings-rate trend.
    Also reports the longest streak on record, for context on whether the
    current run is actually notable."""
    current_period_key = period_key_for(as_of or date_type.today())
    rows = sorted(
        (r for r in monthly_breakdown(session) if r["period_key"] < current_period_key),
        key=lambda r: r["period_key"],
    )

    current_streak = 0
    for r in reversed(rows):
        if r["net"] <= 0:
            break
        current_streak += 1

    best_streak = running = 0
    for r in rows:
        running = running + 1 if r["net"] > 0 else 0
        best_streak = max(best_streak, running)

    return {
        "current_streak_months": current_streak,
        "best_streak_months": best_streak,
        "months_observed": len(rows),
    }


def spend_concentration(session: Session, date_from: Optional[date_type] = None,
                         date_to: Optional[date_type] = None, top_n: int = 3) -> dict:
    """What share of real expense spending came from just the top_n largest
    single transactions in the period - flags whether a big period total is
    concentrated in a few big-ticket purchases (a one-off, less actionable)
    or spread across many small ones (an everyday-habits problem), which
    changes what you'd actually do about it. Complements the Largest Expense
    KPI, which only ever shows the single biggest transaction."""
    amounts = sorted(
        (t.amount for t in session.scalars(_base_query(date_from, date_to))
         if t.transaction_type == TransactionType.expense and t.category.counts_as_expense),
        reverse=True,
    )
    total = sum(amounts)
    top_sum = sum(amounts[:top_n])
    return {
        "top_n": top_n, "top_sum": round(top_sum, 2), "total": round(total, 2),
        "pct": round(top_sum / total, 4) if total else 0.0,
        "transaction_count": len(amounts),
    }


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
