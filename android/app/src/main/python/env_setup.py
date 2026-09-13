"""Sets the environment overrides app/config.py and app/main.py read, BEFORE
any app.* module is ever imported in this process - app/config.py's
Settings() singleton and BASE_DIR are both computed once, at first import,
so whichever of server.py / auth_glue.py / viewers.py Kotlin happens to
touch FIRST must have already set these. That's exactly the risk with
putting this logic directly in server.py: MainActivity.kt's LAN-password
and Viewers screens use auth_glue.py/viewers.py directly and can run before
the server has ever been started once, which would import app.config with
Android's overrides missing. Import this module first, before any app.*
import, from all three - re-importing it after the first time is a cheap
no-op (Python only runs a module's top level once)."""
import os
from pathlib import Path

_HERE = Path(__file__).resolve().parent

os.environ.setdefault("BUDGET_TRACKER_HOME", str(_HERE))
os.environ.setdefault("BUDGET_TRACKER_FRONTEND_DIST", str(_HERE / "static"))
os.environ.setdefault("READ_ONLY_MODE", "true")
# The dedicated spreadsheet backend/app/sync/reports.py's
# regenerate_viewer_manifest() publishes {name, spreadsheet_id} rows to -
# shared as Viewer with this app's read-only service account. Fixed per
# install (set once when this phone was set up), not user-configurable from
# the phone itself - onboarding a person, including which manifest they
# come from, is a desktop-only action.
os.environ.setdefault("VIEWER_MANIFEST_SPREADSHEET_ID", "1oQAJ20668EfJZX6SRjNy0qa3W8hbHJzCmBHYvmwmTbY")
