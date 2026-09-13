"""Host-glue for the Android app's viewers - NOT part of the real backend
(app/), and never reachable over HTTP (server.py's read-only middleware
blocks every write route; this module has no route of its own at all). A
viewer only ever appears here via the manifest the desktop app publishes
(see backend/app/sync/reports.py's regenerate_viewer_manifest) - this phone
has no "add viewer" capability of its own, by design: onboarding a person
only ever happens on the desktop app.

Each viewer gets their own local SQLite file (db.py's existing per-user-file
convention, reused here for per-viewer instead - `viewer_<name>.db`),
refreshed by calling the REAL app.sync.engine.pull() - the exact same
Sheets-row-parsing and upsert-into-SQLAlchemy logic the desktop uses. Never
push() - nothing local ever changes (writes are blocked at the HTTP layer),
so there's nothing to push, and the Viewer-only credentials couldn't push
even if something tried to. Sheets API calls are already rate-limited
process-wide by app/sheets/adapter.py's with_retry().

MainActivity.kt's "Viewers" card calls list_viewers()/activate_viewer() only
- no add/remove. The background refresh loop (server.py) calls refresh_all()
on a timer.

Two different ways to pick a viewer, deliberately kept separate: Kotlin's
activate_viewer() sets a server-WIDE default (fine for the phone's own
single local screen); the web app instead uses check_viewer_password() +
get_request_session(), which server.py wires to a per-browser cookie via a
FastAPI dependency override - so switching who you're looking at from one
browser tab never affects any other device simultaneously connected to the
same phone (see activate_viewer()'s docstring for the bug that would
otherwise cause).
"""
import env_setup  # noqa: F401 - side effect: sets env vars app.* reads, see its docstring

import hashlib
import hmac
import json
import logging
import re
from pathlib import Path
from typing import Optional

from app.config import BASE_DIR, settings
from app.db import create_empty_db, session_for, switch_active_db
from app.repositories.app_settings import SPREADSHEET_ID_KEY, AppSettingRepository
from app.repositories.budgets import BudgetRepository
from app.repositories.categories import CategoryRepository
from app.repositories.savings_goal import SavingsGoalRepository
from app.sheets.adapter import GoogleSheetsService
from app.sync.engine import pull

logger = logging.getLogger("budget_dashboard.viewers")


class WrongPassword(Exception):
    """Raised by activate_viewer() specifically for a wrong/missing password
    on a password-protected viewer - kept distinct from ValueError (unknown
    viewer name) so server.py's route can answer 401 vs 404 correctly."""

VIEWERS_JSON_PATH = BASE_DIR / "viewers.json"
CREDENTIALS_PATH = BASE_DIR / "dashboard_credentials.json"

# Which viewer's database app.db's engine is currently pointed at - tracked
# here (not read back from app.db, which has no concept of "viewer", only
# "whatever file the engine happens to be bound to") so both MainActivity.kt
# and the web app's own switcher (server.py's /api/active_user route) can
# ask "who am I looking at right now".
_active_viewer_name: Optional[str] = None

_CURRENCY_PREFIX = re.compile(r"(?:₹|rs\.?|inr)\s*", re.IGNORECASE)


def _verify_password(password: str, stored_hash: str) -> bool:
    """Same PBKDF2-HMAC-SHA256 scheme as backend/app/user_registry.py's
    _verify_password - the manifest publishes that same hash string
    (`<salt hex>:<digest hex>`) as-is, so this just re-checks it here
    without ever seeing or needing the plaintext password to have been
    stored anywhere."""
    salt_hex, _, digest_hex = stored_hash.partition(":")
    if not salt_hex or not digest_hex:
        return False
    salt = bytes.fromhex(salt_hex)
    expected = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 200_000)
    return hmac.compare_digest(expected.hex(), digest_hex)


