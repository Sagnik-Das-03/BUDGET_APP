from datetime import date as date_type

import typer

from app.db import init_db, session_scope
from app.dashboard import calculations as calc
from app.models import TransactionType
from app.repositories.accounts import AccountRepository
from app.repositories.categories import CategoryRepository
from app.repositories.transactions import TransactionRepository
from app.sync import scheduler
from app.utils import period_key_for

app = typer.Typer(help="Budget Tracker CLI")
category_app = typer.Typer(help="Manage categories")
app.add_typer(category_app, name="category")


def _bootstrap():
    init_db()


@app.command("add-transaction")
def add_transaction(
    description: str = typer.Option(..., "--description", "-d"),
    amount: float = typer.Option(..., "--amount", "-a"),
    type: str = typer.Option("Expense", "--type", "-t"),
    category: str = typer.Option("Other", "--category", "-c"),
    account: str = typer.Option("Primary", "--account"),
    date: str = typer.Option(None, "--date", help="YYYY-MM-DD, defaults to today"),
    notes: str = typer.Option(None, "--notes"),
):
    _bootstrap()
    d = date_type.fromisoformat(date) if date else date_type.today()
    with session_scope() as session:
        cat = CategoryRepository(session).add(category)
        acct = AccountRepository(session).get_or_create(account)
        txn = TransactionRepository(session).create(
            date=d, description=description, amount=amount, transaction_type=TransactionType(type),
            category=cat, account=acct, notes=notes,
        )
        typer.echo(f"Created {txn.transaction_id}: {d} {description} {amount} ({type}, {category})")


@app.command("list")
def list_transactions(year: int = None, month: int = None, limit: int = 50):
    _bootstrap()
    with session_scope() as session:
        rows = TransactionRepository(session).filter(year=year, month=month)[:limit]
        for t in rows:
            ttype = t.transaction_type.value if hasattr(t.transaction_type, "value") else t.transaction_type
            typer.echo(f"{t.transaction_id}  {t.date}  {t.description[:40]:<40}  {t.category.name:<16}  {ttype:<8}  {t.amount:>10.2f}")


@app.command("dashboard")
def dashboard_cmd(range: str = "this_month"):
    _bootstrap()
    with session_scope() as session:
        range_fn = {
            "this_week": calc.range_this_week, "this_month": calc.range_this_month,
            "this_year": calc.range_this_year,
        }.get(range)
        d_from, d_to = range_fn() if range_fn else (None, None)
        s = calc.totals(session, d_from, d_to)
        typer.echo(f"Income:    {s['income']:>12,.2f}")
        typer.echo(f"Expenses:  {s['expenses']:>12,.2f}")
        typer.echo(f"SIP:       {s['sip']:>12,.2f}")
        typer.echo(f"Cash Savings: {s['cash_savings']:>9,.2f}")
        typer.echo(f"Net:       {s['net']:>12,.2f}")
        typer.echo(f"Savings %: {s['savings_rate'] * 100:>11.1f}%")
        typer.echo("\nBy category:")
        for row in calc.by_category(session, d_from, d_to):
            typer.echo(f"  {row['category']:<16} {row['total']:>12,.2f}")


@app.command("sync-now")
def sync_now():
    _bootstrap()
    result = scheduler.run_once()
    typer.echo(result)


@app.command("import-legacy")
def import_legacy(xlsx_path: str = typer.Argument(..., help="Path to the legacy Excel workbook")):
    from scripts.seed_from_existing_xlsx import run_seed
    _bootstrap()
    run_seed(xlsx_path)


@category_app.command("add")
def category_add(name: str, color: str = "#898781"):
    _bootstrap()
    with session_scope() as session:
        cat = CategoryRepository(session).add(name, color)
        typer.echo(f"Category ready: {cat.name} ({cat.color_hex})")


@category_app.command("list")
def category_list():
    _bootstrap()
    with session_scope() as session:
        for c in CategoryRepository(session).list():
            typer.echo(f"{c.id:<4} {c.name:<20} {c.color_hex}")


@category_app.command("deactivate")
def category_deactivate(category_id: int):
    _bootstrap()
    with session_scope() as session:
        cat = CategoryRepository(session).deactivate(category_id)
        typer.echo(f"Deactivated {cat.name}" if cat else "Not found")


if __name__ == "__main__":
    app()
