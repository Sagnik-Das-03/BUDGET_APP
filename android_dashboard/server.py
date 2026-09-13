"""Read-only budget dashboard, served over LAN - no database, no sync
engine, no write path anywhere in this module. Started by ServerService.kt
via Python.getModule("server").callAttr("start_server").

Serves the SAME frontend API contract as the desktop app's /api/dashboard/*,
/api/savings_goal/progress, and /api/sync/config (see backend/app/api/
dashboard.py) - computed from Sheet data via calculations.py instead of a
SQLAlchemy session, but shaped identically, so the real React frontend's
components and frontend/src/lib/api.ts run completely unmodified against
this backend. What's NOT implemented: anything involving editing data,
Ask/LLM, or the desktop's multi-profile registry.

"Active user" mirrors the desktop app's own one-active-profile-at-a-time
model (see app/user_registry.py there) - GET/POST /api/active_user switches
which configured spreadsheet every other endpoint reads from, so none of
the reused frontend code needs to know profiles exist at all.

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
                                  want to view. The SAME read-only service
                                  account must be shared as Viewer on EACH
                                  spreadsheet_id listed here (sharing is
                                  per-file, not per-credential, so one
                                  reader identity can view many people's
                                  sheets independently, each still only
                                  ever read-only).
    static/                      the built frontend (see frontend/'s
                                  android build target) - served at "/".
"""
import json
import time
from datetime import date as date_type
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from android_dashboard import calculations as calc
from android_dashboard.parsing import Config, Txn, parse_config, parse_row
from android_dashboard.sheets_reader import ReadOnlySheetsClient

app = FastAPI(title="Budget Dashboard (read-only)")

_HERE = Path(__file__).resolve().parent
CREDENTIALS_PATH = _HERE / "dashboard_credentials.json"
USERS_CONFIG_PATH = _HERE / "users_config.json"
STATIC_DIR = _HERE / "static"

_CACHE_TTL_SECONDS = 45
_cache: dict[str, dict] = {}  # user name -> {"txns": ..., "config": ..., "fetched_at": ...}
_active_user_name: Optional[str] = None


def _load_users() -> list[dict]:
    if not USERS_CONFIG_PATH.exists():
        return []
    return json.loads(USERS_CONFIG_PATH.read_text()).get("users", [])


def _resolve_user(name: Optional[str]) -> dict:
    users = _load_users()
    if not users:
        raise HTTPException(503, f"No users configured - add one to {USERS_CONFIG_PATH.name}")
    if name is None:
        return users[0]
    for u in users:
        if u["name"] == name:
            return u
    raise HTTPException(404, f"No configured user named {name!r}")


def _active_user() -> dict:
    return _resolve_user(_active_user_name)


def _load_user_data(name: str) -> tuple[list[Txn], Config]:
    cached = _cache.get(name)
    now = time.monotonic()
    if cached and (now - cached["fetched_at"]) < _CACHE_TTL_SECONDS:
        return cached["txns"], cached["config"]

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
    _cache[name] = {"txns": txns, "config": config, "fetched_at": now}
    return txns, config


def _current_data() -> tuple[list[Txn], Config]:
    return _load_user_data(_active_user()["name"])


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/users")
def users():
    return [{"name": u["name"]} for u in _load_users()]


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


# ---------- static frontend (registered last so it never shadows an /api/* route) ----------

if STATIC_DIR.is_dir():
    app.mount("/assets", StaticFiles(directory=str(STATIC_DIR / "assets")), name="assets")

    @app.get("/{full_path:path}")
    def spa(full_path: str):
        candidate = STATIC_DIR / full_path
        if full_path and candidate.is_file():
            return FileResponse(candidate)
        # frontend/vite.android.config.ts's entry is android.html, not the
        # usual index.html - Vite names the built output after the entry.
        return FileResponse(STATIC_DIR / "android.html")


def start_server(host: str = "0.0.0.0", port: int = 8000) -> None:
    import uvicorn
    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    start_server()
