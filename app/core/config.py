from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Env-backed app config; field values are overridden by matching (case-insensitive)
    entries in .env or the process environment."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "local"
    log_level: str = "info"
    database_url: str = "postgresql+psycopg2://postgres:postgres@localhost:5432/ls_process_simulation"
    anthropic_api_key: str | None = None  # required only for the LLM ingestion pipeline


@lru_cache
def get_settings() -> Settings:
    """Cached singleton so .env is parsed once per process, not on every call site."""
    return Settings()
