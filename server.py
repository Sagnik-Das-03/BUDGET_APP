"""Read-only budget dashboard, served over LAN - no write path anywhere in
this module, not even to its own local files (those are a cache, never a
source of truth). Started by ServerService.kt via
Python.getModule("server").callAttr("start_server").

Serves the SAME frontend API contract as the desktop app's /api/dashboard/*,
/api/transactions, /api/categories, /api/accounts, /api/savings_goal/
progress, and /api/sync/config - computed from Sheet data (via
calculations.py/filters.py) instead of a SQLAlchemy session, but shaped
identically, so the real React frontend's components and frontend/src/lib/
api.ts run completely unmodified against this backend. What's NOT
implemented: anything that WRITES data (no create/update/delete transaction
routes exist at all), and Ask/LLM (no local model on this build).

"Active user" mirrors the desktop app's own one-active-profile-at-a-time
model (see app/user_registry.py there) - GET/POST /api/active_user switches
which configured spreadsheet every other endpoint reads from, so none of
the reused frontend code needs to know profiles exist at all. Unlike the
desktop, there's no per-profile login here: adding/removing a viewer
(users_config.py) is a direct Chaquopy call from MainActivity.kt's "Manage
Viewers" screen, never an HTTP route - the phone's owner, already past its
biometric lock, IS this app's admin. Each viewer gets its own isolated slice
of local_db.py's SQLite cache (every table keyed by user_name), the
equivalent of the desktop's "each user is a separate database" for a build
that never writes anything of its own.

Where things live (all bundled inside this app's Python source tree, next
to this file - Chaquopy extracts the whole src/main/python/ directory to
app-private storage on install, so a plain file placed here is readable at
a path relative to this module):

    dashboard_credentials.json  - the READ-ONLY service account key (see
                                  sheets_reader.py's docstring for how to
                                  create one - it must be shared as VIEWER,
                                  never Editor, on every spreadsheet listed
                                  in users_config.json below). NOT checked
                                  into git - copy your key to this exact
                                  path before building.
    users_config.json           - {"users": [{"name": ..., "spreadsheet_id":
                                  ...}, ...]} - one entry per profile you
                                  want to view, managed via users_config.py
                                  from the app's "Manage Viewers" screen (no
                                  need to hand-edit this file). The SAME
                                  read-only service account must be shared
                                  as Viewer on EACH spreadsheet_id listed
                                  here (sharing is per-file, not per-
                                  credential, so one reader identity can
                                  view many people's sheets independently,
                                  each still only ever read-only).
    static/                      a copy of frontend/dist (the SAME build the
                                  desktop app serves) - served at "/". Not a
                                  separate build; Dashboard.tsx/NavBar.tsx/
                                  App.tsx hide editing/AI/nav at runtime based
                                  on the read_only flag this module's
                                  /api/sync/config returns.
    auth_config.json              the LAN password's salted hash (auth.py) -
                                  set from MainActivity.kt's password screen,
                                  never over HTTP. Every request (including
                                  static files) is refused until this exists
                                  - see the middleware below.
    dashboard_cache.db            local_db.py's SQLite mirror of every
                                  configured user's Sheet data, refreshed on
                                  a timer (see the background thread started
                                  at the bottom of this file) instead of
                                  fetched per-request.
"""
import base64
import threading
import time
from datetime import date as date_type
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, Response

from android_dashboard import auth, calculations as calc, users_config
from android_dashboard.filters import filter_transactions
from android_dashboard.local_db import LocalStore
from android_dashboard.parsing import Config, Txn, parse_config, parse_row
from android_dashboard.sheets_reader import ReadOnlySheetsClient

app = FastAPI(title="Budget Dashboard (read-only)")

_HERE = Path(__file__).resolve().parent
CREDENTIALS_PATH = _HERE / "dashboard_credentials.json"
STATIC_DIR = _HERE / "static"

REFRESH_INTERVAL_SECONDS = 60
_store = LocalStore(_HERE / "dashboard_cache.db")
_active_user_name: Optional[str] = None


