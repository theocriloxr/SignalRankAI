from __future__ import annotations


import os
from config import config, resolve_database_url
import time
from datetime import datetime
from typing import Optional


def _env_bool(name: str, default: bool = False) -> bool:
    val = os.getenv(name)
    if val is None:
        return default
    return val.strip().lower() in {"1", "true", "yes", "y", "on"}


def _sync_database_url() -> Optional[str]:
    # Read fresh from environment each call — never use a stale import-time value.
    # Prefer internal/private URLs first; fall back to public/PG* parts when needed.
    url = resolve_database_url(async_driver=False)
    if url:
        return url
    # Last-resort fallback to config snapshot (legacy).
    legacy = (getattr(config, "DATABASE_URL", None) or "").strip()
    if not legacy:
        return None
    if legacy.startswith("postgresql+asyncpg://"):
        return legacy.replace("postgresql+asyncpg://", "postgresql://", 1)
    if legacy.startswith("postgres://"):
        return legacy.replace("postgres://", "postgresql://", 1)
    return legacy


def _advisory_lock_id() -> int:
    # Fixed lock id for this app.
    return 915_337_121


def run_startup_ops(run_mode: str) -> None:
    """Run safe startup operations on Railway.

    - Auto-migrate Postgres schema using Alembic (idempotent), guarded by advisory lock.
    - Optional one-time "fresh start" data wipe controlled by FRESH_START=true.

    This is designed to work with Railway free tier (Postgres only; no Redis).
    """

    db_url = _sync_database_url()
    if not db_url:
        print("[auto_ops] No database URL configured, skipping startup ops", flush=True)
        return
    
    print(f"[auto_ops] Database configured, running startup ops for mode={run_mode}", flush=True)

    # Production hardening: runtime auto-migrate can be disabled, but we still
    # run schema bootstrap safety so fresh databases don't start half-ready.
    auto_migrate_enabled = _env_bool("AUTO_MIGRATE", False)
    strict_schema_ready = _env_bool("STARTUP_STRICT_SCHEMA_READY", False)

    try:
        import psycopg2
    except Exception:
        return

    # Railway can start the app container before Postgres is reachable.
    # Retry briefly to avoid crashing due to transient connection errors.
    try:
        max_attempts = max(1, int((os.getenv("DB_CONNECT_MAX_ATTEMPTS") or "12").strip()))
    except Exception:
        max_attempts = 12
    if not auto_migrate_enabled and not strict_schema_ready:
        # Default to a single attempt when startup isn't strict and migrations
        # are disabled to avoid blocking container boot with retry backoff.
        max_attempts = 1
    try:
        backoff_seconds = max(0.5, float((os.getenv("DB_CONNECT_BACKOFF_SECONDS") or "2").strip()))
    except Exception:
        backoff_seconds = 2.0

    conn = None
    have_lock = False
    try:
        last_err: Exception | None = None
        for attempt in range(1, max_attempts + 1):
            try:
                conn = psycopg2.connect(db_url, connect_timeout=5)
                last_err = None
                break
            except Exception as exc:
                last_err = exc
                # Sleep before retrying (except after final attempt)
                if attempt < max_attempts:
                    time.sleep(backoff_seconds)
        if conn is None:
            # Defer migrations until the next boot if DB is still unreachable.
            return

        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute("SELECT pg_try_advisory_lock(%s)", (_advisory_lock_id(),))
            have_lock = bool((cur.fetchone() or (False,))[0])

        if not have_lock:
            return

        # 1) Migrate schema (optional, env-controlled)
        if auto_migrate_enabled:
            try:
                from alembic import command
                from alembic.config import Config

                cfg = Config("alembic.ini")
                cfg.set_main_option("sqlalchemy.url", db_url)
                command.upgrade(cfg, "head")
            except Exception:
                # If migrations fail, let the service crash to surface the error.
                raise

        # 1b) Failsafe bootstrap for fresh DBs when migrations are skipped or
        # migration graph differs across branches. create_all is idempotent.
        if _env_bool("STARTUP_SCHEMA_BOOTSTRAP", True):
            try:
                from sqlalchemy import create_engine
                from db.models import Base

                eng = create_engine(db_url, pool_pre_ping=True)
                try:
                    Base.metadata.create_all(bind=eng)
                finally:
                    eng.dispose()
            except Exception:
                # Keep startup strict: crash if bootstrap unexpectedly fails.
                raise

        # 2) Optional one-time wipe to "start fresh"
        if _env_bool("FRESH_START", False) and run_mode in {"web", "all"}:
            _fresh_start_if_needed(conn)

