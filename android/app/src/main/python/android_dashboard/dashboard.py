"""Computes dashboard totals from raw Transactions-tab rows.

Simplified vs the desktop app's dashboard/calculations.py: "expenses" here
means every Expense-type row, full stop - the desktop app additionally
splits out SIP/Savings-style categories into their own non-"true spending"
line items via each Category's counts_as_expense flag, but that flag lives
only in the desktop SQLite database, not as a column on the Transactions
sheet - a read-only viewer with nothing but the sheet has no way to know
it. Fine for an at-a-glance phone view; if you want the exact same
SIP/cash-savings split shown here, that flag would need to be exported as
an extra column on the Transactions tab.
"""
from datetime import date as date_type

from android_dashboard.parsing import Txn, parse_row


def _period_key(d: date_type) -> str:
    return f"{d.year:04d}-{d.month:02d}"


def _totals(txns: list[Txn]) -> dict:
    income = sum(t.amount for t in txns if t.transaction_type == "Income")
    expenses = sum(t.amount for t in txns if t.transaction_type == "Expense")
    net = income - expenses
    return {
        "income": round(income, 2),
        "expenses": round(expenses, 2),
        "net": round(net, 2),
        "savings_rate": round(net / income, 4) if income else 0.0,
    }


def compute_dashboard(rows: list[list[str]], today: date_type = None) -> dict:
    today = today or date_type.today()
    this_month_key = _period_key(today)

    txns = [t for t in (parse_row(r) for r in rows) if t and not t.deleted]

    this_month = _totals([t for t in txns if _period_key(t.date) == this_month_key])
    this_year = _totals([t for t in txns if t.date.year == today.year])
    all_time = _totals(txns)

    category_totals: dict[str, float] = {}
    for t in txns:
        if t.transaction_type == "Expense":
            category_totals[t.category] = category_totals.get(t.category, 0.0) + t.amount
    categories = sorted(
        ({"category": c, "total": round(v, 2)} for c, v in category_totals.items()),
        key=lambda r: -r["total"],
    )

    return {
        "this_month": this_month,
        "this_year": this_year,
        "all_time": all_time,
        "categories": categories,
        "transaction_count": len(txns),
        "generated_at": today.isoformat(),
    }
