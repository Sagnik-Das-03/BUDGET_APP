import logging
from pathlib import Path

from fastapi import Depends, FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api import accounts, appearance, budgets, categories, conflicts, dashboard, imports, savings_goal, sync, transactions
from app.auth import require_auth
from app.db import init_db, session_scope
from app.repositories.accounts import AccountRepository
from app.repositories.categories import CategoryRepository
from app.sync import scheduler

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

# backend/app/main.py -> backend/app -> backend -> budget_tracker -> frontend/dist
FRONTEND_DIST = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"

app = FastAPI(title="Budget Tracker")

_auth = [Depends(require_auth)]
app.include_router(transactions.router, dependencies=_auth)
app.include_router(categories.router, dependencies=_auth)
app.include_router(accounts.router, dependencies=_auth)
app.include_router(budgets.router, dependencies=_auth)
app.include_router(savings_goal.router, dependencies=_auth)
app.include_router(dashboard.router, dependencies=_auth)
app.include_router(sync.router, dependencies=_auth)
app.include_router(conflicts.router, dependencies=_auth)
app.include_router(imports.router, dependencies=_auth)
app.include_router(appearance.router, dependencies=_auth)


@app.on_event("startup")
def on_startup() -> None:
    init_db()
    with session_scope() as session:
        CategoryRepository(session).ensure_defaults()
        AccountRepository(session).ensure_default()
    scheduler.start()


@app.on_event("shutdown")
def on_shutdown() -> None:
    scheduler.stop()


@app.get("/health")
def health():
    return {"status": "ok"}


# ---------- serve the built React/Vite frontend ----------
# Registered after /health and all /api/* routers so nothing above is shadowed.
if FRONTEND_DIST.is_dir():
    app.mount("/assets", StaticFiles(directory=str(FRONTEND_DIST / "assets")), name="frontend-assets")

    @app.get("/{full_path:path}", dependencies=_auth)
    def spa(full_path: str):
        """Serves a real static file if one exists at that path (favicon.svg, etc.),
        otherwise falls back to index.html so React Router's client-side routes
        (e.g. /transactions, /settings) work on direct load and refresh."""
        candidate = FRONTEND_DIST / full_path
        if full_path and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(FRONTEND_DIST / "index.html")