def _parse_amount(value: str) -> Optional[float]:
    """A budget/savings-goal amount cell often comes back Sheets-currency-
    formatted (e.g. "₹2,000.00") rather than a bare number - same stripping
    app/sheets/mapping.py's own _parse_amount does for transaction amounts."""
    cleaned = _CURRENCY_PREFIX.sub("", value, count=1).replace(",", "").strip()
    if not cleaned:
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def _apply_config(session, rows: list[list[str]]) -> None:
    """Applies the "Config" tab (backend/app/sync/reports.py's
    regenerate_config_tab) to this viewer's local database: category color/
    counts_as_expense/is_essential, per-category budgets, and the savings
    goal. Without this, every category pull() creates via get_or_create()
    defaults to counts_as_expense=True/is_essential=True (see
    CategoryRepository), and no Budget/SavingsGoal rows exist locally at
    all - exactly why Budget Utilization showed "-" and Essential Spend
    showed 100% before this existed. Same section-scanning approach as the
    tab itself (not a fixed-row table): a title row switches which section
    follows, then a header row, then data rows."""
    cat_repo = CategoryRepository(session)
    budget_repo = BudgetRepository(session)
    goal_repo = SavingsGoalRepository(session)

    section: Optional[str] = None
    for row in rows:
        first = row[0].strip() if row else ""
        if first == "Categories":
            section = "categories"
            continue
        if first.startswith("Budgets"):
            section = "budgets"
            continue
        if first.startswith("Savings Goal"):
            section = "savings_goal"
            continue
        if first in ("Category", "Period", "App Configuration") or not first:
            continue  # header row, or the tab's title row, or blank - not data

        if section == "categories" and len(row) >= 4:
            color = row[1] or "#898781"
            cat = cat_repo.get_or_create(row[0], color_hex=color)
            cat_repo.set_color(cat.id, color)
            cat_repo.set_counts_as_expense(cat.id, row[2].strip().upper() == "TRUE")
            cat_repo.set_is_essential(cat.id, row[3].strip().upper() == "TRUE")
        elif section == "budgets" and len(row) >= 3:
            amount = _parse_amount(row[2])
            if amount is None:
                continue
            cat = cat_repo.get_or_create(row[0])
            budget_repo.set_goal(cat, amount, row[1] or None)
        elif section == "savings_goal" and len(row) >= 2:
            amount = _parse_amount(row[1])
            if amount is not None:
                goal_repo.set_goal(amount, row[0] or None)


def _db_file_for(name: str) -> str:
    return f"viewer_{name}.db"


def _sheets_client() -> Optional[GoogleSheetsService]:
    if not CREDENTIALS_PATH.exists():
        return None
    return GoogleSheetsService(str(CREDENTIALS_PATH))


def _load_viewers() -> dict[str, dict]:
    """name -> {"spreadsheet_id": ..., "password_hash": ... or ""}."""
    if not VIEWERS_JSON_PATH.exists():
        return {}
    try:
        return json.loads(VIEWERS_JSON_PATH.read_text())
    except (json.JSONDecodeError, OSError):
        return {}


def _save_viewers(viewers: dict[str, dict]) -> None:
    VIEWERS_JSON_PATH.write_text(json.dumps(viewers, indent=2))


def list_viewers() -> list[str]:
    return sorted(_load_viewers().keys())


def has_password(name: str) -> bool:
    return bool(_load_viewers().get(name, {}).get("password_hash"))


def list_viewers_json() -> str:
    """Same names as list_viewers(), plus whether each needs a password to
    switch to - pre-serialized, MainActivity.kt/the web app both parse this
    with a plain JSON parser rather than walking a Chaquopy PyObject list."""
    viewers = _load_viewers()
    return json.dumps([
        {"name": name, "has_password": bool(v.get("password_hash"))}
        for name, v in sorted(viewers.items())
    ])


def refresh_manifest() -> None:
    """Pulls {name, spreadsheet_id, password_hash} rows from the desktop-
    published manifest sheet and replaces the local viewer list wholesale -
    a viewer removed on desktop disappears here on the next refresh too,
    not just additions. The password hash travels as-is (PBKDF2, salted) -
    see _verify_password's docstring."""
    if not settings.viewer_manifest_spreadsheet_id:
        return
    sheets = _sheets_client()
    if sheets is None:
        return
    try:
        rows = sheets.get_rows(settings.viewer_manifest_spreadsheet_id, "Viewers")
    except Exception:
        logger.exception("Failed to read the viewer manifest")
        return
    viewers: dict[str, dict] = {}
    for row in rows[1:]:  # row 0 is the "Name"/"Spreadsheet ID"/"Password Hash" header
        if len(row) >= 2 and row[0] and row[1]:
            viewers[row[0]] = {
                "spreadsheet_id": row[1],
                "password_hash": row[2] if len(row) >= 3 else "",
            }
    _save_viewers(viewers)


