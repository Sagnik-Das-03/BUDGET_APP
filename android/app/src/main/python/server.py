"""Android host entry point - Kotlin's ServerService.kt calls
Python.getModule("server").callAttr("start_server"). Runs the REAL backend
(app/, a copy of backend/app/ - see sync_app.bat) as a read-only host: sets
the environment overrides app/config.py and app/main.py already know how to
read, BEFORE importing anything from app.*, then just serves it. Nothing in
app/ itself contains an "if Android" branch - this file is the only
Android-specific code in the whole request path.

The LAN password stays real HTTP Basic Auth on the wire (app/auth.py's
require_auth, via auth_glue.check_password below) - only how the frontend
COLLECTS it changes (a shadcn password field instead of the browser's
native prompt - see frontend/src/lib/lanAuth.ts). The frontend builds the
same Authorization: Basic header itself and attaches it to every request.

Where things live (all bundled inside this app's Python source tree, next
to this file - Chaquopy extracts the whole src/main/python/ directory to
app-private storage on install):

    dashboard_credentials.json  - the READ-ONLY service account key. Must be
                                  shared as VIEWER (never Editor) on the
                                  manifest spreadsheet below AND on every
                                  viewer's own spreadsheet it lists. NOT
                                  checked into git - copy it here before
                                  building (see auth_glue.py's docstring for
                                  the LAN password, a separate concern).
    auth_config.json             the LAN password's salted hash (see
                                  auth_glue.py) - set from the app's "LAN
                                  Password" card, never over HTTP.
    viewers.json                 the local mirror of the manifest sheet
                                  (see viewers.py) - who can be viewed here,
                                  refreshed automatically, never hand-edited.
    data/                        per-viewer SQLite files (app/db.py's normal
                                  per-user-file convention, reused here for
                                  "viewer" instead of "user") plus the
                                  registry app/db.py bootstraps by default -
                                  unused here since viewers.py never touches
                                  the registry, but harmless.
    static/                      a copy of frontend/dist - the SAME build
                                  the desktop app serves.
"""
import env_setup  # noqa: F401 - side effect: sets env vars app.* reads, see its docstring

import threading
import time

import auth_glue
import viewers
from app.auth import set_password_provider

set_password_provider(auth_glue.check_password)

REFRESH_INTERVAL_SECONDS = 60


def _background_refresh_loop() -> None:
    while True:
        try:
            viewers.refresh_all()
        except Exception:
            pass  # a transient Sheets/network hiccup - try again next tick
        time.sleep(REFRESH_INTERVAL_SECONDS)


def _install_viewer_routes(app) -> None:
    """The web app's UserSwitcher.tsx (ReadOnlyUserSwitcher) calls these -
    the same small contract the old android_dashboard/server.py used to
    serve directly. GET, not POST, even for switching: app/main.py's
    enforce_read_only middleware blocks every non-GET/HEAD/OPTIONS request
    on this `app` instance, including routes added here afterwards, and
    picking who to VIEW isn't a ledger write worth carving a middleware
    exception for. Spliced in at the FRONT of app.routes, not appended -
    app/main.py's own catch-all SPA route ("/{full_path:path}") is a path
    converter that matches everything, so routes added after it would never
    be reached if simply appended.

    dependencies=[Depends(require_auth)] is required here explicitly - a
    freshly created APIRouter has no idea about the LAN password gate every
    other router gets via app.main's `dependencies=_auth` on
    include_router(). Without this, an early version of this file let
    anyone on the LAN read the viewer list (names + whether each has a
    password) with no LAN password at all."""
    import fastapi
    from fastapi import Depends

    from app.auth import require_auth

    router = fastapi.APIRouter(dependencies=[Depends(require_auth)])

    @router.get("/users")
    def _list_viewers():
        return [
            {"name": name, "has_password": viewers.has_password(name)}
            for name in viewers.list_viewers()
        ]

    @router.get("/api/active_user")
    def _get_active_viewer(viewer: str = fastapi.Cookie(default=None)):
        # This browser's own cookie wins if it names a real viewer -
        # otherwise fall back to the server-wide default (set from
        # MainActivity.kt, or auto-picked by get_active_viewer()). See
        # viewers.py's module docstring for why there are two mechanisms.
        name = viewer if (viewer and viewer in viewers.list_viewers()) else viewers.get_active_viewer()
        if name is None:
            raise fastapi.HTTPException(404, "No viewers available yet, or all require a password")
        return {"name": name}

    @router.get("/api/active_user/{name}")
    def _set_active_viewer(name: str, response: fastapi.Response, password: str = ""):
        # check_viewer_password(), NOT activate_viewer() - this must never
        # touch the shared global default, or switching from one browser
        # would yank every other device currently viewing the dashboard.
        # The cookie scopes the choice to THIS browser only.
        try:
            viewers.check_viewer_password(name, password)
        except viewers.WrongPassword as e:
            raise fastapi.HTTPException(401, str(e)) from e
        except ValueError as e:
            raise fastapi.HTTPException(404, str(e)) from e
        response.set_cookie("viewer", name, httponly=True, samesite="lax", max_age=60 * 60 * 24 * 30)
        return {"name": name}

    app.routes[0:0] = router.routes


def _install_session_override(app) -> None:
    """Makes every /api/* read (dashboard, transactions, categories, ...)
    resolve per-browser instead of through app.db's single process-wide
    "currently active" engine - without this, two devices open on the
    dashboard at once would fight over one shared pointer: switching viewer
    on one browser would silently switch what the OTHER browser sees too,
    mid-session. FastAPI's dependency_overrides is the officially-supported
    way to swap this in for exactly this `app` instance, with ZERO changes
    to app/db.py or any app/api/*.py route - they all just keep writing
    `Depends(get_session)` same as desktop."""
    import fastapi

    from app.db import get_session

    def _per_browser_session(viewer: str = fastapi.Cookie(default=None)):
        name = viewer if (viewer and viewer in viewers.list_viewers()) else viewers.get_active_viewer()
        if name is None:
            raise fastapi.HTTPException(404, "No viewer selected - switch to one first")
        yield from viewers.get_request_session(name)

    app.dependency_overrides[get_session] = _per_browser_session


def start_server(host: str = "0.0.0.0", port: int = 8000) -> None:
    import uvicorn

    from app.main import app

    _install_viewer_routes(app)
    _install_session_override(app)
    threading.Thread(target=_background_refresh_loop, daemon=True).start()
    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    start_server()
