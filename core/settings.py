from __future__ import annotations

import os

try:
    # pydantic v2 separates settings into pydantic_settings
    from pydantic_settings import BaseSettings
    _PYDANTIC_V2_SETTINGS = True
except Exception:
    try:
        from pydantic import BaseSettings
        _PYDANTIC_V2_SETTINGS = False
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
    ML_MODEL_PATH: Optional[str] = None
    RUN_MODE: str = "engine"
    PAPER_MODE: bool = False

    # Feature flags
    ENABLE_NEWS: bool = True
    ENABLE_ML: bool = True

    # Logging / observability
    LOG_JSON: bool = False
    SENTRY_TRACES_SAMPLE_RATE: float = 0.0

    # Telegram timeouts
    TELEGRAM_POOL_TIMEOUT: int = 30
    TELEGRAM_CONNECT_TIMEOUT: int = 30
    TELEGRAM_READ_TIMEOUT: int = 30
    TELEGRAM_WRITE_TIMEOUT: int = 30

    if not globals().get("_PYDANTIC_V2_SETTINGS", False):
        class Config:
            env_file = ".env"
            env_file_encoding = "utf-8"
            extra = "ignore"
    else:
        model_config = {
            "env_file": ".env",
            "env_file_encoding": "utf-8",
            "extra": "ignore",
        }


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    if not _settings.DATABASE_URL:
        try:
            from config import resolve_database_url
            resolved = resolve_database_url(async_driver=True)
        except Exception:
            resolved = None
        if resolved:
            _settings.DATABASE_URL = resolved
    return _settings


def validate_required_settings() -> None:
    import logging as _logging
    s = get_settings()
    _log = _logging.getLogger(__name__)
    fatal: list[str] = []
    warnings: list[str] = []
    # DATABASE_URL is always required
    if not s.DATABASE_URL:
        fatal.append("DATABASE_URL")
    # TELEGRAM_BOT_TOKEN: fatal only for pure bot service, warning for everything else
    if not s.TELEGRAM_BOT_TOKEN:
        if s.RUN_MODE == "bot":
            fatal.append("TELEGRAM_BOT_TOKEN")
        elif s.RUN_MODE == "all":
            warnings.append("TELEGRAM_BOT_TOKEN (bot will be disabled in RUN_MODE=all)")
    if warnings:
        _log.warning("[settings] Optional settings missing: %s", ", ".join(warnings))
    if fatal:
        raise RuntimeError(f"Missing required settings: {', '.join(fatal)}")
