from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import Optional

from app.db import get_session
from app.repositories.budgets import BudgetRepository
from app.repositories.categories import CategoryRepository
from app.schemas import BudgetIn

router = APIRouter(prefix="/api/budgets", tags=["budgets"])


@router.get("")
def list_budgets(session: Session = Depends(get_session)):
    budgets = BudgetRepository(session).list()
    return [{"category": b.category.name, "period_key": b.period_key, "goal_amount": b.goal_amount} for b in budgets]


@router.post("")
def set_budget(payload: BudgetIn, session: Session = Depends(get_session)):
    cat_repo = CategoryRepository(session)
    category = cat_repo.get_by_name(payload.category)
    if not category:
        raise HTTPException(404, f"Category {payload.category!r} not found")
    budget = BudgetRepository(session).set_goal(category, payload.goal_amount, payload.period_key)
    session.commit()
    return {"category": category.name, "period_key": budget.period_key, "goal_amount": budget.goal_amount}


@router.delete("/{category_name}")
def clear_budget(category_name: str, period_key: Optional[str] = None, session: Session = Depends(get_session)):
    cat_repo = CategoryRepository(session)
    category = cat_repo.get_by_name(category_name)
    if not category:
        raise HTTPException(404, f"Category {category_name!r} not found")
    cleared = BudgetRepository(session).clear_goal(category, period_key)
    session.commit()
    return {"ok": True, "cleared": cleared}
