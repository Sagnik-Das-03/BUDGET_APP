"""Integer-paise storage for rupee amounts - the canonical representation is
the INTEGER column in SQLite, never a float. Every other layer (repositories,
dashboard calculations, API schemas, the frontend, Sheets sync) keeps working
with a plain Python float in rupees; only the physical column changes, via
process_bind_param/process_result_value below.

Converting through Decimal(str(value)) rather than value * 100 matters for
ALREADY-EXISTING float data (see scripts/migrate_amounts_to_paise.py): a
stored float like 45.5 round-trips as "45.5" in str(), and Decimal("45.5")
is exact - whereas 45.5 * 100 can land on 4549.999999999999 or
4550.000000000001 for some values, silently corrupting the migration by a
paisa. New values entered through the app are typed in as "45.50" strings
by the frontend/CSV import anyway, so this is exact for them too.
"""
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import Integer
from sqlalchemy.types import TypeDecorator


class MoneyPaise(TypeDecorator):
    impl = Integer
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        paise = (Decimal(str(value)) * 100).to_integral_value(rounding=ROUND_HALF_UP)
        return int(paise)

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        return value / 100.0
