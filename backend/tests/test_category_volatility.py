from datetime import date

from app.dashboard import calculations as calc
from app.models import TransactionType
from app.repositories.accounts import AccountRepository
from app.repositories.categories import CategoryRepository
from app.repositories.transactions import TransactionRepository
from app.utils import period_key_for


def _txn(tx_repo, category, account, *, d, amount):
    return tx_repo.create(
        date=d, description="txn", amount=amount,
        transaction_type=TransactionType.expense, category=category, account=account,
    )


def _months_ago(n):
    """The 5th of the month `n` full calendar months before the current one -
    keeps this test's fixtures correct regardless of what 'today' actually is
    when the suite runs, since category_volatility() windows off real today()."""
    today = date.today()
    year, month = today.year, today.month
    for _ in range(n):
        month -= 1
        if month == 0:
            month, year = 12, year - 1
    return date(year, month, 5)


def test_flags_a_perfectly_steady_category_as_stable(session):
    cat_repo, acct_repo, tx_repo = CategoryRepository(session), AccountRepository(session), TransactionRepository(session)
    rent, account = cat_repo.get_or_create("Rent"), acct_repo.get_or_create("Primary")

    for n in range(1, 5):
        _txn(tx_repo, rent, account, d=_months_ago(n), amount=25500.0)
    session.commit()

    result = calc.category_volatility(session, months=6)

    row = next(r for r in result if r["category"] == "Rent")
    assert row["coefficient_of_variation"] == 0.0
    assert row["status"] == "stable"
    assert row["months_observed"] == 4


def test_flags_a_wildly_swinging_category_as_volatile(session):
    cat_repo, acct_repo, tx_repo = CategoryRepository(session), AccountRepository(session), TransactionRepository(session)
    shopping, account = cat_repo.get_by_name("Shopping"), acct_repo.get_or_create("Primary")

    for n, amount in zip(range(1, 5), [100.0, 5000.0, 200.0, 4800.0]):
        _txn(tx_repo, shopping, account, d=_months_ago(n), amount=amount)
    session.commit()

    result = calc.category_volatility(session, months=6)

    row = next(r for r in result if r["category"] == "Shopping")
    assert row["status"] == "volatile"


def test_excludes_a_category_with_too_little_history(session):
    cat_repo, acct_repo, tx_repo = CategoryRepository(session), AccountRepository(session), TransactionRepository(session)
    shopping, account = cat_repo.get_by_name("Shopping"), acct_repo.get_or_create("Primary")

    _txn(tx_repo, shopping, account, d=_months_ago(1), amount=500.0)
    _txn(tx_repo, shopping, account, d=_months_ago(2), amount=500.0)
    session.commit()

    result = calc.category_volatility(session, months=6, min_months=3)

    assert not any(r["category"] == "Shopping" for r in result)


def test_excludes_the_in_progress_current_month(session):
    """Today's date falls mid-month for a still-accumulating total - counting
    it alongside fully-elapsed months would make every category look like it
    'dropped' this period even though the month simply isn't over yet."""
    cat_repo, acct_repo, tx_repo = CategoryRepository(session), AccountRepository(session), TransactionRepository(session)
    shopping, account = cat_repo.get_by_name("Shopping"), acct_repo.get_or_create("Primary")

    for n in range(1, 4):
        _txn(tx_repo, shopping, account, d=_months_ago(n), amount=1000.0)
    _txn(tx_repo, shopping, account, d=date.today(), amount=1.0)  # this month - should be ignored
    session.commit()

    result = calc.category_volatility(session, months=6)

    row = next(r for r in result if r["category"] == "Shopping")
    assert row["months_observed"] == 3
    assert row["coefficient_of_variation"] == 0.0


def test_excludes_non_expense_categories_like_sip(session):
    cat_repo, acct_repo, tx_repo = CategoryRepository(session), AccountRepository(session), TransactionRepository(session)
    sip, account = cat_repo.get_by_name("SIP"), acct_repo.get_or_create("Primary")
    assert sip.counts_as_expense is False

    for n in range(1, 5):
        _txn(tx_repo, sip, account, d=_months_ago(n), amount=1000.0 * n)  # would otherwise look "volatile"
    session.commit()

    result = calc.category_volatility(session, months=6)

    assert not any(r["category"] == "SIP" for r in result)


def test_uses_period_key_for_to_bucket_months_consistently_with_the_rest_of_the_app(session):
    cat_repo, acct_repo, tx_repo = CategoryRepository(session), AccountRepository(session), TransactionRepository(session)
    shopping, account = cat_repo.get_by_name("Shopping"), acct_repo.get_or_create("Primary")
    d = _months_ago(1)
    _txn(tx_repo, shopping, account, d=d, amount=100.0)
    session.commit()

    result = calc.category_volatility(session, months=6, min_months=1)

    row = next(r for r in result if r["category"] == "Shopping")
    assert row["months_observed"] == 1
    # sanity: the bucketing period key matches the transaction's own month
    assert period_key_for(d) == f"{d.year}-{d.month:02d}"
