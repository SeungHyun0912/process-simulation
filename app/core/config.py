from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "local"
    log_level: str = "info"
    database_url: str = "postgresql+psycopg2://postgres:postgres@localhost:5432/ls_process_simulation"


@lru_cache
def get_settings() -> Settings:
    return Settings()
