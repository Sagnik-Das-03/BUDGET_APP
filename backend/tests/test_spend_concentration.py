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


def test_top_n_share_of_total_spend(session):
    cat_repo, acct_repo, tx_repo = CategoryRepository(session), AccountRepository(session), TransactionRepository(session)
    category, account = cat_repo.get_by_name("Shopping"), acct_repo.get_or_create("Primary")

    for amount in [5000.0, 3000.0, 2000.0, 100.0, 50.0]:  # total 10150
        _txn(tx_repo, category, account, d=date(2026, 9, 5), amount=amount)
    session.commit()

    result = calc.spend_concentration(session, date(2026, 9, 1), date(2026, 9, 30), top_n=3)

    assert result["top_sum"] == 10000.0  # 5000+3000+2000
    assert result["total"] == 10150.0
    assert result["pct"] == round(10000.0 / 10150.0, 4)
    assert result["transaction_count"] == 5


def test_top_n_larger_than_transaction_count_just_uses_everything(session):
    cat_repo, acct_repo, tx_repo = CategoryRepository(session), AccountRepository(session), TransactionRepository(session)
    category, account = cat_repo.get_by_name("Shopping"), acct_repo.get_or_create("Primary")
    _txn(tx_repo, category, account, d=date(2026, 9, 5), amount=500.0)
    session.commit()

    result = calc.spend_concentration(session, date(2026, 9, 1), date(2026, 9, 30), top_n=3)

    assert result["top_sum"] == result["total"] == 500.0
    assert result["pct"] == 1.0


def test_excludes_non_expense_categories_and_income(session):
    cat_repo, acct_repo, tx_repo = CategoryRepository(session), AccountRepository(session), TransactionRepository(session)
    sip, shopping, account = cat_repo.get_by_name("SIP"), cat_repo.get_by_name("Shopping"), acct_repo.get_or_create("Primary")

    _txn(tx_repo, sip, account, d=date(2026, 9, 5), amount=50000.0)  # not a real expense
    _txn(tx_repo, shopping, account, d=date(2026, 9, 5), amount=100000.0, transaction_type=TransactionType.income)
    _txn(tx_repo, shopping, account, d=date(2026, 9, 5), amount=500.0)
    session.commit()

    result = calc.spend_concentration(session, date(2026, 9, 1), date(2026, 9, 30))

    assert result["total"] == 500.0
    assert result["transaction_count"] == 1


def test_empty_range_returns_zero_without_dividing_by_zero(session):
    result = calc.spend_concentration(session, date(2026, 9, 1), date(2026, 9, 30))
    assert result == {"top_n": 3, "top_sum": 0.0, "total": 0.0, "pct": 0.0, "transaction_count": 0}
