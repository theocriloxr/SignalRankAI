from __future__ import annotations

try:
    # pydantic v2 separates settings into pydantic_settings
    from pydantic_settings import BaseSettings
except Exception:
    try:
        from pydantic import BaseSettings
    except Exception:
        raise
from typing import Optional


class Settings(BaseSettings):
    # Required
    DATABASE_URL: str
    REDIS_URL: Optional[str] = None
    TELEGRAM_BOT_TOKEN: Optional[str] = None
    SENTRY_DSN: Optional[str] = None
    NEWS_API_KEY: Optional[str] = None
    XGBOOST_MODEL_PATH: Optional[str] = None
    RUN_MODE: str = "engine"
    PAPER_MODE: bool = False

    # Feature flags
    ENABLE_NEWS: bool = True
    ENABLE_ML: bool = False

    # Logging / observability
    LOG_JSON: bool = False
    SENTRY_TRACES_SAMPLE_RATE: float = 0.0

    # Telegram timeouts
    TELEGRAM_POOL_TIMEOUT: int = 30
    TELEGRAM_CONNECT_TIMEOUT: int = 30
    TELEGRAM_READ_TIMEOUT: int = 30
    TELEGRAM_WRITE_TIMEOUT: int = 30

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
    # pydantic v2 uses `model_config` for settings; keep both for compatibility
    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
    }


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings


def validate_required_settings() -> None:
    s = get_settings()
    missing = []
    if not s.DATABASE_URL:
        missing.append("DATABASE_URL")
    # Tele bot token is optional in DRY_RUN but warn if RUN_MODE requires it
    if s.RUN_MODE in ("bot", "all") and not s.TELEGRAM_BOT_TOKEN:
        missing.append("TELEGRAM_BOT_TOKEN")
    if missing:
        raise RuntimeError(f"Missing required settings: {', '.join(missing)}")
