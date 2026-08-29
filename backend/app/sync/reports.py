"""Regenerates every generated, read-only tab (per-month, Weekly Summary, Yearly
Summary, Dashboard) from the current DB state - human-readable formatting + native
charts, reusing the validated color palette from the earlier xlsx dashboard work.
Called at the end of every sync cycle that actually changed something, so these
views can never drift from the canonical Transactions tab."""
from datetime import date as date_type

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.dashboard import calculations as calc
from app.models import MonthlyPeriod
from app.repositories.transactions import TransactionRepository
from app.sheets import formatting, mapping
from app.sheets.adapter import GoogleSheetsService
from app.utils import period_key_for

INCOME_COLOR = "#2A78D6"
EXPENSE_COLOR = "#E34948"
NET_COLOR = "#4A3AA7"
GOAL_COLOR = "#898781"
MAGNITUDE_COLOR = "#2A78D6"
SIP_COLOR = "#008300"
CASH_SAVINGS_COLOR = "#1BAF7A"

NOTE = "Auto-generated from the app database - do not edit directly. Edit via the app or the Transactions tab."


def format_transactions_header(sheets: GoogleSheetsService, spreadsheet_id: str) -> None:
    sheet_id = sheets.ensure_sheet(spreadsheet_id, "Transactions")
    sheets.batch_format(spreadsheet_id, [
        formatting.bold_header_request(sheet_id, 0, len(mapping.HEADERS)),
        formatting.freeze_row_request(sheet_id, 1),
        formatting.currency_format_request(sheet_id, 1, 5000, 5, 6),
    ])


def _rewrite_tab(sheets: GoogleSheetsService, spreadsheet_id: str, tab_name: str, grid: list[list],
                  header_rows0: list[tuple[int, int]], currency_ranges: list[tuple[int, int, int, int]],
                  chart_specs: list[dict]) -> int:
    sheet_id = sheets.ensure_sheet(spreadsheet_id, tab_name)
    old_charts = sheets.get_chart_ids(spreadsheet_id, sheet_id)
    sheets.delete_charts(spreadsheet_id, old_charts)
    sheets.clear_and_write(spreadsheet_id, tab_name, grid)

    reqs = [formatting.title_request(sheet_id, 0), formatting.freeze_row_request(sheet_id, 1)]
    for row0, ncols in header_rows0:
        reqs.append(formatting.bold_header_request(sheet_id, row0, ncols))
    for (r0, r1, c0, c1) in currency_ranges:
        reqs.append(formatting.currency_format_request(sheet_id, r0, r1, c0, c1))
    reqs.append(formatting.column_width_request(sheet_id, 0, 180))
    sheets.batch_format(spreadsheet_id, reqs)

    if chart_specs:
        sheets.batch_format(spreadsheet_id, [
            formatting.basic_chart_request(sheet_id=sheet_id, **spec) for spec in chart_specs
        ])
    return sheet_id


def _trend_chart_spec(*, title: str, row_start0: int, row_end0: int, anchor_row0: int) -> dict:
    return dict(
        chart_type="LINE", title=title, domain_col0=0, series_cols0=[1, 2, 3],
        row_start0=row_start0, row_end0=row_end0, series_names=["Income", "Expenses", "Net Savings"],
        series_colors=[INCOME_COLOR, EXPENSE_COLOR, NET_COLOR], anchor_row0=anchor_row0, anchor_col0=6,
    )