@app.middleware("http")
async def require_lan_password(request: Request, call_next):
    """Basic Auth in front of EVERY response, static files included - the
    real risk here isn't someone reading the DB file, it's anyone else on
    the same Wi-Fi just opening this address in a browser. Fails CLOSED
    (503, not a silent pass-through) if no password has been set yet from
    the app, unlike the desktop's own optional basic auth (off by default
    for a localhost-only tool) - see auth.py's docstring for why the two
    differ. The username in the prompt is never checked."""
    if not auth.is_password_set():
        return Response(
            content='{"detail":"No LAN password set yet - open the Budget Dashboard app and set one."}',
            status_code=503, media_type="application/json",
        )
    header = request.headers.get("authorization", "")
    password = ""
    if header.startswith("Basic "):
        try:
            decoded = base64.b64decode(header[6:]).decode("utf-8")
            _, _, password = decoded.partition(":")
        except Exception:
            password = ""
    if not auth.verify_password(password):
        return Response(status_code=401, headers={"WWW-Authenticate": 'Basic realm="Budget Dashboard"'})
    return await call_next(request)


def _resolve_user(name: Optional[str]) -> dict:
    users = users_config.load_users()
    if not users:
        raise HTTPException(503, "No viewers configured yet - add one from the Budget Dashboard app")
    if name is None:
        return users[0]
    for u in users:
        if u["name"] == name:
            return u
    raise HTTPException(404, f"No configured user named {name!r}")


def _active_user() -> dict:
    return _resolve_user(_active_user_name)


def _fetch_from_sheets(name: str) -> tuple[list[Txn], Config]:
    if not CREDENTIALS_PATH.exists():
        raise HTTPException(503, f"Missing {CREDENTIALS_PATH.name} - see server.py's module docstring")
    user = _resolve_user(name)
    try:
        client = ReadOnlySheetsClient(str(CREDENTIALS_PATH))
        txn_rows = client.get_rows(user["spreadsheet_id"], "Transactions")
        config_rows = client.get_rows(user["spreadsheet_id"], "Config")
    except Exception as e:
        raise HTTPException(502, f"Couldn't read {name}'s spreadsheet: {e}") from e
    txns = [t for t in (parse_row(r) for r in txn_rows) if t and not t.deleted]
    config = parse_config(config_rows)
    return txns, config


def _refresh_user(name: str) -> None:
    txns, config = _fetch_from_sheets(name)
    _store.save(name, txns, config)


def _background_refresh_loop() -> None:
    while True:
        for user in users_config.load_users():
            try:
                _refresh_user(user["name"])
            except Exception:
                # A transient Sheets/network hiccup shouldn't take the whole
                # server down - keep serving the last good local copy and
                # try again next tick.
                pass
        time.sleep(REFRESH_INTERVAL_SECONDS)


def _load_user_data(name: str) -> tuple[list[Txn], Config]:
    cached = _store.load(name)
    if cached is None:
        # First time this user's been requested since the local DB was last
        # cleared/created - fetch synchronously so this first request
        # doesn't come back empty while it waits for the next refresh tick.
        _refresh_user(name)
        cached = _store.load(name)
    txns, config, _refreshed_at = cached
    return txns, config


def _current_data() -> tuple[list[Txn], Config]:
    return _load_user_data(_active_user()["name"])


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/users")
def users():
    return [{"name": u["name"]} for u in users_config.load_users()]


@app.get("/api/active_user")
def get_active_user():
    return {"name": _active_user()["name"]}


@app.post("/api/active_user")
def set_active_user(payload: dict):
    global _active_user_name
    name = payload.get("name")
    _resolve_user(name)  # raises 404 if unknown
    _active_user_name = name
    return {"name": name}


# ---------- same contract as backend/app/api/sync.py (fields Dashboard.tsx reads) ----------

