from sqlalchemy import select
from sqlalchemy.orm import Session
from typing import Optional

from app.models import SavingsGoal


class SavingsGoalRepository:
    def __init__(self, session: Session):
        self.session = session

    def for_period(self, period_key: str) -> Optional[float]:
        """Period-specific goal if set, else the recurring monthly default, else None."""
        specific = self.session.scalar(select(SavingsGoal).where(SavingsGoal.period_key == period_key))
        if specific:
            return specific.goal_amount
        default = self.session.scalar(select(SavingsGoal).where(SavingsGoal.period_key.is_(None)))
        return default.goal_amount if default else None

    def set_goal(self, goal_amount: float, period_key: Optional[str] = None) -> SavingsGoal:
        existing = self.session.scalar(select(SavingsGoal).where(SavingsGoal.period_key == period_key))
        if existing:
            existing.goal_amount = goal_amount
            self.session.flush()
            return existing
        goal = SavingsGoal(period_key=period_key, goal_amount=goal_amount)
        self.session.add(goal)
        self.session.flush()
        return goal

    def clear_goal(self, period_key: Optional[str] = None) -> bool:
        existing = self.session.scalar(select(SavingsGoal).where(SavingsGoal.period_key == period_key))
        if not existing:
            return False
        self.session.delete(existing)
        self.session.flush()
        return True