def regenerate_dashboard(session: Session, sheets: GoogleSheetsService, spreadsheet_id: str) -> None:
    today = date_type.today()
    this_month = calc.totals(session, *calc.range_this_month(today))
    this_year = calc.totals(session, *calc.range_this_year(today))
    all_time = calc.totals(session)

    kpi_header_row0 = 3
    grid: list[list] = [
        ["Finance Dashboard"],
        [NOTE],
        [],
        ["Metric", "This Month", "This Year", "All Time"],
        ["Income", this_month["income"], this_year["income"], all_time["income"]],
        ["Expenses (true spending)", this_month["expenses"], this_year["expenses"], all_time["expenses"]],
        ["SIP", this_month["sip"], this_year["sip"], all_time["sip"]],
        ["Cash Savings (transfers)", this_month["cash_savings"], this_year["cash_savings"], all_time["cash_savings"]],
        ["Net Savings", this_month["net"], this_year["net"], all_time["net"]],
        ["Savings Rate", this_month["savings_rate"], this_year["savings_rate"], all_time["savings_rate"]],
        [],
    ]
    kpi_data_end0 = len(grid) - 1  # trailing blank row not part of the currency range
    header_rows0 = [(kpi_header_row0, 4)]
    currency_ranges = [(kpi_header_row0 + 1, kpi_data_end0, 1, 4)]

    trend_header_row0 = len(grid)
    grid.append(["Monthly Trend"])
    grid.append(["Month", "Income", "Expenses", "Net Savings"])
    header_rows0.append((trend_header_row0 + 1, 4))
    trend_data_start0 = len(grid)
    for row in calc.monthly_trend(session):
        grid.append([row["period_key"], row["income"], row["expenses"], row["net"]])
    trend_data_end0 = len(grid)
    currency_ranges.append((trend_data_start0, trend_data_end0, 1, 4))
    grid.append([])

    cat_header_row0 = len(grid)
    grid.append(["Category Breakdown (All Time)"])
    grid.append(["Category", "Total"])
    header_rows0.append((cat_header_row0 + 1, 2))
    cat_data_start0 = len(grid)
    for row in calc.by_category(session):
        grid.append([row["category"], row["total"]])
    cat_data_end0 = len(grid)
    currency_ranges.append((cat_data_start0, cat_data_end0, 1, 2))
    grid.append([])

    budget_rows = calc.budget_vs_actual(session, period_key_for(today))
    chart_specs = [_trend_chart_spec(title="Monthly Trend: Income vs Expenses vs Net Savings",
                                      row_start0=trend_header_row0 + 1, row_end0=trend_data_end0, anchor_row0=3)]
    if cat_data_end0 > cat_data_start0:
        chart_specs.append(dict(
            chart_type="COLUMN", title="Total Spend by Category (All Time)", domain_col0=0, series_cols0=[1],
            row_start0=cat_header_row0 + 1, row_end0=cat_data_end0, series_names=["Total"],
            series_colors=[MAGNITUDE_COLOR], anchor_row0=27, anchor_col0=6,
        ))
    if budget_rows:
        budget_header_row0 = len(grid)
        grid.append([f"{period_key_for(today)}: Budget Goal vs Actual"])
        grid.append(["Category", "Goal", "Actual"])
        header_rows0.append((budget_header_row0 + 1, 3))
        budget_data_start0 = len(grid)
        for row in budget_rows:
            grid.append([row["category"], row["goal"], row["actual"]])
        budget_data_end0 = len(grid)
        currency_ranges.append((budget_data_start0, budget_data_end0, 1, 3))
        chart_specs.append(dict(
            chart_type="COLUMN", title="Budget Goal vs Actual", domain_col0=0, series_cols0=[1, 2],
            row_start0=budget_header_row0 + 1, row_end0=budget_data_end0, series_names=["Goal", "Actual"],
            series_colors=[GOAL_COLOR, INCOME_COLOR], anchor_row0=49, anchor_col0=6,
        ))

    _rewrite_tab(sheets, spreadsheet_id, "Dashboard", grid, header_rows0, currency_ranges, chart_specs)


def regenerate_month_tab(session: Session, sheets: GoogleSheetsService, spreadsheet_id: str,
                          period: MonthlyPeriod) -> None:
    start = date_type(*[int(x) for x in period.period_key.split("-")], 1)
    end = calc.period_end(period.period_key)
    month_totals = calc.totals(session, start, end)
    cat_rows = calc.by_category(session, start, end)

    grid: list[list] = [
        [period.label],
        [NOTE],
        [],
        ["Income", "Expenses", "SIP", "Cash Savings", "Net Savings", "Savings Rate"],
        [month_totals["income"], month_totals["expenses"], month_totals["sip"], month_totals["cash_savings"],
         month_totals["net"], month_totals["savings_rate"]],
        [],
    ]
    header_rows0 = [(3, 6)]
    currency_ranges = [(4, 5, 0, 5)]

    cat_header_row0 = len(grid)
    grid.append(["Category Breakdown"])
    grid.append(["Category", "Total"])
    header_rows0.append((cat_header_row0 + 1, 2))
    cat_data_start0 = len(grid)
    for row in cat_rows:
        grid.append([row["category"], row["total"]])
    cat_data_end0 = len(grid)
    currency_ranges.append((cat_data_start0, cat_data_end0, 1, 2))
    grid.append([])

    chart_specs = []
    if cat_data_end0 > cat_data_start0:
        chart_specs.append(dict(
            chart_type="COLUMN", title=f"{period.label}: Spend by Category", domain_col0=0, series_cols0=[1],
            row_start0=cat_header_row0 + 1, row_end0=cat_data_end0, series_names=["Total"],
            series_colors=[MAGNITUDE_COLOR], anchor_row0=4, anchor_col0=7,
        ))

    tx_header_row0 = len(grid)
    grid.append(["Transactions"])
    grid.append(["Date", "Description", "Category", "Type", "Amount"])
    header_rows0.append((tx_header_row0 + 1, 5))
    tx_data_start0 = len(grid)
    repo = TransactionRepository(session)
    for txn in sorted(repo.filter(period_key=period.period_key), key=lambda t: t.date):
        ttype = txn.transaction_type.value if hasattr(txn.transaction_type, "value") else txn.transaction_type
        grid.append([txn.date.isoformat(), txn.description, txn.category.name, ttype, txn.amount])
    tx_data_end0 = len(grid)
    currency_ranges.append((tx_data_start0, tx_data_end0, 4, 5))

    _rewrite_tab(sheets, spreadsheet_id, period.period_key, grid, header_rows0, currency_ranges, chart_specs)


