"""Ports backend/app/dashboard/calculations.py to operate on a plain list of
parsed Txn objects (see parsing.py) plus a Config (category metadata,
budgets, savings goal - all now exported to the Sheet's "Config" tab by
backend/app/sync/reports.py's regenerate_config_tab) instead of a SQLAlchemy
session. Kept function-for-function parallel to the original so the two
can be diffed against each other if the original ever changes - anything
NOT ported here (detect_anomalies, and by extension the AI insight text)
is out of scope for this read-only, no-LLM build.

Every date-range function takes an already-loaded list[Txn] (never
re-fetches), unlike the original which re-queries per call - this module's
caller (server.py) loads the Sheet once per request/cache window and passes
the same list through every calculation.
"""
from datetime import date as date_type, timedelta
from typing import Optional

from android_dashboard.parsing import Config, Txn

_DAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def day_key_for(d: date_type) -> str:
    return d.isoformat()


def week_key_for(d: date_type) -> str:
    iso = d.isocalendar()
    return f"{iso[0]:04d}-W{iso[1]:02d}"


def period_key_for(d: date_type) -> str:
    return f"{d.year:04d}-{d.month:02d}"


def year_key_for(d: date_type) -> str:
    return f"{d.year:04d}"


def period_start(period_key: str) -> date_type:
    year, month = period_key.split("-")
    return date_type(int(year), int(month), 1)


def period_end(period_key: str) -> date_type:
    year, month = int(period_key.split("-")[0]), int(period_key.split("-")[1])
    if month == 12:
        return date_type(year, 12, 31)
    return date_type(year, month + 1, 1) - timedelta(days=1)


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


_RANGE_FN = {"this_week": range_this_week, "this_month": range_this_month, "this_year": range_this_year}


def resolve_range(range_: str, date_from: Optional[date_type], date_to: Optional[date_type]
                   ) -> tuple[Optional[date_type], Optional[date_type]]:
    if range_ == "all_time":
        return None, None
    if range_ == "custom":
        return date_from, date_to
    return _RANGE_FN.get(range_, range_this_month)()


def _filter(txns: list[Txn], date_from: Optional[date_type], date_to: Optional[date_type]) -> list[Txn]:
    out = txns
    if date_from:
        out = [t for t in out if t.date >= date_from]
    if date_to:
        out = [t for t in out if t.date <= date_to]
    return out


def _categorize_expense(t: Txn, config: Config) -> str:
    meta = config.meta(t.category)
    if meta.counts_as_expense:
        return "expenses"
    if t.category == "SIP":
        return "sip"
    return "cash_savings"


def totals(txns: list[Txn], config: Config, date_from: Optional[date_type] = None,
           date_to: Optional[date_type] = None) -> dict:
    rows = _filter(txns, date_from, date_to)
    income = sum(t.amount for t in rows if t.transaction_type == "Income")
    buckets = {"expenses": 0.0, "sip": 0.0, "cash_savings": 0.0}
    for t in rows:
        if t.transaction_type == "Expense":
            buckets[_categorize_expense(t, config)] += t.amount
    net = income - buckets["expenses"]
    return {
        "income": round(income, 2), "expenses": round(buckets["expenses"], 2),
        "sip": round(buckets["sip"], 2), "cash_savings": round(buckets["cash_savings"], 2),
        "net": round(net, 2), "savings_rate": round(net / income, 4) if income else 0.0,
    }


def by_category(txns: list[Txn], config: Config, date_from: Optional[date_type] = None,
                 date_to: Optional[date_type] = None, transaction_type: str = "Expense") -> list[dict]:
    rows = _filter(txns, date_from, date_to)
    totals_map: dict[str, float] = {}
    for t in rows:
        if t.transaction_type != transaction_type:
            continue
        totals_map[t.category] = totals_map.get(t.category, 0.0) + t.amount
    out = [{"category": name, "total": round(total, 2), "color": config.meta(name).color}
           for name, total in totals_map.items()]
    out.sort(key=lambda r: -r["total"])
    return out


