from functools import lru_cache
from pathlib import Path

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_base_url: str = "http://localhost:5173"
    database_url: str = "sqlite+aiosqlite:///./var/plush-pattern-studio.db"
    redis_url: str | None = None
    object_storage_mode: str = "local"
    object_storage_path: Path = Path("./var/objects")
    object_storage_endpoint: str | None = None
    object_storage_bucket: str | None = None
    object_storage_access_key: SecretStr | None = None
    object_storage_secret_key: SecretStr | None = None
    google_client_id: str | None = None
    google_client_secret: SecretStr | None = None
    openrouter_api_key: SecretStr | None = None
    openrouter_model: str = "google/gemini-3.5-flash-lite"
    meshy_api_key: SecretStr | None = None
    session_secret: SecretStr | None = None


@lru_cache
def get_settings() -> Settings:
    return Settings()