@app.get("/api/sync/config")
def sync_config():
    return {
        "credentials_configured": True, "has_own_credentials": True,
        "google_spreadsheet_id": _active_user().get("spreadsheet_id", ""),
        "sync_interval_seconds": 0, "sync_interval_default": 0, "sync_interval_min": 0,
        "sheet_sort_descending": True, "period_tab_sort_descending": True,
        # The single frontend build (frontend/dist, same as the desktop app)
        # reads this to hide editing/AI/non-Dashboard nav at runtime - see
        # App.tsx/NavBar.tsx/Dashboard.tsx's useCapabilities() usage.
        "read_only": True,
    }


# ---------- same contract as backend/app/api/dashboard.py ----------

def _resolve_range(range_: str, date_from: Optional[str], date_to: Optional[str]):
    d_from = date_type.fromisoformat(date_from) if date_from else None
    d_to = date_type.fromisoformat(date_to) if date_to else None
    return calc.resolve_range(range_, d_from, d_to)


@app.get("/api/dashboard/summary")
def summary(range: str = "this_month", date_from: Optional[str] = None, date_to: Optional[str] = None):
    txns, config = _current_data()
    d_from, d_to = _resolve_range(range, date_from, date_to)
    return calc.totals(txns, config, d_from, d_to)


@app.get("/api/dashboard/by_category")
def by_category(range: str = "this_month", type: str = "Expense",
                 date_from: Optional[str] = None, date_to: Optional[str] = None):
    txns, config = _current_data()
    d_from, d_to = _resolve_range(range, date_from, date_to)
    return calc.by_category(txns, config, d_from, d_to, transaction_type=type)


@app.get("/api/dashboard/trend_for_range")
def trend_for_range(range: str = "this_year", date_from: Optional[str] = None, date_to: Optional[str] = None):
    txns, config = _current_data()
    d_from, d_to = _resolve_range(range, date_from, date_to)
    return calc.trend_for_range(txns, config, range, d_from, d_to)


@app.get("/api/dashboard/monthly_breakdown")
def monthly_breakdown():
    txns, config = _current_data()
    return calc.monthly_breakdown(txns, config)


@app.get("/api/dashboard/category_drilldown")
def category_drilldown(range: str = "this_month", type: str = "Expense",
                        date_from: Optional[str] = None, date_to: Optional[str] = None):
    txns, config = _current_data()
    d_from, d_to = _resolve_range(range, date_from, date_to)
    return calc.category_drilldown(txns, config, d_from, d_to, transaction_type=type)


@app.get("/api/dashboard/highlights")
def highlights(range: str = "this_month", date_from: Optional[str] = None, date_to: Optional[str] = None):
    txns, config = _current_data()
    d_from, d_to = _resolve_range(range, date_from, date_to)
    result = calc.highlights(txns, config, d_from, d_to)
    result["comparison"] = calc.period_comparison(txns, config, range, d_from, d_to)
    return result


@app.get("/api/dashboard/category_trends")
def category_trends(range: str = "this_month", type: str = "Expense",
                     date_from: Optional[str] = None, date_to: Optional[str] = None):
    txns, config = _current_data()
    d_from, d_to = _resolve_range(range, date_from, date_to)
    return calc.category_trends(txns, config, range, d_from, d_to, transaction_type=type)


@app.get("/api/dashboard/category_volatility")
def category_volatility(months: int = 6):
    txns, config = _current_data()
    return calc.category_volatility(txns, config, months=months)


@app.get("/api/dashboard/spending_pattern")
def spending_pattern(range: str = "this_month", date_from: Optional[str] = None, date_to: Optional[str] = None):
    txns, _config = _current_data()
    d_from, d_to = _resolve_range(range, date_from, date_to)
    return calc.spending_pattern(txns, d_from, d_to)


@app.get("/api/dashboard/essential_split")
def essential_split(range: str = "this_month", date_from: Optional[str] = None, date_to: Optional[str] = None):
    txns, config = _current_data()
    d_from, d_to = _resolve_range(range, date_from, date_to)
    return calc.essential_vs_discretionary(txns, config, d_from, d_to)


@app.get("/api/dashboard/savings_streak")
def savings_streak():
    txns, config = _current_data()
    return calc.savings_streak(txns, config)


