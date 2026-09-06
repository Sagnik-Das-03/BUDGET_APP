from datetime import date

from app.dashboard import calculations as calc
from app.models import TransactionType
from app.repositories.accounts import AccountRepository
from app.repositories.categories import CategoryRepository
from app.repositories.transactions import TransactionRepository


def _txn(tx_repo, category, account, *, d, amount):
    return tx_repo.create(
        date=d, description="txn", amount=amount,
        transaction_type=TransactionType.expense, category=category, account=account,
    )


def test_reports_the_delta_between_this_month_and_last_month(session):
    cat_repo, acct_repo, tx_repo = CategoryRepository(session), AccountRepository(session), TransactionRepository(session)
    shopping, food, account = cat_repo.get_by_name("Shopping"), cat_repo.get_by_name("Food-Order"), acct_repo.get_or_create("Primary")

    _txn(tx_repo, shopping, account, d=date(2026, 8, 5), amount=1000.0)  # last month
    _txn(tx_repo, shopping, account, d=date(2026, 9, 5), amount=1500.0)  # this month - up 50%
    _txn(tx_repo, food, account, d=date(2026, 9, 5), amount=200.0)  # new this month, nothing last month
    session.commit()

    result = calc.category_trends(session, "this_month", date(2026, 9, 1), date(2026, 9, 30))

    shopping_row = next(r for r in result if r["category"] == "Shopping")
    assert shopping_row["current"] == 1500.0
    assert shopping_row["previous"] == 1000.0
    assert shopping_row["delta_abs"] == 500.0
    assert shopping_row["delta_pct"] == 0.5

    food_row = next(r for r in result if r["category"] == "Food-Order")
    assert food_row["previous"] == 0.0
    assert food_row["delta_pct"] is None  # can't compute a % change from a zero baseline


def test_sorted_by_absolute_rupee_swing_not_percentage(session):
    """A Rs 50 -> Rs 150 jump is a huge 200% swing but trivial money; a
    Rs 20,000 -> Rs 24,000 jump is a modest 20% swing that actually moved the
    budget - the bigger real-money swing should sort first."""
    cat_repo, acct_repo, tx_repo = CategoryRepository(session), AccountRepository(session), TransactionRepository(session)
    small, big, account = cat_repo.get_by_name("Shopping"), cat_repo.get_by_name("Utilities"), acct_repo.get_or_create("Primary")

    _txn(tx_repo, small, account, d=date(2026, 8, 5), amount=50.0)
    _txn(tx_repo, small, account, d=date(2026, 9, 5), amount=150.0)
    _txn(tx_repo, big, account, d=date(2026, 8, 5), amount=20000.0)
    _txn(tx_repo, big, account, d=date(2026, 9, 5), amount=24000.0)
    session.commit()

    result = calc.category_trends(session, "this_month", date(2026, 9, 1), date(2026, 9, 30))

    assert result[0]["category"] == "Utilities"
    assert result[1]["category"] == "Shopping"


def test_empty_for_all_time_and_custom_which_have_no_natural_previous_period(session):
    assert calc.category_trends(session, "all_time", None, None) == []
    assert calc.category_trends(session, "custom", date(2026, 9, 1), date(2026, 9, 30)) == []


def test_excludes_categories_that_do_not_count_as_a_real_expense(session):
    """Regression test: SIP/Savings (counts_as_expense=False) were leaking
    into Expense trends since by_category() only filters on transaction_type,
    not counts_as_expense - a bigger SIP contribution showing up as a
    "spending" swing is exactly the inconsistency the rest of the app (the
    Expenses KPI, essential/discretionary split, anomaly detection) already
    avoids by excluding these categories."""
    cat_repo, acct_repo, tx_repo = CategoryRepository(session), AccountRepository(session), TransactionRepository(session)
    sip, account = cat_repo.get_by_name("SIP"), acct_repo.get_or_create("Primary")
    assert sip.counts_as_expense is False

    _txn(tx_repo, sip, account, d=date(2026, 8, 5), amount=15000.0)
    _txn(tx_repo, sip, account, d=date(2026, 9, 5), amount=5000.0)
    session.commit()

    result = calc.category_trends(session, "this_month", date(2026, 9, 1), date(2026, 9, 30))

    assert not any(r["category"] == "SIP" for r in result)
