from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Category
from typing import Optional

# Default seed set - includes the expansion agreed on during setup (Transport/Utilities
# split out of the old catch-all "Subscriptions" bucket) and the savings/expense split
# agreed on afterward: SIP and Savings are money that's still yours (invested, or sent
# to family as pooled household savings) so they're excluded from the Expenses/Net
# Savings KPI; Gift is for one-way support payments that behave like a real expense.
# (name, color, counts_as_expense)
DEFAULT_CATEGORIES = [
    ("Income", "#2A78D6", True),
    ("Subscriptions", "#EB6834", True),
    ("Quick-Commerce", "#1BAF7A", True),
    ("Shopping", "#EDA100", True),
    ("Food-Order", "#E87BA4", True),
    ("SIP", "#008300", False),
    ("Savings", "#0CA30C", False),
    ("Gift", "#E87BA4", True),
    ("RENT", "#4A3AA7", True),
    ("Transport", "#9085E9", True),
    ("Utilities", "#199E70", True),
    ("Other", "#E34948", True),
]


class CategoryRepository:
    def __init__(self, session: Session):
        self.session = session

    def list(self, include_inactive: bool = False) -> list[Category]:
        stmt = select(Category).order_by(Category.name)
        if not include_inactive:
            stmt = stmt.where(Category.is_active.is_(True))
        return list(self.session.scalars(stmt))

    def get_by_name(self, name: str) -> Optional[Category]:
        return self.session.scalar(select(Category).where(Category.name == name))

    def get_or_create(self, name: str, color_hex: str = "#898781", counts_as_expense: bool = True) -> Category:
        cat = self.get_by_name(name)
        if cat:
            return cat
        cat = Category(name=name, color_hex=color_hex, is_active=True, counts_as_expense=counts_as_expense)
        self.session.add(cat)
        self.session.flush()
        return cat

    def add(self, name: str, color_hex: str = "#898781") -> Category:
        existing = self.get_by_name(name)
        if existing:
            if not existing.is_active:
                existing.is_active = True
            return existing
        return self.get_or_create(name, color_hex)

    def rename(self, category_id: int, new_name: str) -> Optional[Category]:
        cat = self.session.get(Category, category_id)
        if not cat:
            return None
        cat.name = new_name
        self.session.flush()
        return cat

    def set_color(self, category_id: int, color_hex: str) -> Optional[Category]:
        cat = self.session.get(Category, category_id)
        if not cat:
            return None
        cat.color_hex = color_hex
        self.session.flush()
        return cat

    def set_counts_as_expense(self, category_id: int, counts_as_expense: bool) -> Optional[Category]:
        cat = self.session.get(Category, category_id)
        if not cat:
            return None
        cat.counts_as_expense = counts_as_expense
        self.session.flush()
        return cat

    def deactivate(self, category_id: int) -> Optional[Category]:
        cat = self.session.get(Category, category_id)
        if not cat:
            return None
        cat.is_active = False
        self.session.flush()
        return cat

    def ensure_defaults(self) -> None:
        for name, color, counts_as_expense in DEFAULT_CATEGORIES:
            cat = self.get_or_create(name, color, counts_as_expense)
            if cat.counts_as_expense != counts_as_expense:
                cat.counts_as_expense = counts_as_expense
