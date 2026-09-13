"""Read-only budget dashboard, served over LAN - no database, no sync
engine, no write path anywhere in this module. Started by ServerService.kt
via Python.getModule("server").callAttr("start_server").

Where things live (all bundled inside this app's Python source tree, next
to this file - Chaquopy extracts the whole src/main/python/ directory to
app-private storage on install, so a plain file placed here is readable at
a path relative to this module):

    dashboard_credentials.json  - the READ-ONLY service account key (see
                                  budget_tracker/android_dashboard/
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

Multiple users just means multiple named spreadsheet IDs behind the same
read-only credential - there's no per-user database, no registry, no
passwords, none of the desktop app's multi-user machinery. Pick a user with
?user=<name> (defaults to the first entry in users_config.json).
"""
import html
import json
import time
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse

from android_dashboard.dashboard import compute_dashboard
from android_dashboard.sheets_reader import ReadOnlySheetsClient

app = FastAPI(title="Budget Dashboard (read-only)")

_HERE = Path(__file__).resolve().parent
CREDENTIALS_PATH = _HERE / "dashboard_credentials.json"
USERS_CONFIG_PATH = _HERE / "users_config.json"

_CACHE_TTL_SECONDS = 45
_cache: dict[str, dict] = {}  # user name -> {"data": ..., "fetched_at": ...}


def _load_users() -> list[dict]:
    if not USERS_CONFIG_PATH.exists():
        return []
    return json.loads(USERS_CONFIG_PATH.read_text()).get("users", [])


def _resolve_user(name: str = None) -> dict:
    users = _load_users()
    if not users:
        raise HTTPException(503, f"No users configured - add one to {USERS_CONFIG_PATH.name}")
    if name is None:
        return users[0]
    for u in users:
        if u["name"] == name:
            return u
    raise HTTPException(404, f"No configured user named {name!r}")


def _get_dashboard_data(user_name: str = None) -> dict:
    user = _resolve_user(user_name)
    name = user["name"]

    cached = _cache.get(name)
    now = time.monotonic()
    if cached and (now - cached["fetched_at"]) < _CACHE_TTL_SECONDS:
        return cached["data"]

    if not CREDENTIALS_PATH.exists():
        raise HTTPException(503, f"Missing {CREDENTIALS_PATH.name} - see server.py's module docstring")

    try:
        client = ReadOnlySheetsClient(str(CREDENTIALS_PATH))
        rows = client.get_rows(user["spreadsheet_id"], "Transactions")
    except Exception as e:
        raise HTTPException(502, f"Couldn't read {name}'s spreadsheet: {e}") from e

    data = compute_dashboard(rows)
    data["user"] = name
    _cache[name] = {"data": data, "fetched_at": now}
    return data


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/users")
def users():
    return [{"name": u["name"]} for u in _load_users()]


@app.get("/dashboard")
def dashboard(user: str = Query(default=None)):
    return _get_dashboard_data(user)


def _money(v: float) -> str:
    return f"₹{v:,.2f}"


def _render_html(data: dict, all_users: list[dict]) -> str:
    def _kpi_card(title: str, totals: dict) -> str:
        return f"""
        <div class="card">
          <h2>{html.escape(title)}</h2>
          <div class="row"><span>Income</span><b class="pos">{_money(totals['income'])}</b></div>
          <div class="row"><span>Expenses</span><b class="neg">{_money(totals['expenses'])}</b></div>
          <div class="row"><span>Net</span><b>{_money(totals['net'])}</b></div>
          <div class="row"><span>Savings rate</span><b>{totals['savings_rate'] * 100:.1f}%</b></div>
        </div>"""

    category_rows = "".join(
        f"<tr><td>{html.escape(c['category'])}</td><td class='amt'>{_money(c['total'])}</td></tr>"
        for c in data["categories"][:10]
    ) or "<tr><td colspan='2'>No expenses recorded</td></tr>"

    user_tabs = "".join(
        f'<a class="tab{" active" if u["name"] == data["user"] else ""}" '
        f'href="/?user={html.escape(u["name"])}">{html.escape(u["name"])}</a>'
        for u in all_users
    )

    return f"""<!doctype html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Budget Dashboard</title>
<style>
  body {{ font-family: -apple-system, Segoe UI, Roboto, sans-serif; background: #0b0f14; color: #e6edf3;
         margin: 0; padding: 16px; }}
  h1 {{ font-size: 1.3rem; margin: 0 0 12px; }}
  h2 {{ font-size: 0.85rem; text-transform: uppercase; letter-spacing: .04em; color: #9fb0c0; margin: 0 0 10px; }}
  .tabs {{ display: flex; gap: 8px; margin-bottom: 16px; flex-wrap: wrap; }}
  .tab {{ color: #9fb0c0; text-decoration: none; padding: 6px 12px; border-radius: 999px;
         border: 1px solid #1f2a35; font-size: 0.85rem; }}
  .tab.active {{ background: #1f2a35; color: #e6edf3; }}
  .grid {{ display: grid; gap: 12px; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); }}
  .card {{ background: #131a22; border: 1px solid #1f2a35; border-radius: 10px; padding: 14px 16px; }}
  .row {{ display: flex; justify-content: space-between; padding: 4px 0; font-size: 0.95rem; }}
  .pos {{ color: #4ade80; }} .neg {{ color: #f87171; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 0.9rem; }}
  td {{ padding: 6px 4px; border-bottom: 1px solid #1f2a35; }}
  .amt {{ text-align: right; }}
  .meta {{ color: #6b7a89; font-size: 0.75rem; margin-top: 16px; }}
</style></head>
<body>
  <h1>Budget Dashboard</h1>
  {f'<div class="tabs">{user_tabs}</div>' if len(all_users) > 1 else ''}
  <div class="grid">
    {_kpi_card("This Month", data['this_month'])}
    {_kpi_card("This Year", data['this_year'])}
    {_kpi_card("All Time", data['all_time'])}
    <div class="card">
      <h2>Top Categories (All Time)</h2>
      <table>{category_rows}</table>
    </div>
  </div>
  <p class="meta">{html.escape(data['user'])} · {data['transaction_count']} transactions ·
     generated {html.escape(data['generated_at'])} · read-only, refreshes every {_CACHE_TTL_SECONDS}s</p>
</body></html>"""


@app.get("/", response_class=HTMLResponse)
def index(user: str = Query(default=None)):
    return _render_html(_get_dashboard_data(user), _load_users())


def start_server(host: str = "0.0.0.0", port: int = 8000) -> None:
    import uvicorn
    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    start_server()
