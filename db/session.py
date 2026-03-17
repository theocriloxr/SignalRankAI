from __future__ import annotations

import logging
import os
import socket as _socket
import threading
from config import config
from contextlib import asynccontextmanager
from typing import AsyncIterator, Optional

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool
from sqlalchemy import text

logger = logging.getLogger(__name__)


def _engine_connect_args() -> dict:
    """Return asyncpg connection args tuned for Railway network conditions."""
    try:
        connect_timeout = float((os.getenv("DB_CONNECT_TIMEOUT") or "15").strip())
    except Exception:
        connect_timeout = 15.0
    try:
        command_timeout = float((os.getenv("DB_COMMAND_TIMEOUT") or "45").strip())
    except Exception:
        command_timeout = 45.0
    app_name = (os.getenv("DB_APP_NAME") or "signalrankai").strip() or "signalrankai"
    return {
        "timeout": connect_timeout,
        "command_timeout": command_timeout,
        "server_settings": {"application_name": app_name},
    }


def _prefer_ipv4_url(url: str) -> str:
    """Resolve the database hostname to an IPv4 address and substitute it in
    the URL before handing it to asyncpg.

    Railway's internal Postgres hostnames (*.railway.internal) sometimes
    resolve to an IPv6 address first.  asyncpg picks that address, attempts to
    connect, and gets ECONNREFUSED because Railway's Postgres only listens on
    IPv4.  psycopg2 (used by Alembic / auto_ops) retries all addresses and
    falls back to IPv4 automatically, which is why migrations succeed while
    async DB calls fail.

    This helper resolves the host to its first AF_INET (IPv4) address and
    rewrites the URL so asyncpg never even sees the IPv6 address.
    Returns the original URL unchanged on any error or when the host is
    already an IP literal.
    """
    try:
        from sqlalchemy.engine.url import make_url
        sa_url = make_url(url)
        host = sa_url.host
        if not host:
            return url
        # Already an IPv4 literal (digits + dots) or bracketed IPv6 literal — skip
        if ":" in host or all(c in "0123456789." for c in host):
            return url
        port = int(sa_url.port or 5432)
        infos = _socket.getaddrinfo(host, port, _socket.AF_INET, _socket.SOCK_STREAM)
        if not infos:
            return url
        ipv4 = infos[0][4][0]
        # IMPORTANT: use render_as_string(hide_password=False) — NOT str().
        # SQLAlchemy 2.x's str(url) redacts the password as "***", which causes
        # asyncpg to authenticate with the literal string "***" and get
        # "password authentication failed for user postgres" from the server.
        return sa_url.set(host=ipv4).render_as_string(hide_password=False)
    except Exception:
        # Never break the connection — fall back to original URL
        return url


def get_database_url() -> Optional[str]:
    """Return the async-compatible database URL.

    Priority (evaluated fresh on every call so late-set env vars are always picked up):
      1. DATABASE_PUBLIC_URL  — Railway external IPv4 proxy (avoids IPv6 ECONNREFUSED)
      2. DATABASE_URL         — standard env var (read directly, NOT from Config snapshot)
      3. config.DATABASE_URL  — import-time fallback

    Raises ValueError if NO url is configured so callers get a clear error message
    instead of asyncpg silently falling back to the local 'postgres' user.
    """
    raw = (
        os.getenv("DATABASE_PUBLIC_URL")
        or os.getenv("DATABASE_URL")
        or config.DATABASE_URL
        or ""
    ).strip()
    if not raw:
        raise ValueError(
            "DATABASE_URL is not set. "
            "Set DATABASE_URL (or DATABASE_PUBLIC_URL) as an environment variable."
        )
    # Normalise to asyncpg dialect
    if raw.startswith("postgresql+asyncpg://"):
        return _prefer_ipv4_url(raw)
    if raw.startswith("postgres://"):
        return _prefer_ipv4_url(raw.replace("postgres://", "postgresql+asyncpg://", 1))
    if raw.startswith("postgresql://"):
        return _prefer_ipv4_url(raw.replace("postgresql://", "postgresql+asyncpg://", 1))
    return _prefer_ipv4_url(raw)


def get_database_url_or_none() -> Optional[str]:
    """Like get_database_url() but returns None instead of raising, for optional checks."""
    try:
        return get_database_url()
    except ValueError:
        return None