def refresh_viewer_data(name: str) -> None:
    """Pulls one viewer's Transactions sheet into their own local SQLite
    file - via session_for(), NOT switch_active_db(), so refreshing in the
    background never disturbs whichever viewer is currently being served."""
    spreadsheet_id = _load_viewers().get(name, {}).get("spreadsheet_id")
    if not spreadsheet_id:
        raise ValueError(f"Unknown viewer {name!r} - call refresh_manifest() first")
    sheets = _sheets_client()
    if sheets is None:
        return
    db_file = _db_file_for(name)
    create_empty_db(db_file)  # idempotent - safe even if this viewer already has one
    raw_rows = sheets.get_rows(spreadsheet_id, "Transactions")
    try:
        config_rows = sheets.get_rows(spreadsheet_id, "Config")
    except Exception:
        config_rows = []  # tab not created yet for this spreadsheet - nothing to apply
    with session_for(db_file) as session:
        # So /api/sync/config's google_spreadsheet_id/credentials_configured
        # reflect reality too - purely informational here (the read-only
        # frontend's subtitle only checks the read_only flag, never this),
        # but keeps this viewer's own database internally consistent.
        AppSettingRepository(session).set(SPREADSHEET_ID_KEY, spreadsheet_id)
        pull(session, sheets, spreadsheet_id, raw_rows)  # pull() itself commits
        if config_rows:
            _apply_config(session, config_rows)
            session.commit()


def check_viewer_password(name: str, password: str) -> None:
    """Raises ValueError (unknown viewer) or WrongPassword - the same checks
    activate_viewer() does, WITHOUT touching the shared global active-viewer
    state. This is what the web app's own switch uses (server.py's
    /api/active_user route stores the result in a per-browser cookie
    instead) - see activate_viewer()'s docstring for why the two need to be
    different at all: two people looking at the dashboard from two
    different devices at the same time must never be able to yank each
    other between viewers."""
    entry = _load_viewers().get(name)
    if entry is None:
        raise ValueError(f"Unknown viewer {name!r}")
    stored_hash = entry.get("password_hash") or ""
    if stored_hash and not _verify_password(password, stored_hash):
        raise WrongPassword("Incorrect password")


def activate_viewer(name: str, password: str = "") -> None:
    """Sets the server-WIDE default viewer (via app.db.switch_active_db()) -
    used by MainActivity.kt's Viewers card, a single local screen on the
    phone itself, not simultaneously driven by multiple devices, so a
    shared global default makes sense there. The web app does NOT call
    this to switch (see check_viewer_password() + get_request_session()
    below) - if it did, one browser switching who it's viewing would yank
    every OTHER browser currently looking at the dashboard along with it,
    since app.db's engine/session is one process-wide pointer, not
    per-connection."""
    global _active_viewer_name
    check_viewer_password(name, password)
    db_file = _db_file_for(name)
    create_empty_db(db_file)
    switch_active_db(db_file)
    _active_viewer_name = name


_session_factories: dict[str, object] = {}


def _session_factory_for(name: str):
    """One cached SQLAlchemy sessionmaker per viewer, bound to that
    viewer's own SQLite file directly - separate from app.db's single
    process-wide engine/SessionLocal, and separate from refresh_viewer_
    data()'s own throwaway session_for() connections (a background refresh
    and a request being served concurrently each get their own connection
    to the same file, which SQLite handles fine for this app's mostly-
    read workload)."""
    if name not in _session_factories:
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker

        db_file = _db_file_for(name)
        create_empty_db(db_file)  # ensures the file + schema exist first
        path = BASE_DIR / "data" / db_file
        engine = create_engine(f"sqlite:///{path}", connect_args={"check_same_thread": False})
        _session_factories[name] = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    return _session_factories[name]


def get_request_session(name: str):
    """A FastAPI-dependency-shaped generator bound to ONE specific viewer -
    server.py overrides app.db.get_session with a wrapper around this, so
    every /api/* read (dashboard, transactions, categories, ...) resolves
    per-browser (via that browser's own `viewer` cookie) instead of through
    app.db's single shared "currently active" pointer. This is the actual
    fix for two devices open at once: switching on one no longer moves the
    other."""
    factory = _session_factory_for(name)
    session = factory()
    try:
        yield session
    finally:
        session.close()


def get_active_viewer() -> Optional[str]:
    """None means "pick someone" - either no viewers are known yet, or the
    only ones that are all require a password, so there's nothing safe to
    auto-activate. Otherwise this lazily activates the first PASSWORDLESS
    viewer (alphabetically) so the dashboard has something to show without
    an explicit switch first - never a password-protected one, since that
    would mean showing their data before anyone proved they're allowed to
    see it."""
    global _active_viewer_name
    if _active_viewer_name is not None:
        return _active_viewer_name
    for name in list_viewers():
        if not has_password(name):
            activate_viewer(name)
            return _active_viewer_name
    return None


def refresh_all() -> None:
    """Called by server.py's background loop: manifest first (so a viewer
    added/removed on desktop is reflected before their data is touched),
    then each known viewer's data - one failure doesn't stop the others."""
    refresh_manifest()
    for name in list_viewers():
        try:
            refresh_viewer_data(name)
        except Exception:
            logger.exception("Failed to refresh viewer %r", name)
