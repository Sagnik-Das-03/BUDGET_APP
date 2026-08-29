from datetime import date as date_type
from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_session
from app.dashboard import calculations as calc
from app.repositories.savings_goal import SavingsGoalRepository
from app.schemas import SavingsGoalIn
from app.utils import period_key_for

router = APIRouter(prefix="/api/savings_goal", tags=["savings_goal"])


@router.get("")
def get_goal(period_key: Optional[str] = None, session: Session = Depends(get_session)):
    pk = period_key or period_key_for(date_type.today())
    return {"period_key": pk, "goal_amount": SavingsGoalRepository(session).for_period(pk)}


@router.post("")
def set_goal(payload: SavingsGoalIn, session: Session = Depends(get_session)):
    goal = SavingsGoalRepository(session).set_goal(payload.goal_amount, payload.period_key)
    session.commit()
    return {"period_key": goal.period_key, "goal_amount": goal.goal_amount}


@router.delete("")
def clear_goal(period_key: Optional[str] = None, session: Session = Depends(get_session)):
    cleared = SavingsGoalRepository(session).clear_goal(period_key)
    session.commit()
    return {"ok": True, "cleared": cleared}


@router.get("/progress")
def progress(period_key: Optional[str] = None, session: Session = Depends(get_session)):
    pk = period_key or period_key_for(date_type.today())
    return calc.savings_goal_progress(session, pk) or {"goal": None}
