from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Category
from typing import Optional

# Default seed set - includes the expansion agreed on during setup (Transport/Utilities
# split out of the old catch-all "Subscriptions" bucket) and the savings/expense split
# agreed on afterward: SIP and Savings are money that's still yours (invested, or sent
# to family as pooled household savings) so they're excluded from the Expenses/Net
# Savings KPI; Gift is for one-way support payments that behave like a real expense.
#
# Colors: an 11-hue modern categorical set (validated with the dataviz skill's
# validate_palette.js against both the light #fcfcfb and dark #1c1b19 chart
# surfaces - passes lightness band, chroma floor, adjacent CVD separation and
# contrast as one set in both modes; the CVD check WARNs on one pair in the 6-8
# floor band, which is legal here since every category name is always shown as
# a direct label next to its swatch). "Other" is deliberately excluded from that
# set and kept as neutral muted ink, same precedent as the chart palette's "goal"
# color - a catch-all bucket doesn't need to compete for hue distinctiveness.
# (name, color, counts_as_expense)
DEFAULT_CATEGORIES = [
    ("Income", "#3B82F6", True),
    ("Subscriptions", "#8B5CF6", True),
    ("Quick-Commerce", "#0891B2", True),
    ("Shopping", "#D97706", True),
    ("Food-Order", "#EC4899", True),
    ("SIP", "#65A30D", False),
    ("Savings", "#0D9488", False),
    ("Gift", "#D946EF", True),
    ("RENT", "#F43F5E", True),
    ("Transport", "#6366F1", True),
    ("Utilities", "#EA580C", True),
    ("Other", "#898781", True),
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