def create_engine() -> Optional[AsyncEngine]:
    url = get_database_url_or_none()
    if not url:
        return None
    # In single-service mode (RUN_MODE=all) we run multiple threads/loops (web, bot,
    # worker, engine). Sharing a pooled asyncpg connection pool across event loops
    # can trigger "Future attached to a different loop" errors during connection
    # cleanup. Using NullPool avoids cross-loop pool reuse.
    mode = (os.getenv("RUN_MODE") or "").strip().lower()
    poolclass = NullPool if mode == "all" else None
    connect_args = _engine_connect_args()
    if poolclass is None:
        return create_async_engine(url, pool_pre_ping=True, connect_args=connect_args)
    return create_async_engine(url, pool_pre_ping=True, poolclass=poolclass, connect_args=connect_args)


def create_sessionmaker(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


# ---------------------------------------------------------------------------
# Thread-safe engine cache (per thread)
# ---------------------------------------------------------------------------
# A single AsyncEngine object can still carry loop-bound async internals
# (notably first-connect / event execution mutexes). Sharing one engine across
# multiple event loops/threads can trigger:
#   RuntimeError: <asyncio.locks.Lock ...> is bound to a different event loop
#
# To avoid cross-loop contamination we keep one engine/sessionmaker per thread.
# Each thread may run its own event loop safely with its own engine object.
# ---------------------------------------------------------------------------

_global_engine: Optional[AsyncEngine] = None  # Backward-compat reference only
_global_sessionmaker: Optional[async_sessionmaker[AsyncSession]] = None
_engines_by_thread: dict[int, AsyncEngine] = {}
_sessionmakers_by_thread: dict[int, async_sessionmaker[AsyncSession]] = {}
_global_engine_lock = threading.Lock()
_schema_checked = False


def _get_global_engine() -> Optional[AsyncEngine]:
    """Return (creating if necessary) the async engine for current thread.

    Thread-safe cache by thread id. Never touches asyncio — safe to call from
    any thread, with or without a running event loop.
    """
    global _global_engine, _global_sessionmaker
    tid = int(threading.get_ident())
    existing = _engines_by_thread.get(tid)
    if existing is not None:
        return existing
    with _global_engine_lock:
        existing = _engines_by_thread.get(tid)
        if existing is not None:  # re-check after lock
            return existing
        try:
            url = get_database_url()  # raises ValueError if not set
        except ValueError as _ve:
            logger.critical(
                "[db] DATABASE_URL is not configured — cannot create async engine. "
                "Set DATABASE_URL or DATABASE_PUBLIC_URL in your environment. (%s)", _ve
            )
            return None
        # Always NullPool + per-thread engine object to avoid cross-event-loop
        # lock binding errors in multi-thread runtime.
        engine = create_async_engine(
            url,
            pool_pre_ping=True,
            poolclass=NullPool,
            connect_args=_engine_connect_args(),
        )
        sm = async_sessionmaker(engine, expire_on_commit=False)
        _engines_by_thread[tid] = engine
        _sessionmakers_by_thread[tid] = sm
        # Backward compatibility for modules peeking at globals.
        _global_engine = engine
        _global_sessionmaker = sm
        # Log the masked URL so Railway logs confirm the right DB is in use
        try:
            from sqlalchemy.engine.url import make_url as _mku
            _mu = _mku(url)
            _masked = f"{_mu.drivername}://{_mu.username}:***@{_mu.host}:{_mu.port}/{_mu.database}"
        except Exception:
            _masked = "<url parse error>"
        logger.info("[db] async engine initialised  url=%s  pool=NullPool", _masked)
        return engine


def _get_global_sessionmaker() -> Optional[async_sessionmaker[AsyncSession]]:
    _get_global_engine()  # ensure current-thread engine/sessionmaker exists
    tid = int(threading.get_ident())
    sm = _sessionmakers_by_thread.get(tid)
    if sm is not None:
        return sm
    return _global_sessionmaker


# ---------------------------------------------------------------------------
# Backward-compatible aliases (some modules import these by name)
# ---------------------------------------------------------------------------
def get_engine_for_event_loop() -> Optional[AsyncEngine]:
    """Deprecated alias for _get_global_engine().

    Previously cached engines per-event-loop; now returns the global
    NullPool singleton so callers keep working without changes.
    """
    return _get_global_engine()


def get_sessionmaker_for_event_loop() -> Optional[async_sessionmaker[AsyncSession]]:
    """Deprecated alias for _get_global_sessionmaker()."""
    return _get_global_sessionmaker()


def is_db_configured() -> bool:
    """Return True if a database URL is configured (engine can be created)."""
    return _get_global_engine() is not None


@asynccontextmanager
async def get_session() -> AsyncIterator[AsyncSession]:
    SessionLocal = _get_global_sessionmaker()
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

                # ── Enterprise feature tables ───────────────────────────────────────────

                # User engagement reactions (🔥 taking_it / 👀 watching)
                await session.execute(text(
                    """
                    CREATE TABLE IF NOT EXISTS signal_engagements (
                        id SERIAL PRIMARY KEY,
                        user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                        signal_id VARCHAR(36) NOT NULL REFERENCES signals(signal_id) ON DELETE CASCADE,
                        reaction VARCHAR(16) NOT NULL,
                        created_at TIMESTAMP NOT NULL DEFAULT NOW(),
                        CONSTRAINT uq_signal_engagement_user_signal UNIQUE (user_id, signal_id)
                    )
                    """
                ))
                await session.execute(text("CREATE INDEX IF NOT EXISTS ix_signal_engagements_user_id ON signal_engagements(user_id)"))
                await session.execute(text("CREATE INDEX IF NOT EXISTS ix_signal_engagements_signal_id ON signal_engagements(signal_id)"))
                await session.execute(text("CREATE INDEX IF NOT EXISTS ix_signal_engagements_reaction ON signal_engagements(reaction)"))

                # Active signal message tracking (for inline keyboard live-editing)
                await session.execute(text(
                    """
                    CREATE TABLE IF NOT EXISTS active_signal_messages (
                        id SERIAL PRIMARY KEY,
                        user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                        signal_id VARCHAR(36) NOT NULL REFERENCES signals(signal_id) ON DELETE CASCADE,
                        chat_id BIGINT NOT NULL,
                        message_id BIGINT NOT NULL,
                        is_active BOOLEAN NOT NULL DEFAULT TRUE,
                        created_at TIMESTAMP NOT NULL DEFAULT NOW(),
                        CONSTRAINT uq_active_signal_msg_user_signal UNIQUE (user_id, signal_id)
                    )
                    """
                ))
                await session.execute(text("CREATE INDEX IF NOT EXISTS ix_active_signal_messages_user_id ON active_signal_messages(user_id)"))
                await session.execute(text("CREATE INDEX IF NOT EXISTS ix_active_signal_messages_signal_id ON active_signal_messages(signal_id)"))
                await session.execute(text("CREATE INDEX IF NOT EXISTS ix_active_signal_messages_is_active ON active_signal_messages(is_active)"))

                # Economic calendar events (macro news protector cache)
                await session.execute(text(
                    """
                    CREATE TABLE IF NOT EXISTS economic_events (
                        id SERIAL PRIMARY KEY,
                        event_date TIMESTAMP NOT NULL,
                        currency VARCHAR(8) NOT NULL,
                        title VARCHAR(256) NOT NULL,
                        impact VARCHAR(8) NOT NULL DEFAULT 'low',
                        source VARCHAR(64),
                        fetched_at TIMESTAMP NOT NULL DEFAULT NOW()
                    )
                    """
                ))
                await session.execute(text("CREATE INDEX IF NOT EXISTS ix_economic_events_event_date ON economic_events(event_date)"))
                await session.execute(text("CREATE INDEX IF NOT EXISTS ix_economic_events_currency ON economic_events(currency)"))
                await session.execute(text("CREATE INDEX IF NOT EXISTS ix_economic_events_impact ON economic_events(impact)"))

                # MT5 execution log (tier-gated order tracking)
                await session.execute(text(
                    """
                    CREATE TABLE IF NOT EXISTS mt5_executions (
                        id SERIAL PRIMARY KEY,
                        user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                        signal_id VARCHAR(36) REFERENCES signals(signal_id) ON DELETE SET NULL,
                        metaapi_account_id VARCHAR(128) NOT NULL,
                        order_id VARCHAR(128),
                        symbol VARCHAR(32) NOT NULL,
                        direction VARCHAR(8) NOT NULL,
                        lot_size FLOAT NOT NULL,
                        entry_price FLOAT NOT NULL,
                        stop_loss FLOAT NOT NULL,
                        take_profit TEXT NOT NULL,
                        status VARCHAR(16) NOT NULL DEFAULT 'pending',
                        tier_at_execution VARCHAR(16) NOT NULL DEFAULT 'premium',
                        realized_pnl FLOAT,
                        realized_pnl_pct FLOAT,
                        executed_at TIMESTAMP NOT NULL DEFAULT NOW(),
                        closed_at TIMESTAMP,
                        meta JSONB NOT NULL DEFAULT '{}'
                    )
                    """
                ))
                await session.execute(text("CREATE INDEX IF NOT EXISTS ix_mt5_executions_user_id ON mt5_executions(user_id)"))
                await session.execute(text("CREATE INDEX IF NOT EXISTS ix_mt5_executions_signal_id ON mt5_executions(signal_id)"))
                await session.execute(text("CREATE INDEX IF NOT EXISTS ix_mt5_executions_status ON mt5_executions(status)"))

                # VIP waitlist (capacity overflow queue)
                await session.execute(text(
                    """
                    CREATE TABLE IF NOT EXISTS vip_waitlist (
                        id SERIAL PRIMARY KEY,
                        user_id INTEGER UNIQUE NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                        joined_at TIMESTAMP NOT NULL DEFAULT NOW(),
                        notified_at TIMESTAMP
                    )
                    """
                ))
                await session.execute(text("CREATE INDEX IF NOT EXISTS ix_vip_waitlist_user_id ON vip_waitlist(user_id)"))
                await session.execute(text("ALTER TABLE vip_waitlist ADD COLUMN IF NOT EXISTS invited_at TIMESTAMP"))
                await session.execute(text("ALTER TABLE vip_waitlist ADD COLUMN IF NOT EXISTS invite_expires_at TIMESTAMP"))
                await session.execute(text("CREATE INDEX IF NOT EXISTS ix_vip_waitlist_invite_expires_at ON vip_waitlist(invite_expires_at)"))

                # ── New columns on existing tables (idempotent via IF NOT EXISTS) ───────

                # users: referral + MT5 execution settings
                await session.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS referred_by BIGINT"))
                await session.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS fixed_lot_size FLOAT NOT NULL DEFAULT 0.01"))
                await session.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS daily_executions_today INTEGER NOT NULL DEFAULT 0"))
                await session.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS daily_executions_reset_at TIMESTAMP"))
                await session.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS max_risk_percentage FLOAT NOT NULL DEFAULT 1.0"))
                await session.execute(text("CREATE INDEX IF NOT EXISTS ix_users_referred_by ON users(referred_by)"))
                await session.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS paystack_subscription_code VARCHAR(128)"))
                await session.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS paystack_customer_code VARCHAR(128)"))
                await session.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS auto_renew BOOLEAN NOT NULL DEFAULT TRUE"))
                await session.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS accepted_terms BOOLEAN NOT NULL DEFAULT FALSE"))
                await session.execute(text("CREATE INDEX IF NOT EXISTS ix_users_paystack_subscription_code ON users(paystack_subscription_code)"))

                # signals: auto-expiry + order-block enrichment
                await session.execute(text("ALTER TABLE signals ADD COLUMN IF NOT EXISTS expires_at TIMESTAMP"))
                await session.execute(text("ALTER TABLE signals ADD COLUMN IF NOT EXISTS expired BOOLEAN NOT NULL DEFAULT FALSE"))
                await session.execute(text("ALTER TABLE signals ADD COLUMN IF NOT EXISTS is_near_order_block BOOLEAN NOT NULL DEFAULT FALSE"))
                await session.execute(text("CREATE INDEX IF NOT EXISTS ix_signals_expires_at ON signals(expires_at)"))
                await session.execute(text("CREATE INDEX IF NOT EXISTS ix_signals_expired ON signals(expired)"))

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
    SessionLocal = _get_global_sessionmaker()
    if SessionLocal is None:
        raise RuntimeError("DATABASE_URL is not configured")
    async with SessionLocal() as session:
        yield session
