from __future__ import annotations

import os
import time
from datetime import datetime
from typing import Optional


def _env_bool(name: str, default: bool = False) -> bool:
    val = os.getenv(name)
    if val is None:
        return default
    return val.strip().lower() in {"1", "true", "yes", "y", "on"}


def _sync_database_url() -> Optional[str]:
    url = (os.getenv("DATABASE_URL") or "").strip()
    if not url:
        return None
    if url.startswith("postgresql+asyncpg://"):
        return url.replace("postgresql+asyncpg://", "postgresql://", 1)
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql://", 1)
    return url


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
        return

    # Default: auto-migrate when DATABASE_URL exists.
    if not _env_bool("AUTO_MIGRATE", True):
        return

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

        # 1) Migrate schema
        try:
            from alembic import command
            from alembic.config import Config

            cfg = Config("alembic.ini")
            cfg.set_main_option("sqlalchemy.url", db_url)
            command.upgrade(cfg, "head")
        except Exception:
            # If migrations fail, let the service crash to surface the error.
            raise

        # 2) Optional one-time wipe to "start fresh"
        if _env_bool("FRESH_START", False) and run_mode in {"web", "all"}:
            _fresh_start_if_needed(conn)
        
        # 3) Ensure ml_probability column exists (post-migration fix for 0011)
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT EXISTS (
                        SELECT 1 FROM information_schema.columns 
                        WHERE table_name='signals' AND column_name='ml_probability'
                    )
                """)
                if not cur.fetchone()[0]:
                    # Column doesn't exist, add it
                    cur.execute("ALTER TABLE signals ADD COLUMN ml_probability FLOAT")
                    conn.commit()
        except Exception as e:
            # Column may already exist or table may not exist yet; not critical
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
