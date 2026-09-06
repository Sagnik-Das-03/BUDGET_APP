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


def test_splits_essential_and_discretionary_by_category_flag(session):
    cat_repo, acct_repo, tx_repo = CategoryRepository(session), AccountRepository(session), TransactionRepository(session)
    account = acct_repo.get_or_create("Primary")
    rent, shopping = cat_repo.get_by_name("RENT"), cat_repo.get_by_name("Shopping")
    assert rent.is_essential is True
    assert shopping.is_essential is False

    _txn(tx_repo, rent, account, d=date(2026, 9, 1), amount=25500.0)
    _txn(tx_repo, shopping, account, d=date(2026, 9, 5), amount=4500.0)
    session.commit()

    result = calc.essential_vs_discretionary(session, date(2026, 9, 1), date(2026, 9, 30))

    assert result["essential"] == 25500.0
    assert result["discretionary"] == 4500.0
    assert result["essential_pct"] == round(25500.0 / 30000.0, 4)
    assert result["essential_categories"] == [{"category": "RENT", "total": 25500.0}]
    assert result["discretionary_categories"] == [{"category": "Shopping", "total": 4500.0}]


def test_category_breakdown_is_sorted_by_amount_descending(session):
    cat_repo, acct_repo, tx_repo = CategoryRepository(session), AccountRepository(session), TransactionRepository(session)
    account = acct_repo.get_or_create("Primary")
    shopping, food, quick = cat_repo.get_by_name("Shopping"), cat_repo.get_by_name("Food-Order"), cat_repo.get_by_name("Quick-Commerce")

    _txn(tx_repo, shopping, account, d=date(2026, 9, 1), amount=500.0)
    _txn(tx_repo, food, account, d=date(2026, 9, 2), amount=2000.0)
    _txn(tx_repo, quick, account, d=date(2026, 9, 3), amount=1000.0)
    session.commit()

    result = calc.essential_vs_discretionary(session, date(2026, 9, 1), date(2026, 9, 30))

    assert [r["category"] for r in result["discretionary_categories"]] == ["Food-Order", "Quick-Commerce", "Shopping"]


def test_excludes_categories_that_do_not_count_as_expense(session):
    """SIP is is_essential=True in the defaults, but counts_as_expense=False -
    a SIP contribution must not leak into the essential total, since it's
    not a real expense at all."""
    cat_repo, acct_repo, tx_repo = CategoryRepository(session), AccountRepository(session), TransactionRepository(session)
    account = acct_repo.get_or_create("Primary")
    sip = cat_repo.get_by_name("SIP")
    assert sip.is_essential is True
    assert sip.counts_as_expense is False

    _txn(tx_repo, sip, account, d=date(2026, 9, 1), amount=5000.0)
    session.commit()

    result = calc.essential_vs_discretionary(session, date(2026, 9, 1), date(2026, 9, 30))

    assert result["essential"] == 0.0
    assert result["discretionary"] == 0.0


def test_empty_range_returns_zeroed_percentages(session):
    result = calc.essential_vs_discretionary(session, date(2026, 9, 1), date(2026, 9, 30))
    assert result == {
        "essential": 0.0, "discretionary": 0.0, "essential_pct": 0.0, "discretionary_pct": 0.0,
        "essential_categories": [], "discretionary_categories": [],
    }