@app.get("/api/dashboard/spend_concentration")
def spend_concentration(range: str = "this_month", top_n: int = 3,
                         date_from: Optional[str] = None, date_to: Optional[str] = None):
    txns, config = _current_data()
    d_from, d_to = _resolve_range(range, date_from, date_to)
    return calc.spend_concentration(txns, config, d_from, d_to, top_n=top_n)


@app.get("/api/dashboard/budget_vs_actual")
def budget_vs_actual(period_key: Optional[str] = None):
    txns, config = _current_data()
    pk = period_key or calc.period_key_for(date_type.today())
    return calc.budget_vs_actual(txns, config, pk)


@app.get("/api/dashboard/budget_alerts")
def budget_alerts(period_key: Optional[str] = None, threshold: float = 0.9):
    txns, config = _current_data()
    pk = period_key or calc.period_key_for(date_type.today())
    return calc.budget_alerts(txns, config, pk, warning_threshold=threshold)


@app.get("/api/savings_goal/progress")
def savings_goal_progress(period_key: Optional[str] = None):
    txns, config = _current_data()
    pk = period_key or calc.period_key_for(date_type.today())
    return calc.savings_goal_progress(txns, config, pk) or {"goal": None}


# ---------- same contract as backend/app/api/transactions.py & category/account
# listing (fields Transactions.tsx and NavBar/App's readOnly branch use) - list
# only, no create/update/delete routes exist here at all. ----------

def _txn_to_out(t: Txn) -> dict:
    iso = f"{t.date.isoformat()}T00:00:00"
    return {
        "transaction_id": t.transaction_id, "date": t.date.isoformat(), "description": t.description,
        "amount": t.amount, "transaction_type": t.transaction_type, "category": t.category,
        "account": t.account, "period_key": calc.period_key_for(t.date), "notes": t.notes,
        "source": "sheets", "sync_status": "synced", "created_at": iso, "updated_at": iso,
    }


@app.get("/api/transactions")
def list_transactions(
    year: Optional[int] = None, month: Optional[int] = None,
    category: Optional[list[str]] = Query(None), category_exclude: bool = False,
    account: Optional[list[str]] = Query(None), account_exclude: bool = False,
    type: Optional[str] = None,
    date_from: Optional[date_type] = None, date_to: Optional[date_type] = None,
    search: Optional[str] = None,
):
    txns, _config = _current_data()
    rows = filter_transactions(
        txns, year=year, month=month, category=category, category_exclude=category_exclude,
        account=account, account_exclude=account_exclude, transaction_type=type,
        date_from=date_from, date_to=date_to, search=search,
    )
    return [_txn_to_out(t) for t in rows]


@app.get("/api/categories")
def list_categories():
    _txns, config = _current_data()
    return [
        {"id": i, "name": name, "color_hex": meta.color, "is_active": True,
         "counts_as_expense": meta.counts_as_expense, "is_essential": meta.is_essential}
        for i, (name, meta) in enumerate(config.categories.items())
    ]


@app.get("/api/accounts")
def list_accounts():
    txns, _config = _current_data()
    names = sorted({t.account for t in txns if t.account})
    return [{"id": i, "name": name, "account_type": "", "is_active": True} for i, name in enumerate(names)]


# ---------- static frontend (registered last so it never shadows an /api/* route) ----------

if STATIC_DIR.is_dir():
    app.mount("/assets", StaticFiles(directory=str(STATIC_DIR / "assets")), name="assets")

    @app.get("/{full_path:path}")
    def spa(full_path: str):
        candidate = STATIC_DIR / full_path
        if full_path and candidate.is_file():
            return FileResponse(candidate)
        # static/ is the SAME build as the desktop app's frontend/dist (see
        # this module's docstring) - one frontend, capability-gated at
        # runtime via /api/sync/config's read_only flag, not a separate build.
        return FileResponse(STATIC_DIR / "index.html")


@app.on_event("startup")
def _start_background_refresh() -> None:
    threading.Thread(target=_background_refresh_loop, daemon=True).start()


def start_server(host: str = "0.0.0.0", port: int = 8000) -> None:
    import uvicorn
    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    start_server()
