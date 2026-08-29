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

    @property
    def db_url(self) -> str:
        db_file = (BASE_DIR / self.db_path).resolve()
        db_file.parent.mkdir(parents=True, exist_ok=True)
        return f"sqlite:///{db_file}"

    @property
    def credentials_configured(self) -> bool:
        return bool(self.google_service_account_key_path) and Path(self.google_service_account_key_path).exists()

    @property
    def auth_enabled(self) -> bool:
        return bool(self.auth_username and self.auth_password)


settings = Settings()
