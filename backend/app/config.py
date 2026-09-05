from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=BASE_DIR / ".env", env_file_encoding="utf-8", extra="ignore")

    google_service_account_key_path: str = ""
    google_spreadsheet_id: str = ""
    owner_email: str = ""
    sync_interval_seconds: int = 45
    # HTTP Basic Auth - off by default. Set both to turn it on (see docs).
    auth_username: str = ""
    auth_password: str = ""
    db_path: str = "data/budget_tracker.db"
    app_host: str = "127.0.0.1"
    app_port: int = 8000
    # Directory holding .litertlm model files for local AI features (see app/llm/).
    # Empty = default to backend/models.
    lite_llm_models_dir: str = ""
    # Path to the external backup script (backup_program/start.bat) triggered on
    # shutdown - see app/backup.py. Empty = default to a sibling "backup_program"
    # folder next to this project.
    backup_script_path: str = ""

    @property
    def db_url(self) -> str:
        db_file = (BASE_DIR / self.db_path).resolve()
        db_file.parent.mkdir(parents=True, exist_ok=True)
        return f"sqlite:///{db_file}"

    @property
    def lite_llm_dir(self) -> Path:
        if self.lite_llm_models_dir:
            return Path(self.lite_llm_models_dir)
        return BASE_DIR / "models"

    @property
    def backup_script(self) -> Path:
        if self.backup_script_path:
            return Path(self.backup_script_path)
        return BASE_DIR.parent.parent / "backup_program" / "start.bat"

    @property
    def credentials_configured(self) -> bool:
        return bool(self.google_service_account_key_path) and Path(self.google_service_account_key_path).exists()

    @property
    def auth_enabled(self) -> bool:
        return bool(self.auth_username and self.auth_password)


settings = Settings()
