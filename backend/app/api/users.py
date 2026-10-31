import uuid
from typing import Optional

from fastapi import APIRouter, Body, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from app.config import settings
from app.db import create_empty_db, db_file_size, delete_db_file, session_for, switch_active_db
from app.demo_data import seed_demo_data
from app.models import Transaction
from app.repositories.accounts import AccountRepository
from app.repositories.categories import CategoryRepository
from app.sheets.adapter import GoogleSheetsService
from app.sync.reports import apply_password_resets_from_backup
from app.sync.scheduler import publish_viewer_manifest
from app.user_registry import ADMIN_USERNAME, registry

router = APIRouter(prefix="/api/users", tags=["users"])


class UserOut(BaseModel):
    username: str
    is_active: bool
    db_size_bytes: int
    has_password: bool
    tags: list[str] = []


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


class RenameUserIn(BaseModel):
    new_username: str = Field(min_length=1, max_length=32, pattern=r"^[A-Za-z0-9_-]+$")
    admin_password: Optional[str] = None


class SetTagsIn(BaseModel):
    tags: list[str] = Field(default_factory=list, max_length=20)


class UserStatOut(BaseModel):
    username: str
    is_active: bool
    db_size_bytes: int
    transaction_count: int
    has_password: bool
    tags: list[str] = []


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
        tags=entry.get("tags", []),
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
            has_password=bool(u.get("password_hash")), tags=u.get("tags", []),
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

    # Opaque, never derived from the username - renaming a user (see
    # rename_user below) only ever touches the registry's display name,
    # never a file on disk, and a username collision after a rename/delete
    # can never collide with an old file left over from a different user.
    db_file = f"{uuid.uuid4().hex}.db"
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
    publish_viewer_manifest()
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
    publish_viewer_manifest()
    return {"updated": True}


@router.post("/{username}/rename")
def rename_user(username: str, payload: RenameUserIn):
    """Changes only the display name - the underlying db_file is an opaque
    identifier (see create_user() above) that never changes, so this is a
    pure registry edit, no file touched. Gated like create/delete (not
    set_password/clear_password's own-account or admin-reset logic) since
    this is an identity change, not a credential one. "admin" itself can't
    be renamed - _require_admin()'s gate is hardcoded to that exact
    username (ADMIN_USERNAME), so renaming it would silently disable the
    gate for every future create/delete/rename instead of erroring."""
    _require_admin(payload.admin_password)
    if not registry.exists(username):
        raise HTTPException(404, f"User {username!r} not found")
    if username.lower() == ADMIN_USERNAME.lower():
        raise HTTPException(409, "The admin account can't be renamed")
    try:
        registry.rename_user(username, payload.new_username)
    except ValueError as e:
        raise HTTPException(409, str(e)) from e
    publish_viewer_manifest()
    return {"renamed": True, "username": payload.new_username}


@router.put("/{username}/tags")
def set_tags(username: str, payload: SetTagsIn):
    """Free-form organizational labels only (e.g. "family", "work") - never
    read by any matching/filtering logic, purely for your own use in the
    Admin page, so unlike rename/delete this isn't gated by the admin
    password. Blanks are stripped and duplicates removed (see
    UserRegistry.set_tags); an empty list clears them entirely."""
    if not registry.exists(username):
        raise HTTPException(404, f"User {username!r} not found")
    registry.set_tags(username, payload.tags)
    return {"tags": registry.get_user(username).get("tags", [])}


@router.post("/{username}/clear_password")
def clear_password(username: str, admin_password: Optional[str] = Body(default=None, embed=True)):
    """Admin's password-RESET for a user who forgot theirs - gated by the
    admin account's own password (same check as create/delete), not by
    knowing the target user's old password like set_password requires."""
    _require_admin(admin_password)
    if not registry.exists(username):
        raise HTTPException(404, f"User {username!r} not found")
    registry.clear_password(username)
    publish_viewer_manifest()
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
    publish_viewer_manifest()
    return {"deleted": True}


@router.post("/reset_passwords_from_sheets")
def reset_passwords_from_sheets():
    """Password reset via Sheets, not a password: clear a user's Password
    Hash cell in the "Registry Backup" tab (see app/sync/reports.py's
    apply_password_resets_from_backup) and call this - it clears that
    password locally too, same effect as clear_password() above but reached
    without knowing ANY password. Deliberately not gated by _require_admin()
    - that's the exact lock this exists to recover from when it's ADMIN's
    own password that's forgotten (clear_password on admin itself needs
    admin's current password, which is the one thing you don't have). The
    real gate is edit access to the backup spreadsheet, same trust level as
    the equivalent `reset-passwords` CLI command."""
    if not settings.viewer_manifest_spreadsheet_id:
        raise HTTPException(503, "VIEWER_MANIFEST_SPREADSHEET_ID is not set in .env - nothing to read resets from.")
    if not settings.google_service_account_key_path:
        raise HTTPException(503, "GOOGLE_SERVICE_ACCOUNT_KEY_PATH is not set in .env - can't read the backup.")
    sheets = GoogleSheetsService(settings.google_service_account_key_path)
    reset = apply_password_resets_from_backup(sheets, settings.viewer_manifest_spreadsheet_id)
    if reset:
        publish_viewer_manifest()
    return {"reset": reset}