def regenerate_monthly_breakdown(session: Session, sheets: GoogleSheetsService, spreadsheet_id: str) -> None:
    """One row per month, every month side by side - unlike the per-month tabs
    (one tab each) or the Dashboard's 3-column trend table, this breaks SIP and
    Cash Savings (household/family transfers) out as their own columns instead of
    folding them into Net Savings, while still counting both toward Net Savings
    and the savings rate (spec feedback: 'keep sip and pure cash savings separate
    but count them in savings rate')."""
    headers = ["Month", "Income", "Expenses", "SIP", "Cash Savings", "Net Savings", "Savings Rate"]
    grid: list[list] = [["Monthly Breakdown"], [NOTE], [], headers]
    header_rows0 = [(3, len(headers))]
    data_start0 = len(grid)
    for row in calc.monthly_breakdown(session):
        grid.append([row["period_key"], row["income"], row["expenses"], row["sip"], row["cash_savings"],
                     row["net"], row["savings_rate"]])
    data_end0 = len(grid)
    currency_ranges = [(data_start0, data_end0, 1, 6)]
    chart_specs = []
    if data_end0 > data_start0:
        chart_specs.append(dict(
            chart_type="LINE", title="Monthly Breakdown: Income, Expenses, SIP, Cash Savings, Net Savings",
            domain_col0=0, series_cols0=[1, 2, 3, 4, 5], row_start0=3, row_end0=data_end0,
            series_names=["Income", "Expenses", "SIP", "Cash Savings", "Net Savings"],
            series_colors=[INCOME_COLOR, EXPENSE_COLOR, SIP_COLOR, CASH_SAVINGS_COLOR, NET_COLOR],
            anchor_row0=3, anchor_col0=8,
        ))
    _rewrite_tab(sheets, spreadsheet_id, "Monthly Breakdown", grid, header_rows0, currency_ranges, chart_specs)


def regenerate_weekly_summary(session: Session, sheets: GoogleSheetsService, spreadsheet_id: str) -> None:
    grid: list[list] = [["Weekly Summary"], [NOTE], [], ["Week", "Income", "Expenses", "Net Savings"]]
    header_rows0 = [(3, 4)]
    data_start0 = len(grid)
    for row in calc.weekly_trend(session, limit=26):
        grid.append([row["week_key"], row["income"], row["expenses"], row["net"]])
    data_end0 = len(grid)
    currency_ranges = [(data_start0, data_end0, 1, 4)]
    chart_specs = []
    if data_end0 > data_start0:
        chart_specs.append(_trend_chart_spec(title="Weekly Trend (last 26 weeks)",
                                              row_start0=3, row_end0=data_end0, anchor_row0=3))
    _rewrite_tab(sheets, spreadsheet_id, "Weekly Summary", grid, header_rows0, currency_ranges, chart_specs)


def regenerate_yearly_summary(session: Session, sheets: GoogleSheetsService, spreadsheet_id: str) -> None:
    grid: list[list] = [["Yearly Summary"], [NOTE], [], ["Year", "Income", "Expenses", "Net Savings"]]
    header_rows0 = [(3, 4)]
    data_start0 = len(grid)
    for row in calc.yearly_trend(session):
        grid.append([row["year"], row["income"], row["expenses"], row["net"]])
    data_end0 = len(grid)
    currency_ranges = [(data_start0, data_end0, 1, 4)]
    chart_specs = []
    if data_end0 > data_start0:
        chart_specs.append(_trend_chart_spec(title="Yearly Trend", row_start0=3, row_end0=data_end0, anchor_row0=3))
    _rewrite_tab(sheets, spreadsheet_id, "Yearly Summary", grid, header_rows0, currency_ranges, chart_specs)


def regenerate_all(session: Session, sheets: GoogleSheetsService, spreadsheet_id: str) -> dict:
    regenerate_dashboard(session, sheets, spreadsheet_id)
    periods = list(session.scalars(select(MonthlyPeriod).order_by(MonthlyPeriod.period_key)))
    for period in periods:
        regenerate_month_tab(session, sheets, spreadsheet_id, period)
    regenerate_monthly_breakdown(session, sheets, spreadsheet_id)
    regenerate_weekly_summary(session, sheets, spreadsheet_id)
    regenerate_yearly_summary(session, sheets, spreadsheet_id)
    return {"dashboard": True, "months": len(periods), "monthly_breakdown": True, "weekly": True, "yearly": True}
