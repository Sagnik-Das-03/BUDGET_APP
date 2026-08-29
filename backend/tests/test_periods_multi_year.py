from datetime import date

from app.models import MonthlyPeriod, TransactionType
from app.repositories.accounts import AccountRepository
from app.repositories.categories import CategoryRepository
from app.repositories.transactions import TransactionRepository
from app.sync.periods import discover_sheet_periods, ensure_periods_for_transactions
from app.utils import period_key_for, week_key_for, year_key_for
from sqlalchemy import select


def test_period_keys_do_not_collide_across_years():
    assert period_key_for(date(2026, 4, 15)) == "2026-04"
    assert period_key_for(date(2027, 4, 15)) == "2027-04"
    assert period_key_for(date(2026, 4, 15)) != period_key_for(date(2027, 4, 15))


def test_week_and_year_keys_are_distinct_across_years():
    assert year_key_for(date(2026, 1, 1)) == "2026"
    assert year_key_for(date(2030, 1, 1)) == "2030"
    assert week_key_for(date(2026, 8, 24)) != week_key_for(date(2027, 8, 24))


def test_ensure_periods_registers_every_year_seen_in_transactions(session):
    cat_repo, acct_repo, tx_repo = CategoryRepository(session), AccountRepository(session), TransactionRepository(session)
    category, account = cat_repo.get_by_name("Shopping"), acct_repo.get_or_create("Primary")

    for d in [date(2026, 4, 1), date(2027, 4, 1), date(2028, 12, 1), date(2030, 1, 1)]:
        tx_repo.create(date=d, description="x", amount=1, transaction_type=TransactionType.expense,
                        category=category, account=account)
    session.commit()

    keys = ensure_periods_for_transactions(session)
    assert set(keys) == {"2026-04", "2027-04", "2028-12", "2030-01"}

    periods = list(session.scalars(select(MonthlyPeriod)))
    assert {p.period_key for p in periods} == set(keys)
    labels = {p.period_key: p.label for p in periods}
    assert labels["2026-04"] == "April 2026"
    assert labels["2027-04"] == "April 2027"  # same month name, different year - must not collide


def test_discover_sheet_periods_does_not_duplicate_manually_created_tabs(session, sheets):
    sheets.ensure_sheet("fake-id", "2029-06")
    discovered = discover_sheet_periods(session, sheets, "fake-id")
    assert discovered == ["2029-06"]

    # running discovery again must not re-register or duplicate it
    discovered_again = discover_sheet_periods(session, sheets, "fake-id")
    assert discovered_again == []
    periods = list(session.scalars(select(MonthlyPeriod)))
    assert len([p for p in periods if p.period_key == "2029-06"]) == 1
