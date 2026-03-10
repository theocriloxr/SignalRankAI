from __future__ import annotations

import os
from config import config
from contextlib import asynccontextmanager
from typing import AsyncIterator, Optional

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool


def get_database_url() -> Optional[str]:
    url = config.DATABASE_URL
    if not url:
        return None
    url = url.strip()
    # Railway commonly provides postgres:// or postgresql:// URLs.
    # SQLAlchemy async requires the asyncpg dialect.
    if url.startswith("postgresql+asyncpg://"):
        return url
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql+asyncpg://", 1)
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+asyncpg://", 1)
    return url


def create_engine() -> Optional[AsyncEngine]:
    url = get_database_url()
    if not url:
        return None
    # In single-service mode (RUN_MODE=all) we run multiple threads/loops (web, bot,
    # worker, engine). Sharing a pooled asyncpg connection pool across event loops
    # can trigger "Future attached to a different loop" errors during connection
    # cleanup. Using NullPool avoids cross-loop pool reuse.
    mode = (os.getenv("RUN_MODE") or "").strip().lower()
    poolclass = NullPool if mode == "all" else None
    if poolclass is None:
        return create_async_engine(url, pool_pre_ping=True)
    return create_async_engine(url, pool_pre_ping=True, poolclass=poolclass)


def create_sessionmaker(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)



# --- Per-event-loop engine/session cache ---
import asyncio
from sqlalchemy import text
_engine_cache = {}
_sessionmaker_cache = {}
_schema_checked = False

def get_engine_for_event_loop() -> Optional[AsyncEngine]:
    loop = asyncio.get_event_loop()
    if loop in _engine_cache:
        return _engine_cache[loop]
    engine = create_engine()
    if engine is not None:
        _engine_cache[loop] = engine
    return engine

def get_sessionmaker_for_event_loop() -> Optional[async_sessionmaker[AsyncSession]]:
    loop = asyncio.get_event_loop()
    if loop in _sessionmaker_cache:
        return _sessionmaker_cache[loop]
    engine = get_engine_for_event_loop()
    if engine is None:
        return None
    sm = create_sessionmaker(engine)
    _sessionmaker_cache[loop] = sm
    return sm


@asynccontextmanager
async def get_session() -> AsyncIterator[AsyncSession]:
    SessionLocal = get_sessionmaker_for_event_loop()
    if SessionLocal is None:
        raise RuntimeError("DATABASE_URL is not configured")
    async with SessionLocal() as session:
        global _schema_checked
        if not _schema_checked:
            try:
                await session.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS premium_until TIMESTAMP"))
                await session.execute(text("ALTER TABLE subscriptions ADD COLUMN IF NOT EXISTS bonus_days INTEGER"))
                await session.execute(text(
                    """
                    CREATE TABLE IF NOT EXISTS decision_log (
                        id SERIAL PRIMARY KEY,
                        signal_id VARCHAR(36),
                        asset VARCHAR(32),
                        timeframe VARCHAR(8),
                        decision VARCHAR(32) NOT NULL,
                        reason TEXT,
                        meta JSONB NOT NULL DEFAULT '{}'::jsonb,
                        created_at TIMESTAMP NOT NULL DEFAULT NOW()
                    )
                    """
                ))
                await session.execute(text("CREATE INDEX IF NOT EXISTS ix_decision_log_signal_id ON decision_log(signal_id)"))
                await session.execute(text("CREATE INDEX IF NOT EXISTS ix_decision_log_asset ON decision_log(asset)"))
                await session.execute(text("CREATE INDEX IF NOT EXISTS ix_decision_log_timeframe ON decision_log(timeframe)"))
                await session.execute(text("CREATE INDEX IF NOT EXISTS ix_decision_log_decision ON decision_log(decision)"))
                await session.execute(text("CREATE INDEX IF NOT EXISTS ix_decision_log_created_at ON decision_log(created_at)"))

                await session.execute(text(
                    """
                    CREATE TABLE IF NOT EXISTS ml_rejected_signals (
                        id SERIAL PRIMARY KEY,
                        asset VARCHAR(32) NOT NULL,
                        timeframe VARCHAR(8) NOT NULL,
                        direction VARCHAR(8) NOT NULL,
                        entry DOUBLE PRECISION NOT NULL,
                        stop_loss DOUBLE PRECISION NOT NULL,
                        take_profit TEXT NOT NULL,
                        ml_probability DOUBLE PRECISION NOT NULL,
                        rejection_reason VARCHAR(128) NOT NULL,
                        features JSONB NOT NULL DEFAULT '{}'::jsonb,
                        actual_outcome VARCHAR(32),
                        outcome_tracked_at TIMESTAMP,
                        created_at TIMESTAMP NOT NULL DEFAULT NOW()
                    )
                    """
                ))
                await session.execute(text("CREATE INDEX IF NOT EXISTS ix_ml_rejected_signals_asset ON ml_rejected_signals(asset)"))
                await session.execute(text("CREATE INDEX IF NOT EXISTS ix_ml_rejected_signals_timeframe ON ml_rejected_signals(timeframe)"))
                await session.execute(text("CREATE INDEX IF NOT EXISTS ix_ml_rejected_signals_actual_outcome ON ml_rejected_signals(actual_outcome)"))

                # MT5 credentials table
                await session.execute(text(
                    """
                    CREATE TABLE IF NOT EXISTS mt5_credentials (
                        id SERIAL PRIMARY KEY,
                        user_id INTEGER UNIQUE NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                        mt5_login VARCHAR(64) NOT NULL,
                        password_encrypted VARCHAR(512) NOT NULL,
                        server VARCHAR(128) NOT NULL,
                        metaapi_account_id VARCHAR(128),
                        created_at TIMESTAMP NOT NULL DEFAULT NOW(),
                        updated_at TIMESTAMP NOT NULL DEFAULT NOW()
                    )
                    """
                ))
                await session.execute(text("CREATE INDEX IF NOT EXISTS ix_mt5_credentials_user_id ON mt5_credentials(user_id)"))

                # UNLOGGED tables for high-frequency ephemeral state (replaces Redis)
                await session.execute(text(
                    """
                    CREATE UNLOGGED TABLE IF NOT EXISTS daily_signal_counters (
                        user_id BIGINT NOT NULL,
                        date DATE NOT NULL,
                        count INTEGER NOT NULL DEFAULT 0,
                        PRIMARY KEY (user_id, date)
                    )
                    """
                ))
                await session.execute(text(
                    """
                    CREATE UNLOGGED TABLE IF NOT EXISTS rate_limit_tokens (
                        user_id BIGINT NOT NULL,
                        window_key VARCHAR(64) NOT NULL,
                        hits INTEGER NOT NULL DEFAULT 0,
                        window_start TIMESTAMP NOT NULL,
                        PRIMARY KEY (user_id, window_key)
                    )
                    """
                ))

                await session.commit()
            except Exception:
                # Best-effort; keep app running
                try:
                    await session.rollback()
                except Exception:
                    pass
            _schema_checked = True
        yield session


# Backward-compatible alias used by repository and other modules.
@asynccontextmanager
async def async_session() -> AsyncIterator[AsyncSession]:
    SessionLocal = get_sessionmaker_for_event_loop()
    if SessionLocal is None:
        raise RuntimeError("DATABASE_URL is not configured")
    async with SessionLocal() as session:
        yield session
