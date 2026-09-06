from datetime import date

from app.dashboard import calculations as calc
from app.models import TransactionType
from app.repositories.accounts import AccountRepository
from app.repositories.budgets import BudgetRepository
from app.repositories.categories import CategoryRepository
from app.repositories.transactions import TransactionRepository


def _txn(tx_repo, category, account, *, day, amount, transaction_type=TransactionType.expense):
    return tx_repo.create(
        date=date(2026, 9, day), description=f"txn-{day}", amount=amount,
        transaction_type=transaction_type, category=category, account=account,
    )


def test_projects_totals_linearly_from_days_elapsed_so_far(session):
    """September has 30 days. 10 days in, Rs 300 spent so far (Rs 30/day) -
    at that pace the month should project to Rs 900 (30 days * Rs 30/day)."""
    cat_repo, acct_repo, tx_repo = CategoryRepository(session), AccountRepository(session), TransactionRepository(session)
    category, account = cat_repo.get_by_name("Shopping"), acct_repo.get_or_create("Primary")

    for day in range(1, 11):
        _txn(tx_repo, category, account, day=day, amount=30.0)
    session.commit()

    result = calc.forecast(session, "2026-09", as_of=date(2026, 9, 10))

    assert result["is_current"] is True
    assert result["days_elapsed"] == 10
    assert result["days_in_period"] == 30
    assert result["expenses_so_far"] == 300.0
    assert result["projected_expenses"] == 900.0


def test_projected_savings_rate_uses_projected_figures_not_so_far_figures(session):
    cat_repo, acct_repo, tx_repo = CategoryRepository(session), AccountRepository(session), TransactionRepository(session)
    category, account = cat_repo.get_by_name("Shopping"), acct_repo.get_or_create("Primary")

    _txn(tx_repo, category, account, day=1, amount=1000.0, transaction_type=TransactionType.income)
    _txn(tx_repo, category, account, day=1, amount=200.0)
    session.commit()

    # day 1 of 30 - pace multiplier is 30x
    result = calc.forecast(session, "2026-09", as_of=date(2026, 9, 1))

    assert result["projected_income"] == 30000.0
    assert result["projected_expenses"] == 6000.0
    assert result["projected_net"] == 24000.0
    assert result["projected_savings_rate"] == round(24000.0 / 30000.0, 4)


def test_flags_a_category_pacing_to_exceed_its_budget_even_though_actual_so_far_is_under_it(session):
    """5 days into a 30-day month, Rs 200 spent against a Rs 600 goal - only
    33% actually spent, well under the 90% budget_alerts() threshold, but at
    that daily pace (Rs 40/day) the month projects to Rs 1200, double the
    goal - this is exactly the early-warning gap budget_alerts() (which only
    looks at money already spent) can't catch."""
    cat_repo, acct_repo, tx_repo = CategoryRepository(session), AccountRepository(session), TransactionRepository(session)
    category, account = cat_repo.get_by_name("Shopping"), acct_repo.get_or_create("Primary")
    BudgetRepository(session).set_goal(category, 600.0, period_key="2026-09")

    for day in range(1, 6):
        _txn(tx_repo, category, account, day=day, amount=40.0)
    session.commit()

    result = calc.forecast(session, "2026-09", as_of=date(2026, 9, 5))

    row = next(r for r in result["category_pace"] if r["category"] == "Shopping")
    assert row["actual"] == 200.0
    assert row["goal"] == 600.0
    assert row["projected"] == 1200.0
    assert row["status"] == "over"


def test_category_without_a_goal_is_excluded_from_pace_list(session):
    cat_repo, acct_repo, tx_repo = CategoryRepository(session), AccountRepository(session), TransactionRepository(session)
    category, account = cat_repo.get_by_name("Shopping"), acct_repo.get_or_create("Primary")
    _txn(tx_repo, category, account, day=1, amount=500.0)
    session.commit()

    result = calc.forecast(session, "2026-09", as_of=date(2026, 9, 5))

    assert result["category_pace"] == []


def test_a_fully_elapsed_past_period_has_no_extrapolation(session):
    """Once the period is over, pace collapses to 1x - the 'projection' for a
    closed month is just its final actual, not a forward-looking guess."""
    cat_repo, acct_repo, tx_repo = CategoryRepository(session), AccountRepository(session), TransactionRepository(session)
    category, account = cat_repo.get_by_name("Shopping"), acct_repo.get_or_create("Primary")

    for day in range(1, 6):
        _txn(tx_repo, category, account, day=day, amount=100.0)
    session.commit()

    result = calc.forecast(session, "2026-09", as_of=date(2026, 10, 15))

    assert result["is_current"] is False
    assert result["days_elapsed"] == result["days_in_period"] == 30
    assert result["expenses_so_far"] == 500.0
    assert result["projected_expenses"] == 500.0