def _period_buckets(txns: list[Txn], config: Config, key_fn, date_from: Optional[date_type],
                     date_to: Optional[date_type]) -> dict:
    rows = _filter(txns, date_from, date_to)
    buckets: dict[str, dict] = {}
    for t in rows:
        key = key_fn(t.date)
        b = buckets.setdefault(key, {"income": 0.0, "expenses": 0.0, "sip": 0.0, "cash_savings": 0.0})
        if t.transaction_type == "Income":
            b["income"] += t.amount
        else:
            b[_categorize_expense(t, config)] += t.amount
    return buckets


def daily_trend(txns: list[Txn], config: Config, date_from: Optional[date_type] = None,
                 date_to: Optional[date_type] = None) -> list[dict]:
    buckets = _period_buckets(txns, config, day_key_for, date_from, date_to)
    return [
        {"day": k, "income": round(buckets[k]["income"], 2), "expenses": round(buckets[k]["expenses"], 2),
         "net": round(buckets[k]["income"] - buckets[k]["expenses"], 2)}
        for k in sorted(buckets)
    ]


def weekly_trend(txns: list[Txn], config: Config, limit: Optional[int] = 12,
                  date_from: Optional[date_type] = None, date_to: Optional[date_type] = None) -> list[dict]:
    buckets = _period_buckets(txns, config, week_key_for, date_from, date_to)
    keys = sorted(buckets)
    if limit:
        keys = keys[-limit:]
    return [
        {"week_key": k, "income": round(buckets[k]["income"], 2), "expenses": round(buckets[k]["expenses"], 2),
         "net": round(buckets[k]["income"] - buckets[k]["expenses"], 2)}
        for k in keys
    ]


def monthly_trend(txns: list[Txn], config: Config, limit: Optional[int] = None,
                   date_from: Optional[date_type] = None, date_to: Optional[date_type] = None) -> list[dict]:
    buckets = _period_buckets(txns, config, period_key_for, date_from, date_to)
    keys = sorted(buckets)
    if limit:
        keys = keys[-limit:]
    return [
        {"period_key": k, "label": k, "income": round(buckets[k]["income"], 2),
         "expenses": round(buckets[k]["expenses"], 2),
         "net": round(buckets[k]["income"] - buckets[k]["expenses"], 2)}
        for k in keys
    ]


def yearly_trend(txns: list[Txn], config: Config) -> list[dict]:
    buckets = _period_buckets(txns, config, year_key_for, None, None)
    return [
        {"year": k, "income": round(buckets[k]["income"], 2), "expenses": round(buckets[k]["expenses"], 2),
         "net": round(buckets[k]["income"] - buckets[k]["expenses"], 2)}
        for k in sorted(buckets)
    ]


def trend_for_range(txns: list[Txn], config: Config, range_: str, date_from: Optional[date_type],
                     date_to: Optional[date_type]) -> dict:
    if range_ == "this_week":
        return {"granularity": "daily", "rows": daily_trend(txns, config, date_from, date_to)}
    if range_ == "this_month":
        return {"granularity": "weekly", "rows": weekly_trend(txns, config, date_from=date_from, date_to=date_to, limit=None)}
    if range_ == "this_year":
        return {"granularity": "monthly", "rows": monthly_trend(txns, config, date_from=date_from, date_to=date_to)}
    return {"granularity": "yearly", "rows": yearly_trend(txns, config)}


def monthly_breakdown(txns: list[Txn], config: Config) -> list[dict]:
    buckets = _period_buckets(txns, config, period_key_for, None, None)
    out = []
    for k in sorted(buckets):
        b = buckets[k]
        net = b["income"] - b["expenses"]
        out.append({
            "period_key": k, "income": round(b["income"], 2), "expenses": round(b["expenses"], 2),
            "sip": round(b["sip"], 2), "cash_savings": round(b["cash_savings"], 2),
            "net": round(net, 2), "savings_rate": round(net / b["income"], 4) if b["income"] else 0.0,
        })
    return out