# 3) Belt-and-suspenders column patches — safe ADD COLUMN IF NOT EXISTS for
        #    all columns that 0010_consolidate_full_schema migration covers, in case
        #    Alembic is skipped or the DB was bootstrapped outside of migrations.
        try:
            with conn.cursor() as cur:
                _column_patches = [
                    # users
                    "ALTER TABLE users ADD COLUMN IF NOT EXISTS premium_until TIMESTAMP",
                    "ALTER TABLE users ADD COLUMN IF NOT EXISTS referred_by BIGINT",
                    "ALTER TABLE users ADD COLUMN IF NOT EXISTS fixed_lot_size FLOAT NOT NULL DEFAULT 0.01",
                    "ALTER TABLE users ADD COLUMN IF NOT EXISTS daily_executions_today INTEGER NOT NULL DEFAULT 0",
                    "ALTER TABLE users ADD COLUMN IF NOT EXISTS daily_executions_reset_at TIMESTAMP",
                    "ALTER TABLE users ADD COLUMN IF NOT EXISTS max_risk_percentage FLOAT NOT NULL DEFAULT 1.0",
                    "ALTER TABLE users ADD COLUMN IF NOT EXISTS max_daily_drawdown_pct FLOAT NOT NULL DEFAULT 8.0",
                    "ALTER TABLE users ADD COLUMN IF NOT EXISTS execution_mode VARCHAR(16) NOT NULL DEFAULT 'manual'",
                    "ALTER TABLE users ADD COLUMN IF NOT EXISTS auto_signals_daily_limit INTEGER NOT NULL DEFAULT 3",
                    "ALTER TABLE users ADD COLUMN IF NOT EXISTS paystack_subscription_code VARCHAR(128)",
                    "ALTER TABLE users ADD COLUMN IF NOT EXISTS paystack_customer_code VARCHAR(128)",
                    "ALTER TABLE users ADD COLUMN IF NOT EXISTS auto_renew BOOLEAN NOT NULL DEFAULT TRUE",
                    "ALTER TABLE users ADD COLUMN IF NOT EXISTS referral_count INTEGER DEFAULT 0",
                    "ALTER TABLE users ADD COLUMN IF NOT EXISTS accepted_terms BOOLEAN NOT NULL DEFAULT FALSE",
                    "ALTER TABLE users ADD COLUMN IF NOT EXISTS timezone VARCHAR(64)",
                    "ALTER TABLE users ADD COLUMN IF NOT EXISTS dca_profile VARCHAR(32)",
                    # subscriptions
                    "ALTER TABLE subscriptions ADD COLUMN IF NOT EXISTS bonus_days INTEGER NOT NULL DEFAULT 0",
                    # signals
                    "ALTER TABLE signals ADD COLUMN IF NOT EXISTS ml_probability FLOAT",
                    "ALTER TABLE signals ADD COLUMN IF NOT EXISTS expires_at TIMESTAMP",
                    "ALTER TABLE signals ADD COLUMN IF NOT EXISTS expired BOOLEAN NOT NULL DEFAULT FALSE",
                    "ALTER TABLE signals ADD COLUMN IF NOT EXISTS is_near_order_block BOOLEAN NOT NULL DEFAULT FALSE",
                    # referrals
                    "ALTER TABLE referrals ADD COLUMN IF NOT EXISTS is_successful BOOLEAN NOT NULL DEFAULT FALSE",
                    "ALTER TABLE referrals ADD COLUMN IF NOT EXISTS reward_applied BOOLEAN NOT NULL DEFAULT FALSE",
                    "ALTER TABLE referrals ADD COLUMN IF NOT EXISTS successful_at TIMESTAMP",
                    "ALTER TABLE referrals ADD COLUMN IF NOT EXISTS referrer_notified_at TIMESTAMP",
                    # outcomes (0023 migration belt-and-suspenders)
                    "ALTER TABLE outcomes ADD COLUMN IF NOT EXISTS canonical_outcome VARCHAR(16)",
                    "ALTER TABLE outcomes ADD COLUMN IF NOT EXISTS vip_fill_outcome VARCHAR(16)",
                    "ALTER TABLE outcomes ADD COLUMN IF NOT EXISTS sentiment_outcome VARCHAR(16)",
                    # signal_deliveries (0023 migration belt-and-suspenders)
                    "ALTER TABLE signal_deliveries ADD COLUMN IF NOT EXISTS sent_ok BOOLEAN NOT NULL DEFAULT FALSE",
                    "ALTER TABLE signal_deliveries ADD COLUMN IF NOT EXISTS attempt_count INTEGER NOT NULL DEFAULT 1",
                    "ALTER TABLE signal_deliveries ADD COLUMN IF NOT EXISTS last_attempt_at TIMESTAMP",
                    "ALTER TABLE signal_deliveries ADD COLUMN IF NOT EXISTS last_error TEXT",
                ]
                for stmt in _column_patches:
                    try:
                        cur.execute(stmt)
                    except Exception:
                        pass  # column already exists or table not yet created
                conn.commit()
        except Exception:
            pass

        # 4) Ensure critical audit tables exist (failsafe if migrations didn't run)
        try:
            with conn.cursor() as cur:
                cur.execute(
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
                )
                cur.execute("CREATE INDEX IF NOT EXISTS ix_decision_log_signal_id ON decision_log(signal_id)")
                cur.execute("CREATE INDEX IF NOT EXISTS ix_decision_log_asset ON decision_log(asset)")
                cur.execute("CREATE INDEX IF NOT EXISTS ix_decision_log_timeframe ON decision_log(timeframe)")
                cur.execute("CREATE INDEX IF NOT EXISTS ix_decision_log_decision ON decision_log(decision)")
                cur.execute("CREATE INDEX IF NOT EXISTS ix_decision_log_created_at ON decision_log(created_at)")

                cur.execute(
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
                )
                cur.execute("CREATE INDEX IF NOT EXISTS ix_ml_rejected_signals_asset ON ml_rejected_signals(asset)")
                cur.execute("CREATE INDEX IF NOT EXISTS ix_ml_rejected_signals_timeframe ON ml_rejected_signals(timeframe)")
                cur.execute("CREATE INDEX IF NOT EXISTS ix_ml_rejected_signals_actual_outcome ON ml_rejected_signals(actual_outcome)")

                # managed_assets — failsafe for asset-universe pinning (migration 0015/0016)
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS managed_assets (
                        id              SERIAL PRIMARY KEY,
                        symbol          VARCHAR(32)  NOT NULL,
                        asset_type      VARCHAR(16)  NOT NULL DEFAULT 'crypto',
                        is_active       BOOLEAN      NOT NULL DEFAULT TRUE,
                        added_by        BIGINT,
                        note            VARCHAR(256),
                        last_analyzed_at TIMESTAMP,
                        created_at      TIMESTAMP    NOT NULL DEFAULT NOW(),
                        updated_at      TIMESTAMP    NOT NULL DEFAULT NOW()
                    )
                    """
                )
                cur.execute(
                    "CREATE UNIQUE INDEX IF NOT EXISTS ix_managed_assets_symbol ON managed_assets (symbol)"
                )
                cur.execute(
                    "CREATE INDEX IF NOT EXISTS ix_managed_assets_is_active ON managed_assets (is_active)"
                )
                cur.execute(
                    "CREATE INDEX IF NOT EXISTS ix_managed_assets_last_analyzed "
                    "ON managed_assets (last_analyzed_at ASC NULLS FIRST)"
                )
                # Ensure last_analyzed_at column exists if table was created before 0016
                cur.execute(
                    """
                    ALTER TABLE managed_assets
                    ADD COLUMN IF NOT EXISTS last_analyzed_at TIMESTAMP
                    """
                )
                conn.commit()
        except Exception:
            pass

    finally:
        if conn is not None:
            try:
                if have_lock:
                    with conn.cursor() as cur:
                        cur.execute("SELECT pg_advisory_unlock(%s)", (_advisory_lock_id(),))
            except Exception:
                pass
            try:
                conn.close()
            except Exception:
                pass


def _fresh_start_if_needed(conn) -> None:
    """Wipe application data once, then set a DB flag so it won't repeat."""

    with conn.cursor() as cur:
        # Check flag
        try:
            cur.execute(
                "SELECT 1 FROM runtime_state WHERE key=%s",
                ("signalrankai:fresh_start_done",),
            )
            if cur.fetchone():
                return
        except Exception:
            # runtime_state table missing would imply migrations failed
            return

        # Wipe tables. CASCADE handles FK ordering.
        tables = [
            "signal_deliveries",
            "free_signal_queue",
            "bot_events",
            "referral_rewards",
            "referrals",
            "referral_codes",
            "alert_prefs",
            "outcomes",
            "signals",
            "subscriptions",
            "users",
            "payment_events",
            "strategy_stats",
            "admin_events",
            "runtime_state",
        ]

        cur.execute("TRUNCATE " + ",".join(tables) + " RESTART IDENTITY CASCADE")

        # Re-create the fresh-start flag in runtime_state
        now = datetime.utcnow().isoformat() + "Z"
        cur.execute(
            "INSERT INTO runtime_state(key, value, expires_at, updated_at) VALUES (%s, %s::jsonb, NULL, NOW())",
            ("signalrankai:fresh_start_done", '{"done": true, "at": "%s"}' % now),
        )
