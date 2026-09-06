from datetime import date

from app.dashboard import calculations as calc
from app.models import TransactionType
from app.repositories.accounts import AccountRepository
from app.repositories.categories import CategoryRepository
from app.repositories.transactions import TransactionRepository


def _txn(tx_repo, category, account, *, d, amount, transaction_type=TransactionType.expense):
    return tx_repo.create(
        date=d, description="txn", amount=amount,
        transaction_type=transaction_type, category=category, account=account,
    )


def test_buckets_by_day_of_week(session):
    cat_repo, acct_repo, tx_repo = CategoryRepository(session), AccountRepository(session), TransactionRepository(session)
    category, account = cat_repo.get_by_name("Shopping"), acct_repo.get_or_create("Primary")

    _txn(tx_repo, category, account, d=date(2026, 9, 7), amount=100.0)  # Monday
    _txn(tx_repo, category, account, d=date(2026, 9, 12), amount=300.0)  # Saturday
    session.commit()

    result = calc.spending_pattern(session, date(2026, 9, 1), date(2026, 9, 30))

    by_day = {row["day"]: row for row in result["by_day_of_week"]}
    assert by_day["Monday"]["total"] == 100.0
    assert by_day["Saturday"]["total"] == 300.0
    assert by_day["Monday"]["pct"] == 0.25
    assert by_day["Saturday"]["pct"] == 0.75
    assert by_day["Tuesday"]["total"] == 0.0


def test_buckets_by_third_of_the_month(session):
    cat_repo, acct_repo, tx_repo = CategoryRepository(session), AccountRepository(session), TransactionRepository(session)
    category, account = cat_repo.get_by_name("Shopping"), acct_repo.get_or_create("Primary")

    _txn(tx_repo, category, account, d=date(2026, 9, 1), amount=100.0)  # 1st third
    _txn(tx_repo, category, account, d=date(2026, 9, 15), amount=100.0)  # 2nd third
    _txn(tx_repo, category, account, d=date(2026, 9, 28), amount=200.0)  # 3rd third
    session.commit()

    result = calc.spending_pattern(session, date(2026, 9, 1), date(2026, 9, 30))

    by_third = {row["label"]: row for row in result["by_month_third"]}
    assert by_third["1st (days 1-10)"]["total"] == 100.0
    assert by_third["2nd (days 11-20)"]["total"] == 100.0
    assert by_third["3rd (days 21+)"]["total"] == 200.0
    assert by_third["3rd (days 21+)"]["pct"] == 0.5


def test_ignores_income_transactions(session):
    cat_repo, acct_repo, tx_repo = CategoryRepository(session), AccountRepository(session), TransactionRepository(session)
    category, account = cat_repo.get_by_name("Shopping"), acct_repo.get_or_create("Primary")

    _txn(tx_repo, category, account, d=date(2026, 9, 1), amount=50000.0, transaction_type=TransactionType.income)
    _txn(tx_repo, category, account, d=date(2026, 9, 1), amount=100.0)
    session.commit()

    result = calc.spending_pattern(session, date(2026, 9, 1), date(2026, 9, 30))

    total = sum(row["total"] for row in result["by_day_of_week"])
    assert total == 100.0


def test_empty_range_returns_zeroed_percentages_without_dividing_by_zero(session):
    result = calc.spending_pattern(session, date(2026, 9, 1), date(2026, 9, 30))
    assert all(row["pct"] == 0.0 for row in result["by_day_of_week"])
    assert all(row["pct"] == 0.0 for row in result["by_month_third"])
