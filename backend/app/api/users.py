from typing import Optional

from fastapi import APIRouter, Body, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from app.db import create_empty_db, db_file_size, delete_db_file, session_for, switch_active_db
from app.demo_data import seed_demo_data
from app.models import Transaction
from app.repositories.accounts import AccountRepository
from app.repositories.categories import CategoryRepository
from app.user_registry import ADMIN_USERNAME, registry

router = APIRouter(prefix="/api/users", tags=["users"])


class UserOut(BaseModel):
    username: str
    is_active: bool
    db_size_bytes: int
    has_password: bool


class CreateUserIn(BaseModel):
    username: str = Field(min_length=1, max_length=32, pattern=r"^[A-Za-z0-9_-]+$")
    password: str = Field(min_length=4, max_length=128)
    seed_demo_data: bool = False
    # Only required/checked once an "admin" user exists AND has a password of
    # its own set - see _require_admin(). Bootstrapping a fresh install (no
    # admin yet, or an admin with no password configured) stays open, the
    # same "not locked until deliberately configured" rule as user passwords.
    admin_password: Optional[str] = None


class ActivateIn(BaseModel):
    password: Optional[str] = None


class SetPasswordIn(BaseModel):
    old_password: Optional[str] = None
    new_password: str = Field(min_length=4, max_length=128)


class UserStatOut(BaseModel):
    username: str
    is_active: bool
    db_size_bytes: int
    transaction_count: int
    has_password: bool


class UserStatsOut(BaseModel):
    total_users: int
    total_size_bytes: int
    total_transactions: int
    users_with_password: int
    users: list[UserStatOut]


def _require_admin(admin_password: Optional[str]) -> None:
    """Gates user create/delete to whoever knows the admin account's
    password - independent of which profile happens to be active right now,
    since switching profiles just to perform an admin action would be
    backwards. Open (no check) until an "admin" user actually exists and has
    a password set - see the module docstring in user_registry.py for why
    that's the right default for a personal app being retrofitted with this,
    rather than locking out a setup that never configured it."""
    if not registry.exists(ADMIN_USERNAME) or not registry.has_password(ADMIN_USERNAME):
        return
    if not admin_password:
        raise HTTPException(403, "Admin password required")
    if not registry.verify_password(ADMIN_USERNAME, admin_password):
        raise HTTPException(403, "Incorrect admin password")


def _to_out(entry: dict, active: str) -> UserOut:
    return UserOut(
        username=entry["username"], is_active=entry["username"] == active,
        db_size_bytes=db_file_size(entry["db_file"]), has_password=bool(entry.get("password_hash")),
    )


@router.get("", response_model=list[UserOut])
def list_users():
    active = registry.get_active()
    return [_to_out(u, active) for u in registry.list_users()]


@router.get("/stats", response_model=UserStatsOut)
def user_stats():
    """Admin view: per-user disk usage and transaction count, plus top-level
    totals - each user's count comes from a throwaway session against their
    own file, not the currently active one."""
    active = registry.get_active()
    users = registry.list_users()
    out = []
    for u in users:
        with session_for(u["db_file"]) as session:
            count = session.scalar(
                select(func.count()).select_from(Transaction).where(Transaction.deleted_at.is_(None))
            ) or 0
        out.append(UserStatOut(
            username=u["username"], is_active=u["username"] == active,
            db_size_bytes=db_file_size(u["db_file"]), transaction_count=count,
            has_password=bool(u.get("password_hash")),
        ))
    return UserStatsOut(
        total_users=len(out), total_size_bytes=sum(u.db_size_bytes for u in out),
        total_transactions=sum(u.transaction_count for u in out),
        users_with_password=sum(1 for u in out if u.has_password),
        users=out,
    )


@router.post("", response_model=UserOut)
def create_user(payload: CreateUserIn):
    _require_admin(payload.admin_password)
    if registry.exists(payload.username):
        raise HTTPException(409, f"User {payload.username!r} already exists")

    db_file = f"{payload.username.lower()}.db"
    # Seeded via a throwaway engine bound to the new file - this must NOT
    # touch the currently active user's engine/session, since creating a
    # user is not the same as switching into it.
    create_empty_db(db_file)
    with session_for(db_file) as session:
        try:
            CategoryRepository(session).ensure_defaults()
            AccountRepository(session).ensure_default()
            if payload.seed_demo_data:
                seed_demo_data(session)
            session.commit()
        except Exception:
            session.rollback()
            raise

    registry.add_user(payload.username, db_file, payload.password)
    return UserOut(
        username=payload.username, is_active=registry.get_active() == payload.username,
        db_size_bytes=db_file_size(db_file), has_password=True,
    )


@router.post("/{username}/activate", response_model=UserOut)
def activate_user(username: str, payload: ActivateIn = ActivateIn()):
    db_file = registry.get_db_file(username)
    if not db_file:
        raise HTTPException(404, f"User {username!r} not found")
    if not registry.verify_password(username, payload.password or ""):
        raise HTTPException(403, "Incorrect password")
    # Registry updated BEFORE switching the live engine: switch_active_db()
    # triggers scheduler.reload_for_active_user(), which reads
    # registry.get_active() to decide things like the legacy-spreadsheet-id
    # migration - if that still pointed at the OLD user, the new user's
    # settings would load incorrectly (this was a real bug: the migration
    # silently never fired when switching via this endpoint).
    registry.set_active(username)
    switch_active_db(db_file)
    return UserOut(
        username=username, is_active=True, db_size_bytes=db_file_size(db_file),
        has_password=registry.has_password(username),
    )


@router.post("/{username}/set_password")
def set_password(username: str, payload: SetPasswordIn):
    if not registry.exists(username):
        raise HTTPException(404, f"User {username!r} not found")
    if not registry.verify_password(username, payload.old_password or ""):
        raise HTTPException(403, "Incorrect current password")
    registry.set_password(username, payload.new_password)
    return {"updated": True}


@router.delete("/{username}")
def delete_user(username: str, admin_password: Optional[str] = Body(default=None, embed=True)):
    _require_admin(admin_password)
    db_file = registry.get_db_file(username)
    if not db_file:
        raise HTTPException(404, f"User {username!r} not found")
    if registry.get_active() == username:
        raise HTTPException(409, "Can't delete the currently active user - switch to another user first")
    if len(registry.list_users()) <= 1:
        raise HTTPException(409, "Can't delete the last remaining user")

    # File first, registry second - if the file can't be deleted (e.g. a
    # lingering lock), the user stays visible and deletable rather than
    # becoming an orphaned file with no registry entry pointing at it.
    delete_db_file(db_file)
    registry.remove_user(username)
    return {"deleted": True}
