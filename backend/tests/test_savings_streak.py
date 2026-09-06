from datetime import date

from app.dashboard import calculations as calc
from app.models import TransactionType
from app.repositories.accounts import AccountRepository
from app.repositories.categories import CategoryRepository
from app.repositories.transactions import TransactionRepository


def _txn(tx_repo, category, account, *, d, amount, transaction_type):
    return tx_repo.create(
        date=d, description="txn", amount=amount,
        transaction_type=transaction_type, category=category, account=account,
    )


def _month(tx_repo, category, account, year, month, income, expenses):
    _txn(tx_repo, category, account, d=date(year, month, 1), amount=income, transaction_type=TransactionType.income)
    _txn(tx_repo, category, account, d=date(year, month, 2), amount=expenses, transaction_type=TransactionType.expense)


def test_counts_consecutive_positive_months_back_from_the_most_recent_closed_month(session):
    cat_repo, acct_repo, tx_repo = CategoryRepository(session), AccountRepository(session), TransactionRepository(session)
    shopping, account = cat_repo.get_by_name("Shopping"), acct_repo.get_or_create("Primary")

    _month(tx_repo, shopping, account, 2026, 5, income=1000, expenses=2000)  # loss - breaks any earlier streak
    _month(tx_repo, shopping, account, 2026, 6, income=2000, expenses=1000)  # +1000
    _month(tx_repo, shopping, account, 2026, 7, income=2000, expenses=1000)  # +1000
    _month(tx_repo, shopping, account, 2026, 8, income=2000, expenses=1000)  # +1000
    session.commit()

    # "as_of" September - so June/July/August are the 3 most recent CLOSED months
    result = calc.savings_streak(session, as_of=date(2026, 9, 6))

    assert result["current_streak_months"] == 3
    assert result["months_observed"] == 4


def test_streak_is_zero_when_the_most_recent_closed_month_was_a_loss(session):
    cat_repo, acct_repo, tx_repo = CategoryRepository(session), AccountRepository(session), TransactionRepository(session)
    shopping, account = cat_repo.get_by_name("Shopping"), acct_repo.get_or_create("Primary")

    _month(tx_repo, shopping, account, 2026, 7, income=2000, expenses=1000)
    _month(tx_repo, shopping, account, 2026, 8, income=1000, expenses=2000)  # loss
    session.commit()

    result = calc.savings_streak(session, as_of=date(2026, 9, 6))

    assert result["current_streak_months"] == 0


def test_best_streak_can_exceed_the_current_one(session):
    cat_repo, acct_repo, tx_repo = CategoryRepository(session), AccountRepository(session), TransactionRepository(session)
    shopping, account = cat_repo.get_by_name("Shopping"), acct_repo.get_or_create("Primary")

    _month(tx_repo, shopping, account, 2026, 3, income=2000, expenses=1000)
    _month(tx_repo, shopping, account, 2026, 4, income=2000, expenses=1000)
    _month(tx_repo, shopping, account, 2026, 5, income=2000, expenses=1000)  # a 3-month run, now broken
    _month(tx_repo, shopping, account, 2026, 6, income=1000, expenses=2000)  # loss
    _month(tx_repo, shopping, account, 2026, 7, income=2000, expenses=1000)  # current run of 1
    session.commit()

    result = calc.savings_streak(session, as_of=date(2026, 8, 6))

    assert result["current_streak_months"] == 1
    assert result["best_streak_months"] == 3


def test_excludes_the_in_progress_current_month(session):
    """A partial current-month total shouldn't be able to end (or extend) a
    streak just because it isn't finished yet."""
    cat_repo, acct_repo, tx_repo = CategoryRepository(session), AccountRepository(session), TransactionRepository(session)
    shopping, account = cat_repo.get_by_name("Shopping"), acct_repo.get_or_create("Primary")

    _month(tx_repo, shopping, account, 2026, 8, income=2000, expenses=1000)  # closed, positive
    _txn(tx_repo, shopping, account, d=date(2026, 9, 6), amount=100000.0, transaction_type=TransactionType.expense)  # in-progress Sept, big loss
    session.commit()

    result = calc.savings_streak(session, as_of=date(2026, 9, 6))

    assert result["current_streak_months"] == 1
    assert result["months_observed"] == 1
