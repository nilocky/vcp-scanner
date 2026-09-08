from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env.local", ".env", "../.env.local", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "VCP Scanner"
    port: int = 8000
    cors_origins: list[str] = ["http://localhost:5173"]

    llm_base_url: str = "https://api.deepseek.com/v1"
    llm_api_key: str = ""
    llm_model: str = "deepseek-chat"
    llm_timeout_seconds: float = 60.0

    telegram_bot_token: str = ""
    telegram_chat_id: str = ""

    tv_scan_timeout_seconds: float = 30.0

    db_path: str = "data/bars.db"
    backfill_concurrency: int = 5
    history_period: str = "1y"


@lru_cache
def get_settings() -> Settings:
    return Settings()