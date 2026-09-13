"""Android host entry point - Kotlin's ServerService.kt calls
Python.getModule("server").callAttr("start_server"). Runs the REAL backend
(app/, a copy of backend/app/ - see sync_app.bat) as a read-only host: sets
the environment overrides app/config.py and app/main.py already know how to
read, BEFORE importing anything from app.*, then just serves it. Nothing in
app/ itself contains an "if Android" branch - this file is the only
Android-specific code in the whole request path.

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
    be reached if simply appended."""
    import fastapi

    router = fastapi.APIRouter()

    @router.get("/users")
    def _list_viewers():
        return [{"name": name} for name in viewers.list_viewers()]

    @router.get("/api/active_user")
    def _get_active_viewer():
        name = viewers.get_active_viewer()
        if name is None:
            raise fastapi.HTTPException(404, "No viewers available yet")
        return {"name": name}

    @router.get("/api/active_user/{name}")
    def _set_active_viewer(name: str):
        try:
            viewers.activate_viewer(name)
        except ValueError as e:
            raise fastapi.HTTPException(404, str(e)) from e
        return {"name": name}

    app.routes[0:0] = router.routes


def start_server(host: str = "0.0.0.0", port: int = 8000) -> None:
    import uvicorn

    from app.main import app

    _install_viewer_routes(app)
    threading.Thread(target=_background_refresh_loop, daemon=True).start()
    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    start_server()
