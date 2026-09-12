from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.db import create_empty_db, session_for, switch_active_db
from app.demo_data import seed_demo_data
from app.repositories.accounts import AccountRepository
from app.repositories.categories import CategoryRepository
from app.user_registry import registry

router = APIRouter(prefix="/api/users", tags=["users"])


class UserOut(BaseModel):
    username: str
    is_active: bool


class CreateUserIn(BaseModel):
    username: str = Field(min_length=1, max_length=32, pattern=r"^[A-Za-z0-9_-]+$")
    seed_demo_data: bool = False


@router.get("", response_model=list[UserOut])
def list_users():
    active = registry.get_active()
    return [UserOut(username=u["username"], is_active=u["username"] == active) for u in registry.list_users()]


@router.post("", response_model=UserOut)
def create_user(payload: CreateUserIn):
    if registry.exists(payload.username):
        raise HTTPException(409, f"User {payload.username!r} already exists")

    db_file = f"{payload.username.lower()}.db"
    # Seeded via a throwaway engine bound to the new file - this must NOT
    # touch the currently active user's engine/session, since creating a
    # user is not the same as switching into it.
    create_empty_db(db_file)
    session = session_for(db_file)
    try:
        CategoryRepository(session).ensure_defaults()
        AccountRepository(session).ensure_default()
        if payload.seed_demo_data:
            seed_demo_data(session)
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

    registry.add_user(payload.username, db_file)
    return UserOut(username=payload.username, is_active=registry.get_active() == payload.username)


@router.post("/{username}/activate", response_model=UserOut)
def activate_user(username: str):
    db_file = registry.get_db_file(username)
    if not db_file:
        raise HTTPException(404, f"User {username!r} not found")
    switch_active_db(db_file)
    registry.set_active(username)
    return UserOut(username=username, is_active=True)
