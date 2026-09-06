from datetime import date

from app.dashboard import calculations as calc
from app.models import TransactionType
from app.repositories.accounts import AccountRepository
from app.repositories.categories import CategoryRepository
from app.repositories.transactions import TransactionRepository


def _txn(tx_repo, category, account, *, day, amount):
    return tx_repo.create(
        date=date(2026, 9, day), description=f"txn-{day}", amount=amount,
        transaction_type=TransactionType.expense, category=category, account=account,
    )


def test_flags_a_transaction_well_above_its_categorys_own_history(session):
    cat_repo, acct_repo, tx_repo = CategoryRepository(session), AccountRepository(session), TransactionRepository(session)
    category, account = cat_repo.get_by_name("Shopping"), acct_repo.get_or_create("Primary")

    # baseline: several ordinary ~250 purchases before the window
    for day in range(1, 6):
        _txn(tx_repo, category, account, day=day, amount=250.0)
    session.commit()

    # one big outlier inside the window being checked
    spike = _txn(tx_repo, category, account, day=10, amount=900.0)
    session.commit()

    result = calc.detect_anomalies(session, date(2026, 9, 8), date(2026, 9, 15))

    assert len(result) == 1
    assert result[0]["transaction_id"] == spike.transaction_id
    assert result[0]["category"] == "Shopping"
    assert result[0]["category_avg"] == 250.0
    assert result[0]["multiple"] == 3.6


def test_does_not_flag_a_category_with_too_little_history(session):
    """Only 2 prior transactions - below min_history=3 - so no baseline exists
    yet and nothing in this category can be called "unusual" relative to it."""
    cat_repo, acct_repo, tx_repo = CategoryRepository(session), AccountRepository(session), TransactionRepository(session)
    category, account = cat_repo.get_by_name("Shopping"), acct_repo.get_or_create("Primary")

    _txn(tx_repo, category, account, day=1, amount=250.0)
    _txn(tx_repo, category, account, day=2, amount=250.0)
    session.commit()
    _txn(tx_repo, category, account, day=10, amount=900.0)
    session.commit()

    result = calc.detect_anomalies(session, date(2026, 9, 8), date(2026, 9, 15))
    assert result == []


def test_does_not_flag_ordinary_spending_within_normal_range(session):
    cat_repo, acct_repo, tx_repo = CategoryRepository(session), AccountRepository(session), TransactionRepository(session)
    category, account = cat_repo.get_by_name("Shopping"), acct_repo.get_or_create("Primary")

    for day in range(1, 6):
        _txn(tx_repo, category, account, day=day, amount=250.0)
    session.commit()
    _txn(tx_repo, category, account, day=10, amount=280.0)  # unremarkable
    session.commit()

    result = calc.detect_anomalies(session, date(2026, 9, 8), date(2026, 9, 15))
    assert result == []


def test_ignores_a_small_absolute_gap_even_if_the_multiple_is_high(session):
    """A category whose baseline is tiny (e.g. ₹10) could have a "5x" transaction
    that's still only ₹50 - not worth flagging as a notable anomaly."""
    cat_repo, acct_repo, tx_repo = CategoryRepository(session), AccountRepository(session), TransactionRepository(session)
    category, account = cat_repo.get_by_name("Shopping"), acct_repo.get_or_create("Primary")

    for day in range(1, 6):
        _txn(tx_repo, category, account, day=day, amount=10.0)
    session.commit()
    _txn(tx_repo, category, account, day=10, amount=50.0)  # 5x baseline, but only +₹40
    session.commit()

    result = calc.detect_anomalies(session, date(2026, 9, 8), date(2026, 9, 15))
    assert result == []


def test_baseline_excludes_transactions_from_the_window_itself(session):
    """The spike being evaluated must never count toward its own baseline -
    otherwise a big-enough spike could inflate the average enough to hide itself."""
    cat_repo, acct_repo, tx_repo = CategoryRepository(session), AccountRepository(session), TransactionRepository(session)
    category, account = cat_repo.get_by_name("Shopping"), acct_repo.get_or_create("Primary")

    for day in range(1, 6):
        _txn(tx_repo, category, account, day=day, amount=250.0)
    session.commit()
    spike = _txn(tx_repo, category, account, day=10, amount=900.0)
    session.commit()

    # window includes the spike's own date - it must not contaminate the baseline
    result = calc.detect_anomalies(session, date(2026, 9, 6), date(2026, 9, 12))
    assert len(result) == 1
    assert result[0]["transaction_id"] == spike.transaction_id
    assert result[0]["category_avg"] == 250.0
