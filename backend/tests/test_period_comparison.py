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


def test_net_delta_abs_stays_sane_when_the_previous_period_swings_from_a_loss_to_a_gain(session):
    """Regression test: a previous period with a small negative net (a losing
    week) swinging to a large positive net produced a nonsensical percentage
    (e.g. 5,939%) via net_delta_pct, since percentage-of-a-near-zero-or-
    negative baseline is meaningless. net_delta_abs (a plain rupee
    difference) should read as a sane, well-defined number regardless."""
    cat_repo, acct_repo, tx_repo = CategoryRepository(session), AccountRepository(session), TransactionRepository(session)
    shopping, account = cat_repo.get_by_name("Shopping"), acct_repo.get_or_create("Primary")

    # Previous week (Mon 2026-08-31 .. Sun 2026-09-06): a small net loss
    _txn(tx_repo, shopping, account, d=date(2026, 9, 1), amount=1008.08)
    # Current week (Mon 2026-09-07 .. Sun 2026-09-13): a big net gain
    _txn(tx_repo, shopping, account, d=date(2026, 9, 8), amount=1000.0, transaction_type=TransactionType.income)
    session.commit()

    result = calc.period_comparison(session, "this_week", date(2026, 9, 7), date(2026, 9, 13))

    assert result["net_delta_abs"] == 1000.0 - (-1008.08)
    # The old percentage figure is still exposed (some callers may still want
    # it for genuinely positive baselines) but is documented as unreliable
    # near zero/negative - not asserting a specific value here, just that it
    # doesn't crash and net_delta_abs is what the UI should actually show.
    assert isinstance(result["net_delta_pct"], float)


def test_net_delta_abs_is_a_plain_rupee_difference_in_the_ordinary_case(session):
    cat_repo, acct_repo, tx_repo = CategoryRepository(session), AccountRepository(session), TransactionRepository(session)
    shopping, account = cat_repo.get_by_name("Shopping"), acct_repo.get_or_create("Primary")

    _txn(tx_repo, shopping, account, d=date(2026, 8, 5), amount=1000.0, transaction_type=TransactionType.expense)
    _txn(tx_repo, shopping, account, d=date(2026, 8, 5), amount=5000.0, transaction_type=TransactionType.income)  # last month net = 4000
    _txn(tx_repo, shopping, account, d=date(2026, 9, 5), amount=1000.0, transaction_type=TransactionType.expense)
    _txn(tx_repo, shopping, account, d=date(2026, 9, 5), amount=6000.0, transaction_type=TransactionType.income)  # this month net = 5000
    session.commit()

    result = calc.period_comparison(session, "this_month", date(2026, 9, 1), date(2026, 9, 30))

    assert result["net_delta_abs"] == 1000.0
    assert result["net_delta_pct"] == 0.25
