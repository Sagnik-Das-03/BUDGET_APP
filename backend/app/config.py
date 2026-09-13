import os
from pathlib import Path

from app._pydantic_compat import PYDANTIC_V2, BaseSettings, SettingsConfigDict

# Overridable so the Android host (see android/app/src/main/python/server.py)
# can point this at Chaquopy's app-private storage instead of a sibling of
# this file, which doesn't exist as a writable location on Android. Not read
# anywhere by desktop/Docker, which never sets this env var.
BASE_DIR = Path(os.environ["BUDGET_TRACKER_HOME"]) if os.environ.get("BUDGET_TRACKER_HOME") \
    else Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    if PYDANTIC_V2:
        model_config = SettingsConfigDict(env_file=BASE_DIR / ".env", env_file_encoding="utf-8", extra="ignore")
    else:
        class Config:
            env_file = str(BASE_DIR / ".env")
            env_file_encoding = "utf-8"
            extra = "ignore"

    # Shared fallback only - a user with no service account key of their own
    # (Settings -> Google Sheets sync -> upload credentials) uses this one.
    # Not read anywhere else at request time once a user has their own.
    google_service_account_key_path: str = ""
    # Legacy - only ever consulted once, to migrate the original single-user
    # setup's spreadsheet into that SAME user's own per-user setting (see
    # app/sync/scheduler.py's _migrate_legacy_spreadsheet_id). Every user's
    # actual spreadsheet id lives in their own database from then on -
    # configure/change it from Settings, not here.
    google_spreadsheet_id: str = ""
    sync_interval_seconds: int = 45
    # HTTP Basic Auth - off by default. Set both to turn it on (see docs).
    auth_username: str = ""
    auth_password: str = ""
    app_host: str = "127.0.0.1"
    app_port: int = 8000
    # Directory holding .litertlm model files for local AI features (see app/llm/).
    # Empty = default to backend/models.
    lite_llm_models_dir: str = ""
    # "cpu" (default, dependable) or "gpu" (real speedup when it works, but
    # was unreliable in past testing on this machine - engine creation can
    # succeed while later inference calls fail outright). Opt-in per
    # app/llm/router.py's per-call fallback: a failed GPU call retries once
    # on CPU and that model then stays on CPU for the rest of the process,
    # rather than silently staying broken or paying the failure cost twice.
    llm_backend: str = "cpu"
    # Set by the Android host only (server.py) - see app/main.py's
    # read-only middleware. Never set on desktop/Docker, where it stays
    # False and that middleware is a no-op.
    read_only_mode: bool = False
    # A separate, dedicated spreadsheet (not any single user's own) that
    # regenerate_viewer_manifest() publishes {username, spreadsheet_id} rows
    # to - the only way the Android host learns which viewers exist (see
    # android/app/src/main/python/viewers.py). Empty = manifest publishing
    # is a no-op, so this feature is entirely opt-in.
    viewer_manifest_spreadsheet_id: str = ""

    @property
    def lite_llm_dir(self) -> Path:
        if self.lite_llm_models_dir:
            return Path(self.lite_llm_models_dir)
        return BASE_DIR / "models"

    @property
    def auth_enabled(self) -> bool:
        return bool(self.auth_username and self.auth_password)


settings = Settings()