def category_drilldown(txns: list[Txn], config: Config, date_from: Optional[date_type] = None,
                        date_to: Optional[date_type] = None, transaction_type: str = "Expense") -> list[dict]:
    rows = _filter(txns, date_from, date_to)
    by_cat: dict[str, dict] = {}
    for t in rows:
        if t.transaction_type != transaction_type:
            continue
        node = by_cat.setdefault(t.category, {
            "name": t.category, "color": config.meta(t.category).color, "value": 0.0, "children": [],
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


def highlights(txns: list[Txn], config: Config, date_from: Optional[date_type] = None,
               date_to: Optional[date_type] = None) -> dict:
    cats = by_category(txns, config, date_from, date_to, transaction_type="Expense")
    rows = _filter(txns, date_from, date_to)
    t = totals(txns, config, date_from, date_to)
    if date_from and date_to:
        days = (date_to - date_from).days + 1
    else:
        dates = [tx.date for tx in rows]
        days = (max(dates) - min(dates)).days + 1 if dates else 1
    return {
        "top_category": cats[0] if cats else None,
        "transaction_count": len(rows),
        "avg_daily_spend": round(t["expenses"] / days, 2) if days else 0.0,
        "days": days,
    }


def _pct_delta(current: float, previous: float) -> Optional[float]:
    if previous == 0:
        return None
    return round((current - previous) / abs(previous), 4)


def _previous_range_bounds(range_: str, date_from: Optional[date_type]) -> Optional[tuple[date_type, date_type]]:
    if not date_from:
        return None
    if range_ == "this_week":
        return range_this_week(date_from - timedelta(days=7))
    if range_ == "this_month":
        return _range_previous_month(date_from)
    if range_ == "this_year":
        return range_previous_year(date_from)
    return None


def period_comparison(txns: list[Txn], config: Config, range_: str, date_from: Optional[date_type],
                       date_to: Optional[date_type]) -> Optional[dict]:
    prev = _previous_range_bounds(range_, date_from)
    if not prev:
        return None
    cur = totals(txns, config, date_from, date_to)
    prv = totals(txns, config, *prev)
    return {
        "income_delta_pct": _pct_delta(cur["income"], prv["income"]),
        "expenses_delta_pct": _pct_delta(cur["expenses"], prv["expenses"]),
        "net_delta_pct": _pct_delta(cur["net"], prv["net"]),
        "net_delta_abs": round(cur["net"] - prv["net"], 2),
        "previous_range": {"date_from": prev[0].isoformat(), "date_to": prev[1].isoformat()},
    }


def category_trends(txns: list[Txn], config: Config, range_: str, date_from: Optional[date_type],
                     date_to: Optional[date_type], transaction_type: str = "Expense") -> list[dict]:
    prev = _previous_range_bounds(range_, date_from)
    if not prev:
        return []
    cur_rows = by_category(txns, config, date_from, date_to, transaction_type=transaction_type)
    prv_rows = by_category(txns, config, *prev, transaction_type=transaction_type)
    if transaction_type == "Expense":
        real_expense_names = {name for name in set(t.category for t in txns) if config.meta(name).counts_as_expense}
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


def category_volatility(txns: list[Txn], config: Config, months: int = 6, min_months: int = 3) -> list[dict]:
    this_month_start = period_start(period_key_for(date_type.today()))
    window_start = this_month_start
    for _ in range(months):
        window_start = period_start(period_key_for(window_start - timedelta(days=1)))
    window_end = this_month_start - timedelta(days=1)

    per_cat_month: dict[str, dict[str, float]] = {}
    for t in _filter(txns, window_start, window_end):
        if t.transaction_type != "Expense" or not config.meta(t.category).counts_as_expense:
            continue
        bucket = per_cat_month.setdefault(t.category, {})
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


def spending_pattern(txns: list[Txn], date_from: Optional[date_type] = None,
                      date_to: Optional[date_type] = None) -> dict:
    by_dow = {name: 0.0 for name in _DAY_NAMES}
    by_third = {"1st (days 1-10)": 0.0, "2nd (days 11-20)": 0.0, "3rd (days 21+)": 0.0}
    total = 0.0
    for t in _filter(txns, date_from, date_to):
        if t.transaction_type != "Expense":
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


def essential_vs_discretionary(txns: list[Txn], config: Config, date_from: Optional[date_type] = None,
                                date_to: Optional[date_type] = None) -> dict:
    essential_by_cat: dict[str, float] = {}
    discretionary_by_cat: dict[str, float] = {}
    for t in _filter(txns, date_from, date_to):
        if t.transaction_type != "Expense" or not config.meta(t.category).counts_as_expense:
            continue
        bucket = essential_by_cat if config.meta(t.category).is_essential else discretionary_by_cat
        bucket[t.category] = bucket.get(t.category, 0.0) + t.amount

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


def savings_streak(txns: list[Txn], config: Config, as_of: Optional[date_type] = None) -> dict:
    current_period_key = period_key_for(as_of or date_type.today())
    rows = sorted(
        (r for r in monthly_breakdown(txns, config) if r["period_key"] < current_period_key),
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


def spend_concentration(txns: list[Txn], config: Config, date_from: Optional[date_type] = None,
                         date_to: Optional[date_type] = None, top_n: int = 3) -> dict:
    amounts = sorted(
        (t.amount for t in _filter(txns, date_from, date_to)
         if t.transaction_type == "Expense" and config.meta(t.category).counts_as_expense),
        reverse=True,
    )
    total = sum(amounts)
    top_sum = sum(amounts[:top_n])
    return {
        "top_n": top_n, "top_sum": round(top_sum, 2), "total": round(total, 2),
        "pct": round(top_sum / total, 4) if total else 0.0,
        "transaction_count": len(amounts),
    }


def budget_vs_actual(txns: list[Txn], config: Config, period_key: str) -> list[dict]:
    specific = {b.category: b.goal_amount for b in config.budgets if b.period_key == period_key}
    defaults = {b.category: b.goal_amount for b in config.budgets if b.period_key is None}
    goals = {**defaults, **specific}
    actuals = {row["category"]: row["total"] for row in by_category(
        txns, config, date_from=period_start(period_key), date_to=period_end(period_key), transaction_type="Expense")}
    categories = set(goals) | set(actuals)
    return sorted(
        [{"category": c, "goal": goals.get(c, 0.0), "actual": actuals.get(c, 0.0)} for c in categories],
        key=lambda r: r["category"],
    )


def budget_alerts(txns: list[Txn], config: Config, period_key: str, warning_threshold: float = 0.9) -> list[dict]:
    rows = budget_vs_actual(txns, config, period_key)
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


def savings_goal_for_period(config: Config, period_key: str) -> Optional[float]:
    specific = next((g.goal_amount for g in config.savings_goals if g.period_key == period_key), None)
    if specific is not None:
        return specific
    return next((g.goal_amount for g in config.savings_goals if g.period_key is None), None)


def savings_goal_progress(txns: list[Txn], config: Config, period_key: str,
                           warning_threshold: float = 0.7) -> Optional[dict]:
    goal = savings_goal_for_period(config, period_key)
    if goal is None or goal <= 0:
        return None
    actual = totals(txns, config, period_start(period_key), period_end(period_key))["net"]
    pct = actual / goal
    status = "met" if pct >= 1.0 else "warning" if pct >= warning_threshold else "behind"
    return {"goal": goal, "actual": round(actual, 2), "pct": round(pct, 4), "status": status}
