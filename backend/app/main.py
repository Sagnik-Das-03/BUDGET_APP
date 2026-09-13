import logging
import os
from pathlib import Path

from fastapi import Depends, FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api import (
    accounts, appearance, budgets, categories, conflicts, dashboard, imports, llm, saved_views,
    savings_goal, sync, transactions, users,
)
from app.auth import require_auth
from app.config import settings
from app.db import init_db, session_scope
from app.llm.router import llm_router
from app.repositories.accounts import AccountRepository
from app.repositories.categories import CategoryRepository
from app.sync import scheduler

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

# Overridable so the Android host can point this at Chaquopy's app-private
# storage, where the frontend build is copied to instead of a sibling of
# this repo. Not read anywhere by desktop/Docker, which never sets this.
if os.environ.get("BUDGET_TRACKER_FRONTEND_DIST"):
    FRONTEND_DIST = Path(os.environ["BUDGET_TRACKER_FRONTEND_DIST"])
else:
    # backend/app/main.py -> backend/app -> backend -> budget_tracker -> frontend/dist
    FRONTEND_DIST = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"

app = FastAPI(title="Budget Tracker")


@app.middleware("http")
async def enforce_read_only(request: Request, call_next):
    """The Android host (see android/app/src/main/python/server.py) sets
    read_only_mode=True - every write route is blocked here, in ONE place,
    rather than annotating each mutating endpoint individually. A no-op on
    desktop/Docker, where the flag defaults to False and this middleware
    never rejects anything."""
    if settings.read_only_mode and request.method not in ("GET", "HEAD", "OPTIONS"):
        return JSONResponse(
            {"detail": "This server is read-only - editing happens in the main app."},
            status_code=403,
        )
    return await call_next(request)

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
app.include_router(llm.router, dependencies=_auth)
app.include_router(saved_views.router, dependencies=_auth)
app.include_router(users.router, dependencies=_auth)


@app.on_event("startup")
def on_startup() -> None:
    init_db()
    with session_scope() as session:
        CategoryRepository(session).ensure_defaults()
        AccountRepository(session).ensure_default()
    # The Android host runs its OWN pull-only refresh loop (see
    # android/app/src/main/python/viewers.py) instead of this bidirectional
    # scheduler - there's nothing local to push (writes are blocked by
    # enforce_read_only above), and its Viewer-only credentials couldn't
    # push even if something tried to.
    if not settings.read_only_mode:
        scheduler.start()
    llm_router.warm_up()


@app.on_event("shutdown")
def on_shutdown() -> None:
    if not settings.read_only_mode:
        scheduler.run_once()  # final sync before shutting down
        scheduler.stop()
    llm_router.shutdown()


@app.get("/health")
def health():
    return {"status": "ok"}


# ---------- serve the built React/Vite frontend ----------
# Registered after /health and all /api/* routers so nothing above is shadowed.
if FRONTEND_DIST.is_dir():
    # On the Android host, the static bundle itself must load WITHOUT the
    # LAN password - the React app renders its own shadcn password screen
    # (see frontend/src/lib/lanAuth.ts) instead of the browser's native
    # Basic Auth prompt, which only appears in response to a 401 on an
    # already-loaded page. Desktop is unaffected (still gated by _auth when
    # its own optional AUTH_ENABLED is on) - read_only_mode is always False
    # there. The actual DATA (every /api/* router above) stays behind
    # require_auth regardless; only the JS/CSS/HTML shell is exempt.
    _static_deps = [] if settings.read_only_mode else _auth
    app.mount("/assets", StaticFiles(directory=str(FRONTEND_DIST / "assets")), name="frontend-assets")

    @app.get("/{full_path:path}", dependencies=_static_deps)
    def spa(full_path: str):
        """Serves a real static file if one exists at that path (favicon.svg, etc.),
        otherwise falls back to index.html so React Router's client-side routes
        (e.g. /transactions, /settings) work on direct load and refresh."""
        candidate = FRONTEND_DIST / full_path
        if full_path and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(FRONTEND_DIST / "index.html")
