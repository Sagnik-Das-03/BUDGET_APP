from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Budget, Category
from typing import Optional


class BudgetRepository:
    def __init__(self, session: Session):
        self.session = session

    def list(self) -> list[Budget]:
        return list(self.session.scalars(select(Budget)))

    def for_period(self, period_key: str) -> dict[str, float]:
        """Returns {category_name: goal_amount} for a period, falling back to the
        recurring monthly default (period_key IS NULL) when no period-specific goal exists."""
        specific = {
            b.category.name: b.goal_amount
            for b in self.session.scalars(select(Budget).where(Budget.period_key == period_key))
        }
        defaults = {
            b.category.name: b.goal_amount
            for b in self.session.scalars(select(Budget).where(Budget.period_key.is_(None)))
        }
        return {**defaults, **specific}

    def set_goal(self, category: Category, goal_amount: float, period_key: Optional[str] = None) -> Budget:
        existing = self.session.scalar(
            select(Budget).where(Budget.category_id == category.id, Budget.period_key == period_key)
        )
        if existing:
            existing.goal_amount = goal_amount
            self.session.flush()
            return existing
        budget = Budget(category_id=category.id, period_key=period_key, goal_amount=goal_amount)
        self.session.add(budget)
        self.session.flush()
        return budget

    def clear_goal(self, category: Category, period_key: Optional[str] = None) -> bool:
        existing = self.session.scalar(
            select(Budget).where(Budget.category_id == category.id, Budget.period_key == period_key)
        )
        if not existing:
            return False
        self.session.delete(existing)
        self.session.flush()
        return True
