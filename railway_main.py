"""Railway Free Tier monolith entrypoint.

Runs FastAPI + APScheduler + python-telegram-bot polling in a single asyncio event loop using FastAPI lifespan.

Start with:
  uvicorn railway_main:app --host 0.0.0.0 --port ${PORT:-8080} --workers 1

This keeps existing main.py intact.
"""

from __future__ import annotations

# CRITICAL: Pre-validate SQLAlchemy PostgreSQL dialect BEFORE any other imports
# that might trigger db.models or web.app (Railway fix for KeyError: 'sqlalchemy')
# This MUST be the first import to prevent KeyError: 'sqlalchemy' errors
try:
    from sqlalchemy.dialects.postgresql import UUID
    _SQLALCHEMY_POSTGRES_DIALECT_LOADED = True
except ImportError as _e:
    raise ImportError(f"SQLAlchemy PostgreSQL dialect required. Install: pip install 'sqlalchemy[postgresql]' (got: {_e})")

# Load local environment overrides if present.
try:
    from dotenv import load_dotenv
    load_dotenv(".env", override=False)
    load_dotenv(".env.local", override=True)
except Exception:
    pass

import os


from runtime_safety import apply_runtime_safety_environment

# Compatibility inventory retained for v1.2.1 source-level deployment checks.
_RUNTIME_SAFETY_RELEVANT_FLAGS = (
    "REAL_EXECUTION_ENABLED",
    "AUTO_EXECUTION_ENABLED",
    "AUTO_TRADE_ENABLED",
    "COPY_TRADE_ENABLED",
    "REAL_PAYOUTS_ENABLED",
    "PAYMENTS_PUBLIC_ENABLED",
    "FREE_SIGNAL_DISTRIBUTION_ENABLED",
    "FREE_RANDOM_DISTRIBUTION_ENABLED",
)


def _enforce_nonproduction_safety_environment():
    """Backward-compatible wrapper around the v1.2.3 runtime policy."""
    return apply_runtime_safety_environment()


_RUNTIME_SAFETY = _enforce_nonproduction_safety_environment()
_NONPRODUCTION_SAFETY_OVERRIDES = _RUNTIME_SAFETY.forced_off


import asyncio
import hmac
import json
import re
import sys
import logging
import threading
from collections import deque
from contextlib import asynccontextmanager
from pathlib import Path
import time
from typing import Iterable

from fastapi import FastAPI, Request, Response, HTTPException, Header
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from core.telegram_webhook_config import telegram_webhook_registration_kwargs
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from prometheus_client import Counter, Gauge, Histogram

from core.redis_state import state
from core.redis_streams import (
    StreamMessage,
    stream_consumer_name,
    telegram_update_stream,
)


logger = logging.getLogger(__name__)
_PROCESS_STARTED_MONO = time.monotonic()
_LAST_READINESS_FAILURE_SIGNATURE = ""
_LAST_READINESS_FAILURE_LOG_MONO = 0.0


def _resolve_redis_url() -> str:
    for key in ("REDIS_URL", "REDIS_PRIVATE_URL", "REDIS_PUBLIC_URL", "REDIS_INTERNAL_URL", "REDIS_TLS_URL"):
        val = (os.getenv(key) or "").strip()
        if val:
            if key != "REDIS_URL" and not (os.getenv("REDIS_URL") or "").strip():
                os.environ["REDIS_URL"] = val
            return val
    return ""


# Ensure INFO-level logs are visible in Railway regardless of uvicorn's logging config.
try:
    from utils.logging_config import setup_logging as _setup_logging
    _setup_logging()
except Exception:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s [%(name)s] %(message)s")


_startup_redis_url = _resolve_redis_url()
if _startup_redis_url:
    logger.info("[startup] Redis URL detected; durable webhook queue is available")
else:
    logger.warning("[startup] Redis URL not configured; webhook dispatcher will use the bounded in-process queue")

logger.info(
    "[startup_safety] requested=%s acknowledgement_valid=%s full_system_test_enabled=%s environment=%s",
    int(str(os.getenv("FULL_SYSTEM_STAGING_TEST_MODE") or "").strip().lower() in {"1", "true", "yes", "on", "enabled"}),
    int(bool(_RUNTIME_SAFETY.acknowledgement_valid)),
    int(bool(_RUNTIME_SAFETY.full_system_test_enabled)),
    _RUNTIME_SAFETY.environment,
)

if _RUNTIME_SAFETY.full_system_test_enabled:
    logger.warning(
        "[startup_safety] FULL SYSTEM STAGING TEST MODE active environment=%s "
        "forced_on=%s sandbox_boundaries=%s audience=%s",
        _RUNTIME_SAFETY.environment,
        ",".join(_RUNTIME_SAFETY.forced_on) or "already_enabled",
        ",".join(_RUNTIME_SAFETY.hard_boundaries) or "already_enforced",
        _RUNTIME_SAFETY.audience_allowlist or "EMPTY",
    )
elif _NONPRODUCTION_SAFETY_OVERRIDES:
    logger.warning(
        "[startup_safety] non-production environment forced live-risk flags off: %s",
        ",".join(_NONPRODUCTION_SAFETY_OVERRIDES),
    )
elif str(os.getenv("FULL_SYSTEM_STAGING_TEST_MODE") or "").strip().lower() in {"1", "true", "yes", "on"}:
    if not _RUNTIME_SAFETY.acknowledgement_valid:
        logger.error(
            "[startup_safety] FULL_SYSTEM_STAGING_TEST_MODE requested but acknowledgement is invalid; "
            "live-risk flags remain fail-closed"
        )
    elif _RUNTIME_SAFETY.environment in {"production", "prod"}:
        logger.error(
            "[startup_safety] FULL_SYSTEM_STAGING_TEST_MODE is not permitted in production; "
            "live-risk flags remain fail-closed"
        )
    else:
        logger.error(
            "[startup_safety] FULL_SYSTEM_STAGING_TEST_MODE could not be activated; "
            "live-risk flags remain fail-closed"
        )

# Module-level reference to the fully-configured PTB Application in webhook mode.
# Set by _start_telegram_bot(); used by the POST /telegram/webhook route.
_bot_application: object = None
_bot_ready: bool = False
_pending_webhook_updates = deque(maxlen=500)
_inflight_update_tasks: set[asyncio.Task] = set()
_webhook_dispatch_queue: asyncio.Queue | None = None
_webhook_dispatch_workers: list[asyncio.Task] = []
_webhook_enqueue_started_at: dict[str, float] = {}
_webhook_dispatch_latency_window_s = deque(maxlen=2000)
_scheduler_instance: AsyncIOScheduler | None = None
_lifespan_heartbeat_task: asyncio.Task | None = None
_monitor_tasks: list[asyncio.Task] = []
_use_redis_webhook_queue: bool = False
_last_redis_backend_log_at: float = 0.0
_db_ready_cache: bool | None = None
_db_ready_lock = threading.Lock()
_webhook_stream = telegram_update_stream()


def _append_pending_webhook_update(payload: dict) -> bool:
    """Append without allowing ``deque(maxlen=...)`` to evict valid work."""
    max_items = int(_pending_webhook_updates.maxlen or 0)
    if max_items and len(_pending_webhook_updates) >= max_items:
        webhook_queue_full_total.inc()
        return False
    _pending_webhook_updates.append(payload)
    return True

webhook_queue_full_total = Counter(
    "signalrankai_webhook_queue_full_total",
    "Total dropped webhook updates due to full dispatch queue",
)
webhook_slo_alerts_total = Counter(
    "signalrankai_webhook_slo_alerts_total",
    "Total webhook/outcome SLO alerts",
    labelnames=("kind",),
)
webhook_dispatch_latency_seconds = Histogram(
    "signalrankai_webhook_dispatch_latency_seconds",
    "Latency from webhook enqueue to worker dispatch completion",
    buckets=(0.05, 0.1, 0.25, 0.5, 1, 2, 5, 10, 30, 60),
)
webhook_queue_depth_gauge = Gauge(
    "signalrankai_webhook_queue_depth",
    "Current in-process webhook dispatch queue depth",
)
webhook_queue_utilization_gauge = Gauge(
    "signalrankai_webhook_queue_utilization_ratio",
    "Current in-process webhook dispatch queue utilization ratio",
)
outcome_resolution_latency_seconds = Histogram(
    "signalrankai_outcome_resolution_latency_seconds",
    "Observed signal outcome resolution latency in seconds",
    buckets=(60, 300, 900, 1800, 3600, 14400, 43200, 86400, 172800, 604800),
)


def _percentile(values: Iterable[float], percentile: float) -> float | None:
    if not values:
        return None
    vals = sorted(float(v) for v in values)
    p = max(0.0, min(100.0, float(percentile)))
    if len(vals) == 1:
        return vals[0]
    rank = (p / 100.0) * (len(vals) - 1)
    lo = int(rank)
    hi = min(lo + 1, len(vals) - 1)
    frac = rank - lo
    return vals[lo] + ((vals[hi] - vals[lo]) * frac)


def _emit_slo_alert(kind: str, message: str) -> None:
    webhook_slo_alerts_total.labels(kind=str(kind or "unknown")).inc()
    logger.warning("[slo] %s", message)


def _record_dispatch_latency(update_id: str, started_at: float | None) -> None:
    if started_at is None:
        return
    elapsed = max(0.0, time.monotonic() - started_at)
    _webhook_dispatch_latency_window_s.append(elapsed)
    webhook_dispatch_latency_seconds.observe(elapsed)


def _extract_chat_id(payload: dict | None) -> int:
    try:
        return int((((payload or {}).get("message") or {}).get("chat") or {}).get("id") or 0)
    except Exception:
        return 0



def _redis_queue_requested() -> bool:
    """Use Redis only when configured and not explicitly disabled.

    Earlier builds returned ``True`` unconditionally, causing no-Redis/local
    deployments to claim a durable backend and repeatedly attempt unavailable
    Redis operations.
    """
    configured = bool(
        str(os.getenv("DELIVERY_REDIS_URL") or "").strip()
        or _resolve_redis_url()
    )
    requested = str(os.getenv("WEBHOOK_REDIS_QUEUE_ENABLED", "1")).strip().lower() in {
        "1", "true", "yes", "on"
    }
    return bool(configured and requested)


def _log_task_failure(task: asyncio.Task, task_name: str) -> None:
    try:
        if task.cancelled():
            logger.info("[task] %s cancelled", task_name)
            return
        exc = task.exception()
        if exc is not None:
            logger.error(
                "[task] %s crashed: %s",
                task_name,
                exc,
                exc_info=(type(exc), exc, exc.__traceback__),
            )
    except Exception as inspect_exc:
        logger.warning("[task] failed to inspect %s completion state: %s", task_name, inspect_exc)


async def _sample_outcome_latency_p95_seconds(hours: int = 24, limit: int = 500) -> float | None:
    try:
        from db.session import get_session, is_db_configured
        from sqlalchemy import text
        if not is_db_configured():
            return None
        async with get_session() as session:
            result = await session.execute(
                text(
                    """
                    SELECT EXTRACT(EPOCH FROM (o.closed_at - s.created_at)) AS latency_seconds
                    FROM outcomes o
                    JOIN signals s ON s.signal_id = o.signal_id
                    WHERE o.closed_at IS NOT NULL
                      AND s.created_at IS NOT NULL
                      AND o.closed_at >= NOW() - (:hours || ' hours')::interval
                    ORDER BY o.closed_at DESC
                    LIMIT :limit
                    """
                ),
                {"hours": int(hours), "limit": int(limit)},
            )
            samples: list[float] = []
            for row in result.fetchall() or []:
                try:
                    val = float(getattr(row, "latency_seconds", None) or 0.0)
                    if val >= 0:
                        samples.append(val)
                        outcome_resolution_latency_seconds.observe(val)
                except Exception:
                    continue
            return _percentile(samples, 95.0)
    except Exception as exc:
        logger.debug("[slo] outcome latency sampling skipped: %s", exc)
        return None


async def _safe_get_webhook_info() -> dict | None:
    """Best-effort Telegram webhook info for diagnostics."""
    if (not _bot_ready) or (_bot_application is None):
        return None
    try:
        wh = await _bot_application.bot.get_webhook_info()
        return {
            "url": getattr(wh, "url", ""),
            "pending_update_count": int(getattr(wh, "pending_update_count", 0) or 0),
            "last_error_date": str(getattr(wh, "last_error_date", None)),
            "last_error_message": str(getattr(wh, "last_error_message", None)),
            "max_connections": int(getattr(wh, "max_connections", 0) or 0),
            "ip_address": str(getattr(wh, "ip_address", "") or ""),
        }
    except Exception as exc:
        logger.warning("[webhook] get_webhook_info failed: %s", exc)
        return {"error": str(exc)}


def _app_has_registered_handlers(app_obj: object) -> bool:
    """Return True only when the complete Telegram handler contract is present."""
    if app_obj is None:
        return False
    try:
        handlers_map = getattr(app_obj, "handlers", None)
        if not isinstance(handlers_map, dict):
            return False
        total_handlers = 0
        for _group, handler_list in handlers_map.items():
            try:
                total_handlers += len(handler_list or [])
            except Exception:
                continue
        minimum = max(1, int(os.getenv("BOT_WEBHOOK_READY_MIN_HANDLERS", "60") or 60))
        return total_handlers >= minimum
    except Exception:
        return False


async def _drain_pending_webhook_updates(max_items: int = 200) -> int:
    """Drain queued webhook updates once bot is ready."""
    global _pending_webhook_updates
    if (not _bot_ready) or (_bot_application is None):
        return 0

    drained = 0
    while _pending_webhook_updates and drained < max_items:
        payload = _pending_webhook_updates.popleft()
        try:
            from telegram import Update
            update = Update.de_json(payload, _bot_application.bot)
            await _bot_application.process_update(update)
            drained += 1
        except Exception as exc:
            logger.warning("[webhook] queued update replay failed: %s", exc)
    if drained > 0:
        logger.info("[webhook] replayed queued updates=%d", drained)
    return drained


def _get_webhook_url() -> str:
    """Derive the public HTTPS URL for the current deployment.

    Railway's generated domain is authoritative inside Railway. Explicit
    overrides are fallbacks for non-Railway hosting and local tunnels. This
    ordering prevents a staging service copied from production from registering
    or probing the production domain through a stale APP_BASE_URL.
    """
    domain = (
        os.getenv("RAILWAY_PUBLIC_DOMAIN")
        or os.getenv("WEBHOOK_DOMAIN")
        or os.getenv("WEBHOOK_URL")
        or os.getenv("APP_BASE_URL")
        or ""
    ).strip()
    if not domain:
        return ""
    if not domain.startswith(("http://", "https://")):
        domain = f"https://{domain}"
    return domain.rstrip("/")


def _production_webhook_contract_errors() -> list[str]:
    """Return production blockers that make webhook acceptance unsafe.

    A Railway deployment that cannot durably accept Telegram updates must not
    overwrite the bot's webhook while Railway is still routing the public domain
    to an older deployment. Doing so causes pending updates to hit the old image
    and appear as repeated 404 responses.
    """
    # Durable webhook dependencies are required on every Railway environment,
    # including staging. This is intentionally broader than the production-only
    # public cutover gate used by /readyz.
    if not (_is_running_on_railway() or _production_readiness_required()):
        return []

    errors: list[str] = []
    database_url = str(os.getenv("DATABASE_URL") or "").strip()
    state_url = str(
        os.getenv("STATE_REDIS_URL")
        or os.getenv("SIGNALRANK_STATE_REDIS_URL")
        or os.getenv("REDIS_URL")
        or ""
    ).strip()
    delivery_url = str(os.getenv("DELIVERY_REDIS_URL") or "").strip()
    secret = str(os.getenv("TELEGRAM_WEBHOOK_SECRET") or "").strip()

    if not database_url:
        errors.append("DATABASE_URL")
    if not state_url:
        errors.append("STATE_REDIS_URL|REDIS_URL")
    if not delivery_url:
        errors.append("DELIVERY_REDIS_URL")
    if state_url and delivery_url and state_url == delivery_url:
        errors.append("DISTINCT_REDIS_SERVICES")
    if not secret:
        errors.append("TELEGRAM_WEBHOOK_SECRET")
    return errors


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return bool(default)
    return raw.strip().lower() in {"1", "true", "yes", "y", "on"}


def _is_running_on_railway() -> bool:
    markers = (
        "RAILWAY_SERVICE_NAME",
        "RAILWAY_ENVIRONMENT",
        "RAILWAY_ENVIRONMENT_NAME",
        "RAILWAY_PROJECT_ID",
        "RAILWAY_SERVICE_ID",
        "RAILWAY_DEPLOYMENT_ID",
        "RAILWAY_REPLICA_ID",
        "RAILWAY_PUBLIC_DOMAIN",
        "RAILWAY_PRIVATE_DOMAIN",
    )
    return any(bool((os.getenv(name) or "").strip()) for name in markers)


def _is_db_ready() -> bool:
    global _db_ready_cache
    if _db_ready_cache is not None:
        return _db_ready_cache
    with _db_ready_lock:
        if _db_ready_cache is not None:
            return _db_ready_cache
        try:
            from db.session import is_db_configured

            _db_ready_cache = bool(is_db_configured())
        except Exception as exc:
            _db_ready_cache = False
            logger.warning("[db] readiness check failed: %s", exc)
    return _db_ready_cache


def _validate_production_runtime_contract() -> None:
    """Fail fast when a production Railway service carries test-only controls."""
    environment = str(
        os.getenv("RAILWAY_ENVIRONMENT_NAME")
        or os.getenv("RAILWAY_ENVIRONMENT")
        or os.getenv("APP_ENV")
        or os.getenv("ENVIRONMENT")
        or ""
    ).strip().lower()
    public_testing = str(os.getenv("PUBLIC_TESTING_MODE") or "0").strip().lower() in {
        "1", "true", "yes", "on", "y"
    }
    allow_override = str(
        os.getenv("ALLOW_PUBLIC_TESTING_IN_PRODUCTION") or "0"
    ).strip().lower() in {"1", "true", "yes", "on", "y"}
    if environment in {"production", "prod"} and public_testing and not allow_override:
        raise RuntimeError(
            "PUBLIC_TESTING_MODE=1 is forbidden in production; set it to 0 or explicitly "
            "set ALLOW_PUBLIC_TESTING_IN_PRODUCTION=1 for an isolated non-customer test"
        )


def _log_railway_env_readiness() -> None:
    """Log deployment-critical env readiness for Railway."""
    running_on_railway = _is_running_on_railway()
    if not running_on_railway:
        return

    has_gemini = bool((os.getenv("GEMINI_API_KEY") or "").strip())
    has_mt5_token = bool((os.getenv("META_API_TOKEN") or "").strip())
    has_encryption = bool((os.getenv("ENCRYPTION_KEY") or "").strip())
    has_owner = bool((os.getenv("OWNER_IDS") or "").strip() or (os.getenv("OWNER_TELEGRAM_ID") or "").strip() or (os.getenv("TELEGRAM_OWNER_ID") or "").strip())
    has_telegram_token = bool((os.getenv("TELEGRAM_BOT_TOKEN") or "").strip())
    has_domain = bool((os.getenv("RAILWAY_PUBLIC_DOMAIN") or "").strip() or (os.getenv("WEBHOOK_DOMAIN") or "").strip() or (os.getenv("WEBHOOK_URL") or "").strip())

    logger.info(
        "[railway] env readiness: telegram_token=%s webhook_domain=%s owner=%s gemini=%s mt5_token=%s encryption=%s",
        has_telegram_token,
        has_domain,
        has_owner,
        has_gemini,
        has_mt5_token,
        has_encryption,
    )

    missing = []
    if not has_telegram_token:
        missing.append("TELEGRAM_BOT_TOKEN")
    if not has_domain:
        missing.append("RAILWAY_PUBLIC_DOMAIN|WEBHOOK_DOMAIN")
    if not has_owner:
        missing.append("OWNER_IDS|OWNER_TELEGRAM_ID")
    if not has_gemini:
        missing.append("GEMINI_API_KEY")
    if not has_mt5_token:
        missing.append("META_API_TOKEN")
    if not has_encryption:
        missing.append("ENCRYPTION_KEY")
    if missing:
        logger.warning("[railway] missing env vars: %s", ", ".join(missing))


async def _run_startup_ops() -> None:
    """Run DB migrations/startup ops first.

    Uses existing db.auto_ops.run_startup_ops which handles:
    - DB reachability retry
    - advisory lock
    - alembic upgrade head
    - extra safety table/column ensures
    """
    from db.auto_ops import run_startup_ops

    logger.info("[startup] DB startup ops begin")
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, lambda: run_startup_ops("all"))
    logger.info("[startup] DB startup ops end")


def _ml_archive_backfill_enabled() -> bool:
    """Run ML archive maintenance only on the analytics role or by explicit opt-in."""
    explicit = os.getenv("ML_ARCHIVE_BACKFILL_ENABLED")
    if explicit is not None:
        return _env_bool("ML_ARCHIVE_BACKFILL_ENABLED", False)
    run_mode = (os.getenv("RUN_MODE") or os.getenv("SERVICE_ROLE") or "all").strip().lower()
    return run_mode in {"analytics", "ml", "learning"}


async def _archive_ml_history_job() -> None:
    """Backfill ml_past_training_data from finalized outcomes (idempotent)."""
    if not _ml_archive_backfill_enabled():
        return
    try:
        from ml.schema_version import MODEL_FORMAT_VERSION, get_current_schema_version
        from db.priority import DBPriority
        from db.session import DatabaseWorkDeferred, get_session, is_db_configured
        from sqlalchemy import text
        if not is_db_configured():
            return

        async with get_session(
            priority=DBPriority.ANALYTICS,
            label="ml_archive_backfill",
            timeout_seconds=float(os.getenv("ML_ARCHIVE_DB_TIMEOUT_SECONDS", "0") or 0),
        ) as session:
            # Ensure table exists even if migration order had race conditions.
            await session.execute(text(
                """
                CREATE TABLE IF NOT EXISTS ml_past_training_data (
                    id SERIAL PRIMARY KEY,
                    signal_id VARCHAR(36) UNIQUE NOT NULL,
                    asset VARCHAR(32) NOT NULL,
                    timeframe VARCHAR(8) NOT NULL,
                    direction VARCHAR(8) NOT NULL,
                    entry DOUBLE PRECISION NOT NULL,
                    stop_loss DOUBLE PRECISION NOT NULL,
                    take_profit TEXT NOT NULL,
                    rr_estimate DOUBLE PRECISION NULL,
                    score DOUBLE PRECISION NULL,
                    strength DOUBLE PRECISION NULL,
                    regime VARCHAR(32) NULL,
                    strategy_name VARCHAR(64) NULL,
                    ml_probability DOUBLE PRECISION NULL,
                    outcome_status VARCHAR(16) NOT NULL,
                    outcome_r_multiple DOUBLE PRECISION NULL,
                    outcome_percent DOUBLE PRECISION NULL,
                    outcome_meta JSONB NOT NULL DEFAULT '{}'::jsonb,
                    schema_version INTEGER NOT NULL DEFAULT 1,
                    model_format_version INTEGER NOT NULL DEFAULT 1,
                    signal_created_at TIMESTAMP NULL,
                    outcome_closed_at TIMESTAMP NULL,
                    archived_at TIMESTAMP NOT NULL DEFAULT NOW()
                )
                """
            ))
            await session.execute(
                text(
                    """
                    ALTER TABLE ml_past_training_data
                    ADD COLUMN IF NOT EXISTS schema_version INTEGER NOT NULL DEFAULT 1
                    """
                )
            )
            await session.execute(
                text(
                    """
                    ALTER TABLE ml_past_training_data
                    ADD COLUMN IF NOT EXISTS model_format_version INTEGER NOT NULL DEFAULT 1
                    """
                )
            )

            # Insert only unseen rows by unique signal_id.
            result = await session.execute(
                text(
                    """
                    INSERT INTO ml_past_training_data (
                        signal_id, asset, timeframe, direction,
                        entry, stop_loss, take_profit,
                        rr_estimate, score, strength, regime, strategy_name, ml_probability,
                        outcome_status, outcome_r_multiple, outcome_percent, outcome_meta,
                        schema_version, model_format_version,
                        signal_created_at, outcome_closed_at, archived_at
                    )
                    SELECT
                        s.signal_id, s.asset, s.timeframe, s.direction,
                        s.entry, s.stop_loss, s.take_profit,
                        s.rr_estimate, s.score, s.strength, s.regime, s.strategy_name, s.ml_probability,
                        o.status, o.r_multiple, o.percent, COALESCE(o.meta::jsonb, '{}'::jsonb),
                        :schema_version, :model_format_version,
                        s.created_at, o.closed_at, NOW()
                    FROM signals s
                    JOIN outcomes o ON o.signal_id = s.signal_id
                    WHERE o.status IN ('tp', 'tp1', 'tp2', 'tp3', 'partial_tp', 'sl', 'expired', 'timeout', 'invalidated')
                    ON CONFLICT (signal_id) DO NOTHING
                    """
                ),
                {
                    "schema_version": int(get_current_schema_version()),
                    "model_format_version": int(MODEL_FORMAT_VERSION),
                },
            )
            await session.commit()
            try:
                inserted = int(getattr(result, "rowcount", 0) or 0)
            except Exception:
                inserted = 0
            if inserted > 0:
                logger.info("[ml_archive] backfilled rows=%d", inserted)
    except DatabaseWorkDeferred:
        logger.debug("[ml_archive] deferred while foreground database work is active")
    except Exception as exc:
        logger.warning(f"[ml_archive] backfill failed: {exc}")


async def _maybe_run_start_fresh_keep_users() -> None:
    """Startup reset is disabled to preserve existing data."""
    logger.info("[startup] fresh reset disabled; preserving existing data")
    return


def _build_scheduler() -> AsyncIOScheduler:
    """Create the AsyncIOScheduler for web-layer background jobs.

    Bot-specific recurring jobs (downgrade_expired, delete_old_signals,
    free_distribution, resend_unsent) are already owned by run_bot()'s
    APScheduler BackgroundScheduler — adding them here too would cause
    duplicate execution.  This scheduler only registers jobs that are
    unique to the web layer (VIP waitlist TTL management).
    """
    # Import waitlist jobs from their lightweight canonical module.  This
    # avoids importing the entire web surface merely to register scheduler
    # callbacks and gives us a full traceback if registration ever regresses.
    try:
        from services.waitlist_jobs import (
            check_waitlist_capacity_job as _check_waitlist_capacity_job,
            monitor_expired_invites_job as _monitor_expired_invites_job,
        )
    except Exception as exc:
        logger.exception("[sched] waitlist jobs unavailable: %s", exc)
        _check_waitlist_capacity_job = None
        _monitor_expired_invites_job = None

    scheduler = AsyncIOScheduler(timezone="UTC")

    # VIP waitlist TTL — web layer only, not present in run_bot()
    try:
        if _check_waitlist_capacity_job is None:
            raise LookupError("waitlist capacity job unavailable")
        scheduler.add_job(
            _check_waitlist_capacity_job,
            IntervalTrigger(hours=1, timezone="UTC"),
            id="wl_capacity",
            replace_existing=True,
            max_instances=1,
        )
    except Exception as exc:
        logger.warning("[sched] could not add wl_capacity job: %s", exc, exc_info=True)
    try:
        if _monitor_expired_invites_job is None:
            raise LookupError("waitlist monitor job unavailable")
        scheduler.add_job(
            _monitor_expired_invites_job,
            IntervalTrigger(minutes=15, timezone="UTC"),
            id="wl_monitor",
            replace_existing=True,
            max_instances=1,
        )
    except Exception as exc:
        logger.warning("[sched] could not add wl_monitor job: %s", exc, exc_info=True)

    # ML history belongs to the analytics role. Keep it off the production monolith.
    if _ml_archive_backfill_enabled():
        try:
            scheduler.add_job(
                _archive_ml_history_job,
                IntervalTrigger(
                    minutes=max(5, int(os.getenv("ML_ARCHIVE_INTERVAL_MINUTES", "10") or 10)),
                    timezone="UTC",
                ),
                id="ml_archive_backfill",
                replace_existing=True,
                max_instances=1,
            )
        except Exception as exc:
            logger.warning(f"[sched] could not add ml_archive_backfill job: {exc}")
    else:
        logger.info("[sched] ML archive backfill disabled for this service role")

    return scheduler


async def _start_telegram_bot() -> "tuple[object, bool]":
    """Configure the Telegram bot for webhook mode and register the webhook URL.

     Process:
        1. Set TELEGRAM_USE_WEBHOOK.
        2. Start run_bot() in a background executor thread.
        3. Poll for bot._webhook_application exposure.
        4. Initialize + start the Application on uvicorn's event loop.
        5. Delete any stale webhook, then register the new one with Telegram.

    Returns (application, True) on success, (None, False) on any failure.
    Never raises — failures are logged so the web server keeps running.
    """
    global _bot_application, _bot_ready
    print("[bot] webhook setup starting", flush=True)

    if _bot_ready and _bot_application is not None:
        return _bot_application, True

    contract_errors = _production_webhook_contract_errors()
    if contract_errors:
        joined = ",".join(contract_errors)
        print(f"[bot] webhook setup blocked: production contract missing={joined}", flush=True)
        logger.error(
            "[bot] webhook setup blocked by production contract missing=%s; "
            "existing Telegram webhook was not changed",
            joined,
        )
        return None, False

    if not _is_db_ready():
        print("[bot] webhook setup skipped: DATABASE_URL missing", flush=True)
        logger.warning("[bot] DATABASE_URL not set; skipping webhook setup")
        return None, False

    if _env_bool("DRY_RUN", False):
        print("[bot] webhook setup skipped: DRY_RUN enabled", flush=True)
        logger.warning("[bot] DRY_RUN enabled; skipping webhook setup")
        return None, False

    bot_token = (os.getenv("TELEGRAM_BOT_TOKEN") or "").strip()
    if not bot_token:
        print("[bot] webhook setup skipped: TELEGRAM_BOT_TOKEN missing", flush=True)
        logger.warning("[bot] TELEGRAM_BOT_TOKEN not set; skipping webhook setup")
        return None, False

    try:
        from signalrank_telegram.bot import run_bot
    except Exception as exc:
        import traceback
        tb = traceback.format_exc()
        print(f"[bot] webhook setup import error: {exc}\nTraceback:\n{tb[:1000]}", flush=True)
        logger.error(
            "[bot] Fatal import error — cannot start Telegram bot. "
            "Fix the syntax/import error and redeploy. Details: %s\nTraceback:\n%s",
            exc,
            tb[:1000],
            exc_info=True,
        )
        raise

    # Signal webhook mode before calling run_bot()
    os.environ["TELEGRAM_USE_WEBHOOK"] = "1"

    def _run_bot_safe() -> str | None:
        try:
            run_bot()
            return None
        except Exception as exc:
            # Recovery path: allow later attempts to re-enter run_bot() if this
            # initialization path failed before exposing the webhook app.
            try:
                from signalrank_telegram import bot as _bot_module
                with getattr(_bot_module, "_bot_init_lock"):
                    setattr(_bot_module, "_bot_init_started", False)
                    setattr(_bot_module, "_bot_init_started_at", 0.0)
            except Exception:
                pass
            print(f"[bot] run_bot() setup error: {exc}", flush=True)
            logger.error(f"[bot] run_bot() setup error: {exc}")
            return str(exc)

    # Start run_bot() in executor but do not block on full completion. In webhook
    # mode run_bot can spend significant time in optional setup paths.
    try:
        loop = asyncio.get_running_loop()
        setup_future = loop.run_in_executor(None, _run_bot_safe)
    except Exception as exc:
        print(f"[bot] run_bot setup executor failed: {exc}", flush=True)
        logger.warning(f"[bot] run_bot() executor failed: {exc}; skipping webhook setup")
        return None, False

    # Retrieve the application only after run_bot reports handlers registered.
    app_obj = None
    handlers_ready = False
    discover_timeout_s = int(os.getenv("BOT_APP_DISCOVERY_TIMEOUT_SECONDS", "90") or 90)
    deadline = asyncio.get_running_loop().time() + max(1, discover_timeout_s)
    next_diag_log_at = asyncio.get_running_loop().time() + 10.0
    while asyncio.get_running_loop().time() < deadline:
        try:
            from signalrank_telegram import bot as _bot_module
            app_obj = getattr(_bot_module, "_webhook_application", None)
            handlers_flag = bool(getattr(_bot_module, "_webhook_handlers_ready", False))
            handlers_detected = _app_has_registered_handlers(app_obj)
            handlers_ready = handlers_flag and handlers_detected
        except Exception:
            app_obj = None
            handlers_flag = False
            handlers_detected = False
            handlers_ready = False
        if app_obj is not None and handlers_ready:
            break
        now_monotonic = asyncio.get_running_loop().time()
        if now_monotonic >= next_diag_log_at:
            logger.info(
                "[bot] discovery waiting: app_present=%s handlers_flag=%s handlers_detected=%s timeout_s=%s",
                bool(app_obj is not None),
                bool(handlers_flag),
                bool(handlers_detected),
                discover_timeout_s,
            )
            next_diag_log_at = now_monotonic + 10.0
        await asyncio.sleep(0.25)

    # If still none, check whether run_bot finished with a setup error.
    if (app_obj is None or not handlers_ready) and setup_future.done():
        try:
            setup_error = setup_future.result()
        except Exception as exc:
            setup_error = str(exc)
        if setup_error:
            logger.warning(f"[bot] run_bot() returned setup error: {setup_error}")

    # Never proceed with a partially initialised PTB application. The explicit
    # readiness flag is set only after commands and callback routes exist.

    if app_obj is None or not handlers_ready:
        print("[bot] webhook setup failed: handlers not ready", flush=True)
        logger.warning(
            "[bot] webhook application/handlers not ready after discovery window; skipping webhook setup"
        )
        return None, False

    # Initialize and start the Application on uvicorn's event loop
    try:
        await app_obj.initialize()
        post_init = getattr(app_obj, "post_init", None)
        if callable(post_init):
            await post_init(app_obj)
            logger.info("[bot] post_init completed in webhook lifecycle")
        await app_obj.start()
    except Exception as exc:
        print(f"[bot] application initialize/start failed: {exc}", flush=True)
        logger.warning(f"[bot] application initialize/start failed: {exc}; skipping webhook setup")
        return None, False

    _bot_application = app_obj
    _bot_ready = True

    # Log bot identity to confirm the expected bot token/account is in use.
    try:
        me = await app_obj.bot.get_me()
        logger.info(
            "[bot] identity: id=%s username=@%s can_join_groups=%s can_read_all_group_messages=%s",
            getattr(me, "id", "?"),
            getattr(me, "username", "?"),
            getattr(me, "can_join_groups", None),
            getattr(me, "can_read_all_group_messages", None),
        )
    except Exception as exc:
        logger.warning("[bot] get_me failed during startup: %s", exc)

    # Replay any updates received before bot became ready.
    try:
        await _drain_pending_webhook_updates(max_items=300)
    except Exception as exc:
        logger.warning("[webhook] queued replay after startup failed: %s", exc)

    # Register webhook with Telegram. Avoid unnecessary setWebhook calls because
    # Telegram rate-limits repeated registrations during rapid Railway deploys.
    webhook_url = _get_webhook_url()
    if webhook_url:
        webhook_endpoint = f"{webhook_url}/telegram/webhook"
        webhook_kwargs = telegram_webhook_registration_kwargs()
        webhook_info = None
        try:
            webhook_info = await app_obj.bot.get_webhook_info()
        except Exception as exc:
            logger.debug("[webhook] pre-registration status unavailable: %s", exc)

        force_registration = _env_bool("TELEGRAM_FORCE_WEBHOOK_REREGISTER", False)
        already_registered = bool(
            webhook_info is not None
            and str(getattr(webhook_info, "url", "") or "").rstrip("/")
            == webhook_endpoint.rstrip("/")
        )

        if already_registered and not force_registration:
            logger.info("[bot] webhook already registered: %s", webhook_endpoint)
            print(f"[bot] webhook already registered: {webhook_endpoint}", flush=True)
        else:
            set_ok = False
            max_attempts = max(1, min(3, int(os.getenv("TELEGRAM_WEBHOOK_SET_MAX_ATTEMPTS", "2") or 2)))
            for attempt in range(1, max_attempts + 1):
                try:
                    await app_obj.bot.set_webhook(webhook_endpoint, **webhook_kwargs)
                    set_ok = True
                    print(f"[bot] webhook registered: {webhook_endpoint}", flush=True)
                    logger.info("[bot] webhook registered: %s attempt=%s", webhook_endpoint, attempt)
                    break
                except Exception as exc:
                    retry_after = getattr(exc, "retry_after", None)
                    if retry_after is None:
                        match = re.search(r"Retry in (\d+)", str(exc), flags=re.IGNORECASE)
                        retry_after = int(match.group(1)) if match else None
                    if retry_after is not None and attempt < max_attempts:
                        sleep_seconds = max(1.0, min(15.0, float(retry_after) + 0.25))
                        logger.warning(
                            "[bot] set_webhook rate-limited attempt=%s/%s retry_in=%.2fs",
                            attempt,
                            max_attempts,
                            sleep_seconds,
                        )
                        await asyncio.sleep(sleep_seconds)
                        continue
                    print(f"[bot] set_webhook failed: {exc}", flush=True)
                    logger.warning(
                        "[bot] set_webhook failed attempt=%s/%s err=%s — preserving existing webhook",
                        attempt,
                        max_attempts,
                        exc,
                    )
                    break
            if not set_ok and webhook_info is not None and already_registered:
                logger.info("[bot] existing webhook remains active after registration failure")

        try:
            wh = await app_obj.bot.get_webhook_info()
            logger.info(
                "[webhook] startup status: url_set=%s pending=%s last_error_date=%s last_error_message=%s",
                bool(getattr(wh, "url", "")),
                int(getattr(wh, "pending_update_count", 0) or 0),
                getattr(wh, "last_error_date", None),
                getattr(wh, "last_error_message", None),
            )
            print(
                "[webhook] startup status: "
                f"url_set={bool(getattr(wh, 'url', ''))} "
                f"pending={int(getattr(wh, 'pending_update_count', 0) or 0)} "
                f"last_error_date={getattr(wh, 'last_error_date', None)} "
                f"last_error_message={getattr(wh, 'last_error_message', None)}",
                flush=True,
            )
        except Exception as _wh_exc:
            logger.warning("[webhook] get_webhook_info failed after registration: %s", _wh_exc)
    else:
        print("[bot] webhook NOT registered: RAILWAY_PUBLIC_DOMAIN/WEBHOOK_URL missing", flush=True)
        logger.warning(
            "[bot] RAILWAY_PUBLIC_DOMAIN / WEBHOOK_URL not set — webhook NOT registered with Telegram. "
            "Set RAILWAY_PUBLIC_DOMAIN env var to enable inbound commands."
        )

    print("[bot] webhook mode active", flush=True)
    logger.info("[bot] webhook mode active — all handlers registered, awaiting updates via POST /telegram/webhook")
    return _bot_application, True


async def _stop_telegram_bot(application: object) -> None:
    """Stop the Telegram bot gracefully (webhook or polling mode)."""
    if application is None:
        return
    global _bot_ready
    _bot_ready = False
    # In webhook mode, keep webhook by default to avoid deploy races where an
    # old instance clears the webhook after a new instance has already set it.
    if os.getenv("TELEGRAM_USE_WEBHOOK"):
        _delete_on_shutdown = str(
            os.getenv("TELEGRAM_DELETE_WEBHOOK_ON_SHUTDOWN", "0")
        ).strip().lower() in {"1", "true", "yes", "on"}
        if _delete_on_shutdown:
            try:
                await application.bot.delete_webhook()
                logger.info("[bot] webhook deleted on shutdown (TELEGRAM_DELETE_WEBHOOK_ON_SHUTDOWN=1)")
            except Exception:
                pass
        else:
            logger.info("[bot] preserving webhook on shutdown (default)")
    # Stop the updater if it was started (polling mode only)
    updater = getattr(application, "updater", None)
    try:
        if updater is not None and hasattr(updater, "stop"):
            await updater.stop()
    except Exception:
        pass
    # Stop the application — triggers _post_stop callback
    try:
        if hasattr(application, "stop"):
            await application.stop()
    except Exception:
        pass
    try:
        post_stop = getattr(application, "post_stop", None)
        if callable(post_stop):
            await post_stop(application)
    except Exception as exc:
        logger.debug("[bot] post_stop callback failed: %s", exc)
    try:
        if hasattr(application, "shutdown"):
            await application.shutdown()
    except Exception as exc:
        logger.debug("[bot] application shutdown failed: %s", exc)


async def _notify_admin_bot_ready() -> None:
    if (not _bot_ready) or (_bot_application is None):
        return
    try:
        from config import OWNER_IDS

        if not OWNER_IDS:
            return

        # Railway rolling deploys can briefly run the retiring and replacement
        # containers together. Claim a shared short-lived notification key so
        # owners receive one ready message instead of one from each container.
        try:
            ttl_seconds = max(30, int(os.getenv("BOT_READY_NOTIFICATION_DEDUPE_SECONDS", "180") or 180))
        except (TypeError, ValueError):
            ttl_seconds = 180
        environment = str(
            os.getenv("RAILWAY_ENVIRONMENT_NAME")
            or os.getenv("RAILWAY_ENVIRONMENT")
            or os.getenv("APP_ENV")
            or "unknown"
        ).strip().lower()
        deployment_id = str(os.getenv("RAILWAY_DEPLOYMENT_ID") or "unknown").strip()
        dedupe_key = f"startup:bot_ready:{environment}"

        async def _claim_ready_notification() -> bool:
            try:
                from core.redis_state import state

                def _claim() -> bool:
                    redis_client = state._get_redis_sync()  # shared state Redis; atomic SET NX
                    if redis_client is not None:
                        return bool(redis_client.set(
                            dedupe_key,
                            deployment_id,
                            ex=ttl_seconds,
                            nx=True,
                        ))
                    # Best-effort fallback for local development without Redis.
                    if state.get_sync(dedupe_key):
                        return False
                    state.set_sync(dedupe_key, deployment_id, ex=ttl_seconds)
                    return True

                return bool(await asyncio.to_thread(_claim))
            except Exception as exc:
                logger.warning("[bot_ready_notification] dedupe unavailable error=%s", type(exc).__name__)
                return True

        if not await _claim_ready_notification():
            logger.info("[bot_ready_notification] duplicate suppressed key=%s ttl=%ss", dedupe_key, ttl_seconds)
            return

        msg = "✅ SignalRankAI bot is alive, webhook-ready, and core functions are running."
        for owner_id in OWNER_IDS:
            try:
                await _bot_application.bot.send_message(chat_id=int(owner_id), text=msg)
            except Exception:
                continue
    except Exception:
        return


async def _maybe_startup_delay(env_name: str, default_s: float, component: str) -> None:
    try:
        delay_s = max(0.0, float((os.getenv(env_name) or str(default_s)).strip()))
    except Exception:
        delay_s = float(default_s)
    if delay_s <= 0:
        return
    logger.info("[startup] delaying %s start by %.1fs", component, delay_s)
    await asyncio.sleep(delay_s)


def _start_engine_loop_in_background() -> asyncio.Task:
    """Start the blocking engine.main_loop in a thread executor."""
    from config import config
    from engine.core import main_loop

    dry_run = bool(getattr(config, "DRY_RUN", False))

    async def _runner() -> None:
        loop = asyncio.get_running_loop()
        await _maybe_startup_delay(
            "ENGINE_START_DELAY_SECONDS",
            12.0 if _is_running_on_railway() else 0.0,
            "engine loop",
        )
        print("[engine] background loop starting", flush=True)
        logger.info("[engine] background loop starting")
        try:
            await loop.run_in_executor(None, lambda: main_loop(dry_run))
        except Exception as exc:
            print(f"[engine] background loop crashed: {exc}", flush=True)
            logger.exception(f"[engine] background loop crashed: {exc}")
            raise

    task = asyncio.create_task(_runner())
    task.add_done_callback(lambda t: _log_task_failure(t, "engine-loop"))
    return task


async def _run_deployment_diagnostics_once() -> None:
    """Run the read-only deployment audit after the HTTP service is ready.

    Full pytest/provider certification is opt-in because it can consume the
    entire Railway Hobby allocation. The generated report is secret-safe and
    can be fetched through the protected diagnostics endpoint.
    """
    if not _env_bool(
        "DEPLOYMENT_DIAGNOSTICS_ENABLED",
        _is_running_on_railway(),
    ):
        logger.info("[deployment_diagnostics] disabled")
        return
    delay = max(1.0, float(os.getenv("DEPLOYMENT_DIAGNOSTICS_START_DELAY_SECONDS", "25") or 25))
    await asyncio.sleep(delay)
    report_path = str(
        os.getenv("DEPLOYMENT_DIAGNOSTICS_REPORT_PATH")
        or "/tmp/signalrank_deployment_diagnostics.json"
    )
    command = [
        sys.executable,
        "scripts/deployment_diagnostics.py",
        "--phase",
        "runtime",
        "--output",
        report_path,
        "--continue-on-failure",
    ]
    # Always probe the current Railway deployment first. A duplicated staging
    # environment may still contain production APP_BASE_URL/WEBHOOK_DOMAIN values.
    base_url = str(
        os.getenv("DEPLOYMENT_DIAGNOSTICS_BASE_URL")
        or os.getenv("RAILWAY_PUBLIC_DOMAIN")
        or os.getenv("WEBHOOK_DOMAIN")
        or os.getenv("WEBHOOK_URL")
        or os.getenv("APP_BASE_URL")
        or ""
    ).strip()
    # A rolling public domain may still target the previous image. Runtime
    # diagnostics must validate the container that launched the audit.
    if _is_running_on_railway() and not str(os.getenv("DEPLOYMENT_DIAGNOSTICS_BASE_URL") or "").strip():
        port = str(os.getenv("PORT") or "8080").strip()
        base_url = f"http://127.0.0.1:{port}"
    if base_url:
        if not base_url.startswith(("http://", "https://")):
            base_url = f"https://{base_url}"
        command.extend(["--base-url", base_url])
    if _env_bool("DEPLOYMENT_DIAGNOSTICS_LIVE_PROVIDERS", False):
        command.append("--live-providers")
    if _env_bool("DEPLOYMENT_EXTENDED_SCANS_ENABLED", False):
        command.append("--extended-scans")
    if _env_bool("DEPLOYMENT_FULL_TESTS_ENABLED", False):
        command.append("--run-full-suite")

    logger.info("[deployment_diagnostics] starting command=%s", command)
    try:
        process = await asyncio.create_subprocess_exec(
            *command,
            cwd=str(Path(__file__).resolve().parent),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        timeout = max(60.0, float(os.getenv("DEPLOYMENT_DIAGNOSTICS_TIMEOUT_SECONDS", "1800") or 1800))
        stdout, _ = await asyncio.wait_for(process.communicate(), timeout=timeout)
        text = (stdout or b"").decode("utf-8", errors="replace")
        for line in text.splitlines()[-200:]:
            logger.info("[deployment_diagnostics_output] %s", line)
        logger.info(
            "[deployment_diagnostics] completed exit_code=%s report=%s",
            process.returncode,
            report_path,
        )
    except asyncio.TimeoutError:
        logger.error("[deployment_diagnostics] timed out")
        try:
            process.kill()
        except Exception:
            pass
    except Exception as exc:
        logger.exception("[deployment_diagnostics] failed: %s", exc)


def _start_worker_loop_in_background() -> asyncio.Task:
    """Start the worker.main loop in a thread executor."""
    from worker.worker import main as worker_main

    async def _runner() -> None:
        loop = asyncio.get_running_loop()
        await _maybe_startup_delay(
            "WORKER_START_DELAY_SECONDS",
            20.0 if _is_running_on_railway() else 0.0,
            "worker loop",
        )
        print("[worker] background loop starting", flush=True)
        logger.info("[worker] background loop starting")
        try:
            await loop.run_in_executor(None, worker_main)
        except Exception as exc:
            _etype = type(exc).__name__
            _erepr = repr(exc)
            print(f"[worker] background loop crashed: type={_etype} repr={_erepr}", flush=True)
            logger.exception("[worker] background loop crashed: type=%s repr=%r", _etype, exc)
            raise

    task = asyncio.create_task(_runner())
    task.add_done_callback(lambda t: _log_task_failure(t, "worker-loop"))
    return task


@asynccontextmanager
async def lifespan(_: FastAPI):
    global _lifespan_heartbeat_task
    _validate_production_runtime_contract()
    _log_railway_env_readiness()
    try:
        from db.session import get_session_api_contract

        contract = get_session_api_contract()
        logger.info(
            "[db_session_api] signature_version=%s supports_priority=%s supports_label=%s "
            "supports_timeout=%s legacy_adapter=%s",
            contract["signature_version"],
            str(contract["supports_priority"]).lower(),
            str(contract["supports_label"]).lower(),
            str(contract["supports_timeout"]).lower(),
            str(contract["legacy_adapter"]).lower(),
        )
    except Exception as exc:
        logger.error("[db_session_api] self-check failed: %s", exc)
    _db_ready = _is_db_ready()

    if not _db_ready:
        logger.critical(
            "[startup] DATABASE_URL not configured; DB-dependent subsystems disabled (startup ops/engine/worker/bot)"
        )
    # ── Lifespan heartbeat: confirm event loop is alive ──
    async def _lifespan_heartbeat():
        import time
        while True:
            logger.info(f"[lifespan] heartbeat: event loop alive at {time.strftime('%Y-%m-%d %H:%M:%S')}")
            await asyncio.sleep(300)
    _lifespan_heartbeat_task = asyncio.create_task(_lifespan_heartbeat())
    _lifespan_heartbeat_task.add_done_callback(lambda t: _log_task_failure(t, "lifespan-heartbeat"))
    # ── 1) DB startup/background maintenance ───────────────────────────────────
    # Keep startup healthcheck-friendly: schedule DB-heavy work in background,
    # and only wait for bounded time when explicitly configured.
    startup_ops_task: asyncio.Task | None = None
    startup_maintenance_tasks: list[asyncio.Task] = []

    # On Railway, default to non-blocking startup so healthchecks can connect
    # immediately; operators can opt in to waiting by setting STARTUP_OPS_TIMEOUT_SECONDS.
    _default_ops_timeout = "0" if os.getenv("RAILWAY_SERVICE_NAME") else "35"
    startup_ops_timeout_s = int(os.getenv("STARTUP_OPS_TIMEOUT_SECONDS", _default_ops_timeout) or 0)

    if _db_ready:
        try:
            startup_ops_task = asyncio.create_task(_run_startup_ops())
            startup_ops_task.add_done_callback(lambda t: _log_task_failure(t, "startup-ops"))
            startup_maintenance_tasks.append(startup_ops_task)
            if startup_ops_timeout_s > 0:
                await asyncio.wait_for(asyncio.shield(startup_ops_task), timeout=startup_ops_timeout_s)
            else:
                logger.info("[startup] DB startup ops scheduled in background (non-blocking)")
        except asyncio.TimeoutError:
            logger.warning(
                "[startup] DB startup ops exceeded %ss; continuing boot while ops finish in background",
                startup_ops_timeout_s,
            )
        except Exception as exc:
            logger.error(
                "[startup] DB startup ops failed: %s; continuing anyway — web endpoints will serve degraded responses",
                exc,
            )
    else:
        logger.warning("[startup] DB startup ops skipped: DATABASE_URL not configured")

    async def _run_post_startup_maintenance() -> None:
        """Run maintenance in strict order once startup ops are done.

        Order is important:
          1) optional fresh reset (archives + truncates runtime tables)
          2) ML archive backfill safety pass
        """
        logger.info("[startup] post-maintenance begin")
        startup_wait_for_maintenance_s = int(
            os.getenv("STARTUP_OPS_WAIT_FOR_MAINTENANCE_SECONDS", "90") or 90
        )
        try:
            if startup_ops_task is not None:
                if startup_wait_for_maintenance_s > 0:
                    await asyncio.wait_for(
                        asyncio.shield(startup_ops_task),
                        timeout=startup_wait_for_maintenance_s,
                    )
                else:
                    await asyncio.shield(startup_ops_task)
                logger.info("[startup] post-maintenance: startup-ops wait complete")
        except asyncio.TimeoutError:
            logger.warning(
                "[startup] post-maintenance: startup-ops wait exceeded %ss; proceeding anyway",
                startup_wait_for_maintenance_s,
            )
        except Exception as exc:
            logger.warning(f"[startup] post-startup maintenance proceeding after startup-ops error: {exc}")

        # Fresh reset first so clearing happens before additional archive pass.
        try:
            await _maybe_run_start_fresh_keep_users()
            logger.info("[startup] post-maintenance: fresh reset skipped (disabled)")
        except Exception as exc:
            logger.warning(f"[startup] fresh reset step failed: {exc}")

        # ML archive maintenance is isolated to the analytics role.
        if _ml_archive_backfill_enabled():
            try:
                await _archive_ml_history_job()
                logger.info("[startup] post-maintenance: ml archive backfill step complete")
            except Exception as exc:
                logger.warning(f"[startup] ml archive initial backfill failed: {exc}")
        else:
            logger.info("[startup] post-maintenance: ml archive backfill disabled")

        logger.info("[startup] post-maintenance end")

    # Keep maintenance non-blocking by default on Railway, with optional bounded wait.
    _default_maintenance_timeout = "0" if os.getenv("RAILWAY_SERVICE_NAME") else "15"
    maintenance_timeout_s = int(
        os.getenv("STARTUP_MAINTENANCE_TIMEOUT_SECONDS", _default_maintenance_timeout) or 0
    )
    if _db_ready:
        try:
            maintenance_task = asyncio.create_task(_run_post_startup_maintenance())
            maintenance_task.add_done_callback(lambda t: _log_task_failure(t, "startup-maintenance"))
            startup_maintenance_tasks.append(maintenance_task)
            if maintenance_timeout_s > 0:
                await asyncio.wait_for(asyncio.shield(maintenance_task), timeout=maintenance_timeout_s)
            else:
                logger.info("[startup] post-startup maintenance scheduled in background (non-blocking)")
        except asyncio.TimeoutError:
            logger.warning(
                "[startup] post-startup maintenance exceeded %ss; continuing in background",
                maintenance_timeout_s,
            )
        except Exception as exc:
            logger.warning(f"[startup] could not schedule post-startup maintenance: {exc}")
    else:
        logger.warning("[startup] post-startup maintenance skipped: DATABASE_URL not configured")


    _running_on_railway = _is_running_on_railway()
    # Production and certification workers must never race repository migrations.
    # Pre-deploy is responsible for upgrading the schema; runtime only proves it.
    profile = str(os.getenv("SIGNALRANK_ENV_PROFILE") or "").strip().lower()
    strict_worker_admission = _production_readiness_required() or profile in {
        "staging-certification",
        "production-advisory",
        "production-live-owner-canary",
    }
    worker_admitted = True
    worker_admission: dict[str, object] = {"ok": True, "detail": "not_required"}
    if strict_worker_admission:
        from core.version import runtime_commit_matches_expected

        database_admission = await _database_readiness_check()
        commit_ok, commit_detail = runtime_commit_matches_expected()
        worker_admitted = bool(database_admission.get("ok")) and commit_ok
        worker_admission = {
            "ok": worker_admitted,
            "database": database_admission,
            "release_commit": {"ok": commit_ok, "detail": commit_detail},
        }
        logger.info("[worker_admission] %s", json.dumps(worker_admission, sort_keys=True, default=str))
        if not worker_admitted:
            logger.critical(
                "[worker_admission] engine and worker loops blocked by schema or release identity"
            )

    # ── 2) Engine loop (long-running background task) ─────────────────────────
    # Default ON in monolith so web+bot+engine+worker run in one service.
    # Can still be disabled explicitly with RUN_ENGINE_LOOP=0.
    engine_task = None
    _run_engine = str(
        os.getenv("RUN_ENGINE_LOOP", "1")
    ).strip().lower() in {"1", "true", "yes", "on"}
    if not _run_engine:
        logger.info(
            "[startup] Engine loop skipped (RUN_ENGINE_LOOP=0)%s",
            " [Railway default]" if _running_on_railway else "",
        )
    elif not _db_ready:
        logger.warning("[startup] Engine loop skipped (DATABASE_URL not configured)")
    elif not worker_admitted:
        logger.critical("[startup] Engine loop blocked by database worker admission")
    else:
        try:
            engine_task = _start_engine_loop_in_background()
            print("[startup] Engine loop task created", flush=True)
            logger.info("[startup] Engine loop task created")
        except Exception as exc:
            # Provide better error context for debugging
            import traceback
            tb = traceback.format_exc()
            exc_msg = f"{type(exc).__name__}: {exc}"
            if "is not defined" in str(exc):
                # This is typically a masked ImportError - provide the full traceback
                print(f"[startup] Could not start engine loop: {exc_msg}\nTraceback:\n{tb[:500]}", flush=True)
            else:
                print(f"[startup] Could not start engine loop: {exc_msg}", flush=True)
            logger.warning(f"[startup] Could not start engine loop: {exc_msg}\nTraceback:\n{tb[:500]}")

    # ── 2b) Worker loop (long-running background task) ───────────────────────
    # Default ON in monolith so web+bot+engine+worker run in one service.
    # Can still be disabled explicitly with RUN_WORKER_LOOP=0.
    worker_task = None
    _run_worker = str(
        os.getenv("RUN_WORKER_LOOP", "1")
    ).strip().lower() in {"1", "true", "yes", "on"}
    if not _run_worker:
        logger.info(
            "[startup] Worker loop skipped (RUN_WORKER_LOOP=0)%s",
            " [Railway default]" if _running_on_railway else "",
        )
    elif not _db_ready:
        logger.warning("[startup] Worker loop skipped (DATABASE_URL not configured)")
    elif not worker_admitted:
        logger.critical("[startup] Worker loop blocked by database worker admission")
    else:
        try:
            worker_task = _start_worker_loop_in_background()
            print("[startup] Worker loop task created", flush=True)
            logger.info("[startup] Worker loop task created")
        except Exception as exc:
            print(f"[startup] Could not start worker loop: {exc}", flush=True)
            logger.warning(f"[startup] Could not start worker loop: {exc}")

    # ── Crash detection for background tasks ─────────────────────────────────
    async def _monitor_background_tasks():
        nonlocal engine_task, worker_task
        _reported_done: set[tuple[str, int]] = set()

        def _report_task(name: str, task: asyncio.Task | None, expected_completion: bool = False) -> None:
            if task is None or not task.done():
                return
            key = (name, id(task))
            if key in _reported_done:
                return
            _reported_done.add(key)

            try:
                if task.cancelled():
                    logger.info("[monitor] %s task cancelled", name)
                    return
                exc = task.exception()
                if exc is not None:
                    logger.error(
                        "[monitor] %s task failed: %s",
                        name,
                        exc,
                        exc_info=(type(exc), exc, exc.__traceback__),
                    )
                    return
                if expected_completion:
                    logger.info("[monitor] %s task completed", name)
                else:
                    logger.warning("[monitor] %s task has stopped unexpectedly!", name)
            except Exception as _mt_err:
                logger.warning("[monitor] could not inspect %s task state: %s", name, _mt_err)

        while True:
            await asyncio.sleep(30)
            _report_task("Engine", engine_task, expected_completion=False)
            _report_task("Worker", worker_task, expected_completion=False)
            _report_task("Bot start", bot_start_task, expected_completion=True)

            # Auto-restart critical long-running loops if they stop unexpectedly.
            try:
                if engine_task is not None and engine_task.done() and not engine_task.cancelled() and _run_engine:
                    logger.warning("[monitor] restarting Engine loop after unexpected stop")
                    engine_task = _start_engine_loop_in_background()
            except Exception as exc:
                logger.warning("[monitor] engine restart attempt failed: %s", exc)
            try:
                if worker_task is not None and worker_task.done() and not worker_task.cancelled() and _run_worker:
                    logger.warning("[monitor] restarting Worker loop after unexpected stop")
                    worker_task = _start_worker_loop_in_background()
            except Exception as exc:
                logger.warning("[monitor] worker restart attempt failed: %s", exc)

            # Keep webhook worker pool healthy if any worker task crashes.
            try:
                desired_workers = max(4, _worker_count)
                active_workers: list[asyncio.Task] = []
                for idx, wt in enumerate(list(_webhook_dispatch_workers), start=1):
                    if wt.done():
                        _log_task_failure(wt, f"webhook-worker-{idx}")
                        continue
                    active_workers.append(wt)
                _webhook_dispatch_workers.clear()
                _webhook_dispatch_workers.extend(active_workers)
                while len(_webhook_dispatch_workers) < desired_workers:
                    wid = len(_webhook_dispatch_workers) + 1
                    new_worker = asyncio.create_task(_webhook_worker(wid))
                    new_worker.add_done_callback(lambda t, _wid=wid: _log_task_failure(t, f"webhook-worker-{_wid}"))
                    _webhook_dispatch_workers.append(new_worker)
                    logger.warning("[monitor] restarted webhook worker id=%s", wid)
            except Exception as exc:
                logger.warning("[monitor] webhook worker health check failed: %s", exc)

    async def _monitor_telegram_webhook_health():
        while True:
            await asyncio.sleep(60)
            if (not _bot_ready) or (_bot_application is None):
                continue
            try:
                queue_size = 0
                queue_util = 0.0
                if _use_redis_webhook_queue:
                    try:
                        queue_size = int(await state.webhook_queue_depth())
                    except Exception:
                        queue_size = 0
                    queue_cap = int(os.getenv("REDIS_WEBHOOK_QUEUE_MAX_DEPTH", "2000") or 2000)
                    try:
                        queue_util = float(queue_size) / float(max(1, queue_cap))
                    except Exception:
                        queue_util = 0.0
                elif _webhook_dispatch_queue is not None:
                    queue_size = int(_webhook_dispatch_queue.qsize())
                    try:
                        queue_util = float(queue_size) / float(max(1, _webhook_dispatch_queue.maxsize))
                    except Exception:
                        queue_util = 0.0
                webhook_queue_depth_gauge.set(queue_size)
                webhook_queue_utilization_gauge.set(queue_util)
                if queue_util >= 0.90:
                    _emit_slo_alert(
                        "webhook_queue_utilization",
                        f"webhook queue utilization high: utilization={queue_util:.2f} size={queue_size}",
                    )

                lat_p99 = _percentile(_webhook_dispatch_latency_window_s, 99.0)
                if lat_p99 is not None and lat_p99 > 5.0:
                    _emit_slo_alert(
                        "webhook_dispatch_latency",
                        f"webhook dispatch latency p99 breached: p99_s={lat_p99:.3f}",
                    )

                out_p95 = await _sample_outcome_latency_p95_seconds(hours=24, limit=500)
                if out_p95 is not None and out_p95 > 86400.0:
                    _emit_slo_alert(
                        "outcome_latency",
                        f"outcome latency p95 breached: p95_s={out_p95:.1f}",
                    )

                wh = await _bot_application.bot.get_webhook_info()
                _url_set = bool(getattr(wh, "url", ""))
                _pending = int(getattr(wh, "pending_update_count", 0) or 0)
                _last_err_date = getattr(wh, "last_error_date", None)
                _last_err_msg = getattr(wh, "last_error_message", None)
                logger.info(
                    "[webhook] periodic status: url_set=%s pending=%s last_error_date=%s last_error_message=%s",
                    _url_set,
                    _pending,
                    _last_err_date,
                    _last_err_msg,
                )
                print(
                    "[webhook] periodic status: "
                    f"url_set={_url_set} "
                    f"pending={_pending} "
                    f"last_error_date={_last_err_date} "
                    f"last_error_message={_last_err_msg}",
                    flush=True,
                )
                if not _url_set:
                    try:
                        _base = _get_webhook_url()
                        if _base:
                            _endpoint = f"{_base}/telegram/webhook"
                            _kwargs = telegram_webhook_registration_kwargs()
                            await _bot_application.bot.set_webhook(_endpoint, **_kwargs)
                            logger.warning("[webhook] periodic self-heal: webhook was unset, re-registered=%s", _endpoint)
                            print(f"[webhook] periodic self-heal: re-registered={_endpoint}", flush=True)
                    except Exception as _heal_exc:
                        logger.warning("[webhook] periodic self-heal failed: %s", _heal_exc)
            except Exception as exc:
                logger.warning("[webhook] periodic status check failed: %s", exc)

    async def _monitor_redis_webhook_backend() -> None:
        """Re-check Redis availability and switch queue backend dynamically."""
        global _use_redis_webhook_queue, _last_redis_backend_log_at
        while True:
            await asyncio.sleep(15)
            try:
                redis_enabled = _redis_queue_requested()
                if not redis_enabled:
                    if _use_redis_webhook_queue:
                        _use_redis_webhook_queue = False
                        logger.warning("[webhook] Redis queue disabled by config; using in-process queue")
                    continue

                if _webhook_stream.configured:
                    redis_ok = bool(await _webhook_stream.ping())
                else:
                    # Compatibility path for local/test deployments that have
                    # not yet provisioned the dedicated delivery Redis.
                    redis_ok = bool(await state.has_redis())
                if redis_ok and (not _use_redis_webhook_queue):
                    _use_redis_webhook_queue = _redis_queue_requested()
                    logger.info("[webhook] Redis became available; switched queue_backend=redis")
                elif (not redis_ok) and _use_redis_webhook_queue:
                    _use_redis_webhook_queue = False
                    logger.warning("[webhook] Redis unavailable; switched queue_backend=in_process")
                elif not redis_ok:
                    now = time.monotonic()
                    if now - float(_last_redis_backend_log_at or 0.0) >= 60.0:
                        _last_redis_backend_log_at = now
                        logger.warning("[webhook] Redis unavailable; retaining queue_backend=in_process")
            except Exception as exc:
                logger.debug("[webhook] Redis backend monitor error: %s", exc)

    async def _webhook_worker(worker_id: int) -> None:
        """Background worker: process Telegram updates from queue."""
        stream_consumer = stream_consumer_name(f"telegram-{worker_id}")
        while True:
            payload = None
            payload_source = "redis" if _use_redis_webhook_queue else "in_process"
            consumed_in_process = False
            stream_message: StreamMessage | None = None

            # Important: even in Redis mode, consume local fallback items first.
            # This prevents ingress/worker disconnect when Redis enqueue times out.
            if _webhook_dispatch_queue is not None:
                try:
                    payload = _webhook_dispatch_queue.get_nowait()
                    consumed_in_process = True
                    payload_source = "in_process"
                except asyncio.QueueEmpty:
                    payload = None

            if payload is None and _use_redis_webhook_queue:
                if _webhook_stream.configured:
                    stream_messages = await _webhook_stream.read(
                        consumer=stream_consumer,
                        count=1,
                        block_ms=1_000,
                    )
                    if stream_messages:
                        stream_message = stream_messages[0]
                        payload = stream_message.payload
                    payload_source = "redis_stream"
                else:
                    payload = await state.dequeue_webhook_update(timeout_seconds=1)
                    payload_source = "redis_legacy"
                if not payload:
                    continue

            if payload is None:
                if _webhook_dispatch_queue is None:
                    await asyncio.sleep(0.25)
                    continue
                payload = await _webhook_dispatch_queue.get()
                consumed_in_process = True
                payload_source = "in_process"

            payload_update_id = (payload or {}).get("update_id", "?")
            started_at = _webhook_enqueue_started_at.pop(str(payload_update_id), None)
            try:
                logger.info(
                    "[webhook] worker=%s start update_id=%s backend=%s",
                    worker_id,
                    payload_update_id,
                    payload_source,
                )
                if (not _bot_ready) or (_bot_application is None):
                    if stream_message is not None:
                        # Leave the entry pending; another consumer can claim it
                        # after the lease once the bot application is ready.
                        await asyncio.sleep(0.1)
                    elif not _append_pending_webhook_update(payload):
                        logger.error(
                            "[webhook] pending queue full while bot unavailable update_id=%s",
                            payload_update_id,
                        )
                    continue
                from telegram import Update
                update_type = next((k for k in (payload or {}) if k not in ("update_id",)), "unknown")
                logger.debug("[webhook] worker=%s processing update_id=%s type=%s", worker_id, payload_update_id, update_type)
                update = Update.de_json(payload, _bot_application.bot)
                process_task = asyncio.create_task(_bot_application.process_update(update))
                _inflight_update_tasks.add(process_task)
                process_task.add_done_callback(lambda t: _inflight_update_tasks.discard(t))
                soft_timeout_s = max(5.0, float(os.getenv("WEBHOOK_SOFT_TIMEOUT_SECONDS", "30") or 30.0))
                hard_timeout_s = max(10.0, float(os.getenv("WEBHOOK_HARD_TIMEOUT_SECONDS", "120") or 120.0))
                try:
                    await asyncio.wait_for(asyncio.shield(process_task), timeout=soft_timeout_s)
                except asyncio.TimeoutError:
                    chat_id = _extract_chat_id(payload)
                    if chat_id > 0:
                        try:
                            await _bot_application.bot.send_message(
                                chat_id=chat_id,
                                text="⏳ Still processing your request. I’ll send the complete result shortly.",
                            )
                        except Exception:
                            pass
                    try:
                        await asyncio.wait_for(process_task, timeout=hard_timeout_s)
                    except asyncio.TimeoutError:
                        process_task.cancel()
                        logger.warning("[webhook] update_id=%s processing exceeded hard limit and was cancelled", payload_update_id)
                        raise
                _record_dispatch_latency(str(payload_update_id), started_at)
                if stream_message is not None:
                    acknowledged = await _webhook_stream.ack(stream_message.message_id)
                    if not acknowledged:
                        raise RuntimeError(
                            f"stream acknowledgement failed for {stream_message.message_id}"
                        )
                logger.info("[webhook] worker=%s finished update_id=%s", worker_id, payload_update_id)
            except Exception as exc:
                if stream_message is not None:
                    try:
                        attempts = await _webhook_stream.fail(stream_message, exc)
                        logger.warning(
                            "[webhook] stream processing failed id=%s attempts=%s",
                            stream_message.message_id,
                            attempts,
                        )
                    except Exception:
                        logger.exception(
                            "[webhook] failed to persist stream retry state id=%s",
                            stream_message.message_id,
                        )
                logger.error(
                    "[webhook] worker=%s failed processing update: %s",
                    worker_id,
                    exc,
                    exc_info=(type(exc), exc, exc.__traceback__),
                )
            finally:
                if consumed_in_process and _webhook_dispatch_queue is not None:
                    try:
                        _webhook_dispatch_queue.task_done()
                    except Exception:
                        pass

    _monitor_tasks.append(asyncio.create_task(_monitor_background_tasks()))
    _monitor_tasks[-1].add_done_callback(lambda t: _log_task_failure(t, "monitor-background"))
    _monitor_tasks.append(asyncio.create_task(_monitor_telegram_webhook_health()))
    _monitor_tasks[-1].add_done_callback(lambda t: _log_task_failure(t, "monitor-webhook-health"))
    _monitor_tasks.append(asyncio.create_task(_monitor_redis_webhook_backend()))
    _monitor_tasks[-1].add_done_callback(lambda t: _log_task_failure(t, "monitor-redis-backend"))
    _monitor_tasks.append(asyncio.create_task(_run_deployment_diagnostics_once()))
    _monitor_tasks[-1].add_done_callback(lambda t: _log_task_failure(t, "deployment-diagnostics"))

    # Bounded queue + worker pool sized for a single Railway Hobby process.
    global _webhook_dispatch_queue, _webhook_dispatch_workers, _use_redis_webhook_queue
    _default_queue_size = "1000"
    _default_worker_count = "4"
    _use_redis_webhook_queue = _redis_queue_requested()
    _queue_size = int(os.getenv("WEBHOOK_UPDATE_QUEUE_SIZE", _default_queue_size) or _default_queue_size)
    _worker_count = int(os.getenv("WEBHOOK_UPDATE_WORKERS", _default_worker_count) or _default_worker_count)
    _webhook_dispatch_queue = asyncio.Queue(maxsize=max(100, min(10_000, _queue_size)))
    _webhook_dispatch_workers = [
        asyncio.create_task(_webhook_worker(i + 1))
        for i in range(max(1, min(16, _worker_count)))
    ]
    for idx, _wt in enumerate(_webhook_dispatch_workers, start=1):
        _wt.add_done_callback(lambda t, _idx=idx: _log_task_failure(t, f"webhook-worker-{_idx}"))
    logger.info(
        "[webhook] dispatcher started workers=%s queue_size=%s redis_queue=%s",
        len(_webhook_dispatch_workers),
        _webhook_dispatch_queue.maxsize,
        _use_redis_webhook_queue,
    )

    scheduler = None

    # ── 4) Telegram webhook ───────────────────────────────────────────────────
    # Keep startup fast for Railway healthchecks; initialize bot in background
    # with retries until it is ready.
    application, bot_started = None, False
    bot_start_task: asyncio.Task | None = None
    bot_stop_event = asyncio.Event()

    def _start_scheduler_once() -> AsyncIOScheduler | None:
        nonlocal scheduler
        global _scheduler_instance
        if _scheduler_instance is not None:
            scheduler = _scheduler_instance
            return scheduler
        try:
            _scheduler_instance = _build_scheduler()
            _scheduler_instance.start()
            scheduler = _scheduler_instance
            logger.info("[sched] started")
            return scheduler
        except Exception as exc:
            logger.warning("[startup] Scheduler failed to start: %s", exc)
            return None

    if _db_ready:
        _start_scheduler_once()
    else:
        logger.warning("[startup] Scheduler skipped: DATABASE_URL not configured")

    async def _start_bot_bg() -> None:
        nonlocal application, bot_started
        if not _db_ready:
            logger.warning("[startup] Telegram bot disabled: DATABASE_URL not configured")
            return
        backoff_seconds = 5
        attempt_no = 0
        discover_timeout_s = int(os.getenv("BOT_APP_DISCOVERY_TIMEOUT_SECONDS", "90") or 90)
        attempt_timeout_env = int(os.getenv("BOT_START_ATTEMPT_TIMEOUT_SECONDS", "45") or 45)
        # Ensure a single attempt can complete discovery + init + webhook registration.
        attempt_timeout_s = max(attempt_timeout_env, discover_timeout_s + 20)
        logger.info(
            "[startup] Telegram bot timeout config: attempt_timeout=%ss discovery_timeout=%ss",
            attempt_timeout_s,
            discover_timeout_s,
        )
        while not bot_stop_event.is_set() and not bot_started:
            attempt_no += 1
            _attempt_started = asyncio.get_running_loop().time()
            _attempt_result = "unknown"
            try:
                print("[startup] Telegram webhook setup attempt", flush=True)
                application, bot_started = await asyncio.wait_for(
                    _start_telegram_bot(),
                    timeout=attempt_timeout_s,
                )
                print(f"[startup] Telegram webhook setup completed: started={bot_started}", flush=True)
                _attempt_result = "started" if bot_started else "not_ready"
                if bot_started:
                    _start_scheduler_once()
                    await _notify_admin_bot_ready()
                    _elapsed = asyncio.get_running_loop().time() - _attempt_started
                    logger.info(
                        "[startup] Telegram webhook attempt summary: attempt=%s result=%s elapsed_s=%.2f",
                        attempt_no,
                        _attempt_result,
                        _elapsed,
                    )
                    return
            except asyncio.TimeoutError:
                print("[startup] Telegram webhook setup attempt timed out", flush=True)
                logger.warning(
                    "[startup] Telegram webhook setup attempt timed out after %ss",
                    attempt_timeout_s,
                )
                _attempt_result = "timeout"
            except Exception as exc:
                print(f"[startup] Telegram webhook setup error (background): {exc}", flush=True)
                logger.warning(f"[startup] Telegram webhook setup error (background): {exc}")
                _attempt_result = "error"

            _elapsed = asyncio.get_running_loop().time() - _attempt_started
            logger.info(
                "[startup] Telegram webhook attempt summary: attempt=%s result=%s elapsed_s=%.2f next_backoff_s=%s",
                attempt_no,
                _attempt_result,
                _elapsed,
                backoff_seconds,
            )

            try:
                await asyncio.wait_for(bot_stop_event.wait(), timeout=backoff_seconds)
            except asyncio.TimeoutError:
                pass
            backoff_seconds = min(backoff_seconds * 2, 60)

    if _db_ready:
        try:
            bot_start_task = asyncio.create_task(_start_bot_bg())
            bot_start_task.add_done_callback(lambda t: _log_task_failure(t, "bot-start"))
            print("[startup] Telegram webhook setup scheduled in background", flush=True)
        except Exception as exc:
            print(f"[startup] Could not schedule Telegram webhook setup: {exc}", flush=True)
            logger.warning(f"[startup] Could not schedule Telegram webhook setup: {exc}")
    else:
        logger.warning("[startup] Telegram webhook setup skipped: DATABASE_URL not configured")

    logger.info(
        f"[startup] complete — engine={'ok' if engine_task else 'skipped'} "
        f"worker={'ok' if worker_task else 'skipped'} "
        f"scheduler={'ok' if scheduler else 'skipped'} "
        f"bot={'webhook' if bot_started else 'initializing'}"
    )

    # ── Startup subsystem summary ─────────────────────────────────────────────
    # Emit a single consolidated log line showing which subsystems are active so
    # operators can immediately verify the single-service deployment is healthy.
    _worker_outcome_enabled = str(os.getenv("WORKER_OUTCOME_TRACKER_ENABLED", "1")).strip().lower() in {"1", "true", "yes", "on"}
    _engine_outcome_requested = str(os.getenv("ENGINE_OUTCOME_TRACKER_ENABLED", "0")).strip().lower() in {"1", "true", "yes", "on"}
    # The monolith has one authoritative realtime outcome owner: the worker loop.
    # ENGINE_OUTCOME_TRACKER_ENABLED is retained only as a compatibility input and
    # does not start a second tracker.
    _engine_outcome_state = "DISABLED(worker_owned)"
    if _engine_outcome_requested:
        logger.warning(
            "[startup] ENGINE_OUTCOME_TRACKER_ENABLED requested but ignored; "
            "worker loop is the sole realtime outcome owner"
        )
    _bot_state = "DISABLED" if not _db_ready else ("ENABLED" if bot_started else "INITIALIZING")
    _subsystem_summary = (
        "[startup] subsystem summary | "
        f"signal_engine={'ENABLED' if engine_task else 'DISABLED'} | "
        f"outcome_worker={'ENABLED' if worker_task else 'DISABLED'} | "
        f"worker_outcome_tracker={'ENABLED' if (worker_task and _worker_outcome_enabled) else 'DISABLED'} | "
        f"engine_outcome_tracker={_engine_outcome_state} | "
        f"scheduler={'ENABLED' if scheduler else 'DISABLED'} | "
        f"bot={_bot_state}"
    )
    print(_subsystem_summary, flush=True)
    logger.info(_subsystem_summary)

    try:
        yield
    finally:
        for _t in startup_maintenance_tasks:
            if _t.done():
                try:
                    _ = _t.result()
                except Exception:
                    pass
            else:
                try:
                    _t.cancel()
                except Exception:
                    pass

        # ── Shutdown order: bot → scheduler → worker task → engine task ───────
        try:
            bot_stop_event.set()
        except Exception:
            pass

        if bot_start_task is not None and not bot_start_task.done():
            try:
                bot_start_task.cancel()
            except Exception:
                pass

        if bot_started and application is not None:
            try:
                await _stop_telegram_bot(application)
                logger.info("[bot] stopped")
            except Exception as exc:
                logger.warning(f"[shutdown] bot stop error: {exc}")

        # Shut down the bot's BackgroundScheduler (owned by signalrank_telegram.bot)
        # before Python's atexit handlers shut down its ThreadPoolExecutor.  Without
        # this, APScheduler fires pending jobs after the executor is already gone,
        # producing: RuntimeError: cannot schedule new futures after shutdown.
        try:
            from signalrank_telegram import bot as _bot_mod
            _bot_sched = getattr(_bot_mod, "_bot_scheduler", None)
            if _bot_sched is not None and getattr(_bot_sched, "running", False):
                _bot_sched.shutdown(wait=False)
                logger.info("[sched] bot BackgroundScheduler shutdown")
            else:
                logger.debug("[sched] bot BackgroundScheduler not running — skip shutdown")
        except Exception as exc:
            logger.warning("[shutdown] bot BackgroundScheduler shutdown error: %s", exc)

        if scheduler is not None:
            try:
                scheduler.shutdown(wait=False)
                logger.info("[sched] shutdown")
            except Exception as exc:
                logger.warning(f"[shutdown] scheduler shutdown error: {exc}")

        if worker_task is not None:
            try:
                worker_task.cancel()
            except Exception:
                pass

        if engine_task is not None:
            try:
                engine_task.cancel()
            except Exception:
                pass

        if _webhook_dispatch_workers:
            for _wt in _webhook_dispatch_workers:
                try:
                    _wt.cancel()
                except Exception:
                    pass
        if _monitor_tasks:
            for _mt in list(_monitor_tasks):
                try:
                    _mt.cancel()
                except Exception:
                    pass
            _monitor_tasks.clear()
        if _lifespan_heartbeat_task is not None:
            try:
                _lifespan_heartbeat_task.cancel()
            except Exception:
                pass
            _lifespan_heartbeat_task = None
        if _inflight_update_tasks:
            for _task in list(_inflight_update_tasks):
                try:
                    _task.cancel()
                except Exception:
                    pass
        try:
            await _webhook_stream.close()
        except Exception as exc:
            logger.debug("[shutdown] webhook stream close failed: %s", exc)
        try:
            from core.telemetry import shutdown_tracer

            shutdown_tracer()
            logger.info("[telemetry] tracer shutdown")
        except Exception as exc:
            logger.debug("[shutdown] telemetry shutdown failed: %s", exc)


import logging

# Web app import - SQLAlchemy PostgreSQL dialect is already pre-validated at module load time (top of file)
from web.app import app as _web_app

app = FastAPI(lifespan=lifespan)


@app.get("/diagnostics/deployment")
async def _deployment_diagnostics_endpoint(
    x_diagnostics_key: str | None = Header(default=None, alias="X-Diagnostics-Key"),
) -> JSONResponse:
    """Return the latest secret-safe deployment audit when explicitly enabled."""
    if not _env_bool("DEPLOYMENT_DIAGNOSTICS_ENDPOINT_ENABLED", False):
        return JSONResponse(status_code=404, content={"ok": False, "error": "not_enabled"})
    expected = str(os.getenv("DEPLOYMENT_DIAGNOSTICS_KEY") or "").strip()
    if _production_readiness_required() and not expected:
        return JSONResponse(status_code=503, content={"ok": False, "error": "diagnostics_key_not_configured"})
    supplied = str(x_diagnostics_key or "").strip()
    if expected and not hmac.compare_digest(supplied, expected):
        return JSONResponse(status_code=401, content={"ok": False, "error": "invalid_diagnostics_key"})
    report_path = Path(
        os.getenv("DEPLOYMENT_DIAGNOSTICS_REPORT_PATH")
        or "/tmp/signalrank_deployment_diagnostics.json"
    )
    if not report_path.exists():
        return JSONResponse(
            status_code=202,
            content={"ok": False, "status": "pending", "report_path": str(report_path)},
        )
    try:
        payload = json.loads(report_path.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.exception("[deployment_diagnostics] report read failed: %s", exc)
        return JSONResponse(status_code=500, content={"ok": False, "error": "report_unreadable"})
    return JSONResponse(status_code=200, content={"ok": True, "report": payload})


# ─────────────────────────────────────────────────────────────────────────────────────
# Railway healthcheck - add directly to main app for reliability
# This ensures /healthz responds even if the mount fails or during edge cases
# ─────────────────────────────────────────────────────────────────────────────────────

class _HealthResponse(BaseModel):
    status: str = "ok"
    uptime: float
    signals_active: int = 0
    cache_hit_rate: float = 0.0
    resource_state: str = "OPTIMAL"


@app.get("/metrics/prometheus", include_in_schema=False)
async def _metrics_prometheus_endpoint() -> Response:
    """Expose Prometheus metrics directly on the Railway monolith.

    The compatibility web app is mounted later, but this direct route keeps the
    scrape/readiness contract available even if that mount changes or fails.
    """
    from core.telemetry import prometheus_content_type, prometheus_metrics_text

    return Response(
        content=prometheus_metrics_text(),
        media_type=prometheus_content_type(),
    )


@app.get("/health", response_model=_HealthResponse)
@app.get("/healthz", response_model=_HealthResponse)
@app.get("/livez", response_model=_HealthResponse)
async def _healthz_endpoint():
    """Cheap process liveness check.

    This endpoint deliberately performs no network or database I/O. Dependency
    admission belongs to ``/readyz`` so provider or database jitter cannot
    trigger a Railway restart loop.
    """
    resource_state = "OPTIMAL"
    try:
        from core.resource_governor import get_resource_governor

        resource_state = str(get_resource_governor().snapshot().state.value)
    except Exception:
        pass
    return _HealthResponse(
        status="ok",
        uptime=max(0.0, time.monotonic() - _PROCESS_STARTED_MONO),
        signals_active=0,
        cache_hit_rate=0.0,
        resource_state=resource_state,
    )


def _database_readiness_timeout_seconds() -> float:
    """Return the bounded timeout for the Railway database readiness probe.

    Railway starts health checks while migrations, startup maintenance and the
    Telegram application may still be warming the same small database pool.
    The previous 1.5 second budget was shorter than normal cold-start catalogue
    latency and produced false 503s even while ordinary database work succeeded.
    """
    raw = str(os.getenv("DB_READINESS_TIMEOUT_SECONDS") or "8").strip()
    try:
        value = float(raw)
    except (TypeError, ValueError):
        value = 8.0
    return max(2.0, min(30.0, value))


async def _database_readiness_check() -> dict[str, object]:
    """Verify connectivity and the complete runtime schema in one round trip."""
    timeout_s = _database_readiness_timeout_seconds()
    try:
        from alembic.config import Config
        from alembic.script import ScriptDirectory
        from sqlalchemy import text

        from db.priority import DBPriority
        from db.session import get_session, is_db_configured

        if not is_db_configured():
            return {"ok": False, "detail": "not_configured"}

        alembic_cfg = Config(str(Path(__file__).with_name("alembic.ini")))
        expected_heads = tuple(ScriptDirectory.from_config(alembic_cfg).get_heads())
        if len(expected_heads) != 1:
            return {"ok": False, "detail": "repository_migration_heads_invalid"}

        # Readiness is traffic-admission control, so it uses the reserved
        # critical lane rather than competing as an ordinary interactive query.
        # A single catalogue query proves connectivity, migration head, required
        # columns and the active-thesis guard without four separate round trips.
        async with get_session(
            priority=DBPriority.CRITICAL,
            label="readiness",
            timeout_seconds=timeout_s,
        ) as session:
            result = await asyncio.wait_for(
                session.execute(
                    text(
                        """
                        SELECT
                            COALESCE(
                                (SELECT version_num FROM alembic_version LIMIT 1),
                                ''
                            ) AS deployed_revision,
                            EXISTS (
                                SELECT 1
                                FROM information_schema.columns
                                WHERE table_schema = current_schema()
                                  AND table_name = 'decision_log'
                                  AND column_name = 'created_at'
                            ) AS decision_log_created_at,
                            EXISTS (
                                SELECT 1
                                FROM information_schema.columns
                                WHERE table_schema = current_schema()
                                  AND table_name = 'signals'
                                  AND column_name = 'mfe_pct'
                            ) AS signals_mfe_pct,
                            EXISTS (
                                SELECT 1
                                FROM information_schema.columns
                                WHERE table_schema = current_schema()
                                  AND table_name = 'signals'
                                  AND column_name = 'mae_pct'
                            ) AS signals_mae_pct,
                            EXISTS (
                                SELECT 1
                                FROM information_schema.columns
                                WHERE table_schema = current_schema()
                                  AND table_name = 'signals'
                                  AND column_name = 'performance_version'
                            ) AS signals_performance_version,
                            EXISTS (
                                SELECT 1
                                FROM pg_index AS i
                                JOIN pg_class AS idx ON idx.oid = i.indexrelid
                                JOIN pg_class AS tbl ON tbl.oid = i.indrelid
                                JOIN pg_namespace AS ns ON ns.oid = tbl.relnamespace
                                WHERE ns.nspname = current_schema()
                                  AND tbl.relname = 'signals'
                                  AND idx.relname = 'ix_signals_active_thesis'
                                  AND i.indisunique IS TRUE
                                  AND pg_get_expr(i.indpred, i.indrelid) ILIKE '%status%'
                                  AND pg_get_expr(i.indpred, i.indrelid) ILIKE '%active%'
                            ) AS active_guard_present,
                            (
                                SELECT COUNT(*)
                                FROM (
                                    SELECT signal_id
                                    FROM outcomes
                                    GROUP BY signal_id
                                    HAVING COUNT(*) > 1
                                ) AS duplicate_outcomes
                            ) AS outcome_duplicate_groups,
                            EXISTS (
                                SELECT 1
                                FROM pg_index AS i
                                JOIN pg_class AS idx ON idx.oid = i.indexrelid
                                JOIN pg_class AS tbl ON tbl.oid = i.indrelid
                                JOIN pg_namespace AS ns ON ns.oid = tbl.relnamespace
                                WHERE ns.nspname = current_schema()
                                  AND tbl.relname = 'outcomes'
                                  AND idx.relname = 'uq_outcomes_signal_id'
                                  AND i.indisunique IS TRUE
                            ) AS outcome_guard_present
                        """
                    )
                ),
                timeout=timeout_s,
            )
            row = result.mappings().one()
            await session.rollback()

        deployed = str(row.get("deployed_revision") or "")
        if deployed != expected_heads[0]:
            return {
                "ok": False,
                "detail": "migration_not_at_head",
                "deployed_revision": deployed or None,
                "expected_revision": expected_heads[0],
            }

        column_flags = {
            "decision_log.created_at": bool(row.get("decision_log_created_at")),
            "signals.mfe_pct": bool(row.get("signals_mfe_pct")),
            "signals.mae_pct": bool(row.get("signals_mae_pct")),
            "signals.performance_version": bool(row.get("signals_performance_version")),
        }
        missing_columns = sorted(name for name, present in column_flags.items() if not present)
        if missing_columns:
            return {
                "ok": False,
                "detail": "critical_schema_columns_missing",
                "missing": missing_columns,
                "revision": deployed,
            }

        if not bool(row.get("active_guard_present")):
            return {
                "ok": False,
                "detail": "active_signal_guard_missing",
                "index": "ix_signals_active_thesis",
                "revision": deployed,
            }

        outcome_duplicate_groups = int(row.get("outcome_duplicate_groups") or 0)
        if outcome_duplicate_groups:
            return {
                "ok": False,
                "detail": "duplicate_outcome_projections",
                "duplicate_groups": outcome_duplicate_groups,
                "revision": deployed,
            }
        if not bool(row.get("outcome_guard_present")):
            return {
                "ok": False,
                "detail": "outcome_projection_guard_missing",
                "index": "uq_outcomes_signal_id",
                "revision": deployed,
            }

        return {
            "ok": True,
            "detail": "reachable",
            "revision": deployed,
            "expected_revision": expected_heads[0],
            "critical_schema": column_flags,
            "active_signal_guard": True,
            "outcome_projection_guard": True,
            "outcome_duplicate_groups": 0,
            "probe_timeout_seconds": timeout_s,
        }
    except TimeoutError:
        logger.warning(
            "[readyz] database readiness probe timed out after %.2fs",
            timeout_s,
        )
        return {"ok": False, "detail": "timeout", "timeout_seconds": timeout_s}
    except Exception as exc:
        return {"ok": False, "detail": type(exc).__name__}


async def _redis_url_readiness_check(url: str, *, label: str) -> dict[str, object]:
    if not str(url or "").strip():
        return {"ok": False, "detail": "not_configured", "role": label}
    client = None
    try:
        from redis.asyncio import Redis

        client = Redis.from_url(
            str(url).strip(),
            decode_responses=True,
            socket_connect_timeout=0.75,
            socket_timeout=0.75,
            max_connections=max(
                1,
                min(64, int(os.getenv("REDIS_MAX_CONNECTIONS", "24") or 24)),
            ),
        )
        pong = await asyncio.wait_for(client.ping(), timeout=1.0)
        return {"ok": bool(pong), "detail": "reachable" if pong else "ping_failed", "role": label}
    except asyncio.TimeoutError:
        return {"ok": False, "detail": "timeout", "role": label}
    except Exception as exc:
        return {"ok": False, "detail": type(exc).__name__, "role": label}
    finally:
        if client is not None:
            try:
                close = getattr(client, "aclose", None) or getattr(client, "close", None)
                if close is not None:
                    result = close()
                    if asyncio.iscoroutine(result):
                        await result
            except Exception:
                logger.debug("[readyz] redis client close failed", exc_info=True)


def _is_unconfigured_runtime_value(value: object) -> bool:
    """Return True for empty/example values that must never pass production readiness."""
    raw = str(value or "").strip().strip('"').strip("'")
    if not raw:
        return True
    lowered = raw.lower()
    if raw.startswith("<") and raw.endswith(">"):
        return True
    return lowered in {
        "changeme",
        "change-me",
        "replace-me",
        "placeholder",
        "todo",
        "none",
        "null",
    }


def _production_cutover_check() -> dict[str, object]:
    """Reject accidental staging, placeholder, or restricted production deployments."""
    environment = str(
        os.getenv("RAILWAY_ENVIRONMENT_NAME")
        or os.getenv("RAILWAY_ENVIRONMENT")
        or os.getenv("APP_ENV")
        or os.getenv("ENVIRONMENT")
        or ""
    ).strip().lower()
    violations: list[str] = []
    if environment not in {"production", "prod"}:
        violations.append("environment_not_production")
    if _env_bool("PUBLIC_TESTING_MODE", False):
        violations.append("public_testing_enabled")
    if _env_bool("FULL_SYSTEM_STAGING_TEST_MODE", False) or _env_bool(
        "FULL_SYSTEM_STAGING_TEST_ACTIVE", False
    ):
        violations.append("staging_test_mode_enabled")
    if str(os.getenv("DELIVERY_AUDIENCE_ALLOWLIST") or "").strip():
        violations.append("delivery_allowlist_not_empty")
    if _env_bool("RESEND_AUDIENCE_ALLOWLIST_ONLY", False):
        violations.append("resend_allowlist_only")
    forced_financial = str(os.getenv("FINANCIAL_ACTIVATION_FORCED_OFF") or "").strip()
    if forced_financial:
        violations.append(f"financial_activation_forced_off:{forced_financial}")
    if not _env_bool("FREE_SIGNAL_DISTRIBUTION_ENABLED", True):
        violations.append("free_distribution_disabled")
    if not _env_bool("RUN_ENGINE_LOOP", True):
        violations.append("engine_loop_disabled")
    if not _env_bool("RUN_WORKER_LOOP", True):
        violations.append("worker_loop_disabled")
    if not _env_bool("LIFECYCLE_EVENT_NOTIFICATIONS_ENABLED", True):
        violations.append("lifecycle_notifications_disabled")
    if not _env_bool("SEND_OUTCOME_NOTIFICATIONS_ENABLED", True):
        violations.append("outcome_notifications_disabled")
    if _env_bool("LIFECYCLE_TP_SL_NOTIFICATIONS_ENABLED", False):
        violations.append("duplicate_tp_sl_notification_dispatchers_enabled")
    if _env_bool("DELIVERY_SIGNAL_UPDATE_ENABLED", False):
        violations.append("signal_delivery_edit_mode_enabled")
    try:
        if int(os.getenv("TELEGRAM_SEND_MAX_ATTEMPTS", "3") or 3) < 2:
            violations.append("telegram_send_retries_too_low")
    except Exception:
        violations.append("telegram_send_retries_invalid")
    try:
        if int(os.getenv("RESEND_UNSENT_INTERVAL_SECONDS", "30") or 30) > 60:
            violations.append("unsent_signal_recovery_interval_too_high")
    except Exception:
        violations.append("unsent_signal_recovery_interval_invalid")
    try:
        if int(os.getenv("OUTCOME_NOTIFICATION_INTERVAL_SECONDS", "30") or 30) > 60:
            violations.append("outcome_notification_interval_too_high")
    except Exception:
        violations.append("outcome_notification_interval_invalid")
    try:
        if int(os.getenv("MONITOR_REFRESH_INTERVAL_SECONDS", "60") or 60) > 120:
            violations.append("monitor_refresh_interval_too_high")
    except Exception:
        violations.append("monitor_refresh_interval_invalid")
    if _env_bool("RESEND_SKIP_WHEN_ENGINE_FANOUT_ACTIVE", False):
        violations.append("resend_recovery_can_be_suppressed_by_fanout")
    if _env_bool("TELEGRAM_RICH_MESSAGES_ENABLED", False):
        violations.append("uncertified_rich_signal_delivery_enabled")

    required_values = {
        "DATABASE_URL": os.getenv("DATABASE_URL"),
        "TELEGRAM_BOT_TOKEN": os.getenv("TELEGRAM_BOT_TOKEN"),
        "TELEGRAM_WEBHOOK_SECRET": os.getenv("TELEGRAM_WEBHOOK_SECRET"),
        "GEMINI_API_KEY": os.getenv("GEMINI_API_KEY"),
        "ENCRYPTION_KEY": os.getenv("ENCRYPTION_KEY"),
        "STATE_REDIS_URL": os.getenv("STATE_REDIS_URL") or os.getenv("REDIS_URL"),
        "DELIVERY_REDIS_URL": os.getenv("DELIVERY_REDIS_URL"),
    }
    for name, value in required_values.items():
        if _is_unconfigured_runtime_value(value):
            violations.append(f"missing_or_placeholder:{name}")

    owner_value = (
        os.getenv("OWNER_IDS")
        or os.getenv("OWNER_TELEGRAM_IDS")
        or os.getenv("OWNER_TELEGRAM_ID")
        or os.getenv("TELEGRAM_OWNER_ID")
    )
    if _is_unconfigured_runtime_value(owner_value):
        violations.append("missing_or_placeholder:OWNER_TELEGRAM_ID")

    state_url = str(required_values["STATE_REDIS_URL"] or "").strip()
    delivery_url = str(required_values["DELIVERY_REDIS_URL"] or "").strip()
    if state_url and delivery_url and state_url == delivery_url:
        violations.append("state_and_delivery_redis_not_distinct")

    if _env_bool("DEMO_EXECUTION_ENABLED", False) and _is_unconfigured_runtime_value(
        os.getenv("META_API_TOKEN")
    ):
        violations.append("missing_or_placeholder:META_API_TOKEN")

    if _env_bool("PAYMENTS_ENABLED", False) or _env_bool("PAYMENTS_PUBLIC_ENABLED", False):
        paystack_secret = str(os.getenv("PAYSTACK_SECRET_KEY") or "").strip().strip('"').strip("'")
        paystack_public = str(os.getenv("PAYSTACK_PUBLIC_KEY") or "").strip().strip('"').strip("'")
        if _is_unconfigured_runtime_value(paystack_secret) or not paystack_secret.startswith("sk_live_"):
            violations.append("paystack_live_secret_invalid")
        if _is_unconfigured_runtime_value(paystack_public) or not paystack_public.startswith("pk_live_"):
            violations.append("paystack_live_public_invalid")

    try:
        from core.financial_activation import evaluate_financial_activation
        financial = evaluate_financial_activation()
        if not financial.ok:
            violations.extend(
                f"financial:{check.name}" for check in financial.checks
                if check.blocking and not check.ok
            )
    except Exception as exc:
        violations.append(f"financial_activation_check:{type(exc).__name__}")

    return {
        "ok": not violations,
        "detail": "public_production" if not violations else ",".join(violations),
        "environment": environment or "unknown",
        "audience": "global" if not str(os.getenv("DELIVERY_AUDIENCE_ALLOWLIST") or "").strip() else "restricted",
    }


def _runtime_environment_name() -> str:
    return str(
        os.getenv("RAILWAY_ENVIRONMENT_NAME")
        or os.getenv("RAILWAY_ENVIRONMENT")
        or os.getenv("APP_ENV")
        or os.getenv("ENVIRONMENT")
        or ""
    ).strip().lower()


def _production_readiness_required() -> bool:
    """Return whether production-only cutover policy must gate traffic.

    Railway also hosts staging and preview environments. Platform presence by
    itself must not turn a dependency healthcheck into a production-launch
    certification check.
    """
    return _runtime_environment_name() in {"production", "prod"}


def _readiness_cutover_check(*, production: bool) -> dict[str, object]:
    cutover = _production_cutover_check()
    if production:
        return {**cutover, "required": True}
    return {
        **cutover,
        "ok": True,
        "required": False,
        "detail": "not_required_for_nonproduction",
        "production_detail": cutover.get("detail"),
    }


@app.get("/ready")
@app.get("/readyz")
async def _readyz_endpoint(response: Response) -> dict[str, object]:
    """Dependency admission check for Railway traffic routing."""
    state_url = str(
        os.getenv("STATE_REDIS_URL")
        or os.getenv("SIGNALRANK_STATE_REDIS_URL")
        or os.getenv("REDIS_URL")
        or ""
    ).strip()
    delivery_url = str(os.getenv("DELIVERY_REDIS_URL") or "").strip()
    production = _production_readiness_required()

    database, state_redis, delivery_redis = await asyncio.gather(
        _database_readiness_check(),
        _redis_url_readiness_check(state_url, label="state"),
        _redis_url_readiness_check(delivery_url, label="delivery"),
    )
    try:
        from core.financial_activation import evaluate_financial_activation
        financial_activation = evaluate_financial_activation().as_dict()
    except Exception as exc:
        financial_activation = {"ok": False, "detail": type(exc).__name__}
    try:
        from core.version import (
            EXPECTED_RELEASE_COMMIT,
            GIT_COMMIT_SHA,
            runtime_commit_matches_expected,
        )

        commit_ok, commit_detail = runtime_commit_matches_expected()
    except Exception as exc:
        GIT_COMMIT_SHA = str(os.getenv("RAILWAY_GIT_COMMIT_SHA") or os.getenv("GIT_COMMIT_SHA") or "unknown")
        EXPECTED_RELEASE_COMMIT = str(os.getenv("EXPECTED_RELEASE_COMMIT") or "")
        commit_ok, commit_detail = False, type(exc).__name__
    checks: dict[str, object] = {
        "database": database,
        "state_redis": state_redis,
        "delivery_redis": delivery_redis,
        "production_cutover": _readiness_cutover_check(production=production),
        "release_commit": {
            "ok": commit_ok if production else True,
            "required": production,
            "detail": commit_detail if production else "not_required_for_nonproduction",
        },
        "financial_activation": financial_activation,
    }

    distinct_redis = bool(state_url and delivery_url and state_url != delivery_url)
    allow_shared_dev = (
        not production
        and _env_bool("ALLOW_SHARED_REDIS_FOR_DEV", False)
    )
    checks["redis_separation"] = {
        "ok": distinct_redis or allow_shared_dev,
        "detail": "distinct" if distinct_redis else ("shared_dev_override" if allow_shared_dev else "must_be_distinct"),
    }

    shadow_required = _env_bool("SHADOW_OUTCOME_TRACKER_ENABLED", False) or _env_bool(
        "WORKER_SHADOW_TRACKER_ENABLED", False
    )
    if shadow_required:
        try:
            from engine.admin_pulse import _shadow_tracker_health

            shadow_health = _shadow_tracker_health()
            checks["shadow_tracker"] = {
                "ok": bool(shadow_health.get("proven")),
                "detail": str(shadow_health.get("status") or "missing"),
                **shadow_health,
            }
        except Exception as exc:
            checks["shadow_tracker"] = {
                "ok": False,
                "detail": f"health_probe_failed:{type(exc).__name__}",
            }
    if str(os.getenv("TELEGRAM_BOT_TOKEN") or "").strip():
        checks["telegram"] = {
            "ok": bool(_bot_ready and _bot_application is not None),
            "detail": "ready" if _bot_ready else "initializing",
        }
        webhook_secret_configured = bool(str(os.getenv("TELEGRAM_WEBHOOK_SECRET") or "").strip())
        checks["telegram_webhook_secret"] = {
            "ok": webhook_secret_configured or not production,
            "detail": "configured" if webhook_secret_configured else "missing",
        }

    try:
        from core.resource_governor import ResourceState, get_resource_governor

        snapshot = get_resource_governor().snapshot()
        checks["resource_guard"] = {
            "ok": snapshot.state is not ResourceState.CRITICAL,
            "detail": snapshot.state.value,
        }
    except Exception:
        checks["resource_guard"] = {"ok": True, "detail": "not_loaded"}

    ready = all(
        bool(value.get("ok"))
        for value in checks.values()
        if isinstance(value, dict)
    )
    if not ready:
        response.status_code = 503
        global _LAST_READINESS_FAILURE_SIGNATURE, _LAST_READINESS_FAILURE_LOG_MONO
        signature = json.dumps(checks, sort_keys=True, default=str)
        now = time.monotonic()
        if (
            signature != _LAST_READINESS_FAILURE_SIGNATURE
            or now - _LAST_READINESS_FAILURE_LOG_MONO >= 30.0
        ):
            logger.warning("[readyz] degraded checks=%s", signature)
            _LAST_READINESS_FAILURE_SIGNATURE = signature
            _LAST_READINESS_FAILURE_LOG_MONO = now
    deployed_revision = database.get("revision") or database.get("deployed_revision")
    expected_revision = database.get("expected_revision")
    return {
        "status": "ready" if ready else "degraded",
        "ready": ready,
        "release_identity": {
            "confirmed": bool(commit_ok and database.get("ok") and deployed_revision == expected_revision),
            "deployed_git_sha": str(GIT_COMMIT_SHA),
            "expected_git_sha": str(EXPECTED_RELEASE_COMMIT),
            "deployed_alembic_revision": deployed_revision,
            "expected_alembic_revision": expected_revision,
        },
        "checks": checks,
    }


async def _telegram_webhook_route(req: Request) -> dict:
    """Receive Telegram updates and dispatch them to the bot application.

    Telegram POSTs to this URL for every incoming message or command.
    PTB's Application.process_update() dispatches the update to the
    correct CommandHandler on uvicorn's event loop — no polling conflict.
    """
    logger.debug("[webhook] Telegram webhook endpoint hit")
    logger.debug(
        "[webhook] incoming update — content_type=%s",
        req.headers.get("content-type", ""),
    )
    if (not _bot_ready) or (_bot_application is None):
        try:
            payload = await req.json()
            logger.info(
                "[webhook] ingress queued while bot_not_ready update_id=%s",
                (payload or {}).get("update_id", "?"),
            )
            if not _append_pending_webhook_update(payload):
                logger.warning("[webhook] bot_not_ready pending queue is full")
                return {
                    "ok": False,
                    "error": "queue_full",
                    "bot_ready": False,
                    "status": "queue_full",
                    "queue_backend": "pending",
                }
            logger.warning(
                "[webhook] bot_not_ready — update queued size=%d",
                len(_pending_webhook_updates),
            )
            return {
                "ok": True,
                "queued": True,
                "bot_ready": False,
                "status": "queued",
                "queue_backend": "pending",
                "queue_size": len(_pending_webhook_updates),
            }
        except Exception:
            # Keep Telegram delivery path healthy even during transient startup.
            logger.warning("[webhook] bot_not_ready and payload parse failed; acknowledging")
            return {"ok": False, "error": "invalid_payload", "bot_ready": False, "status": "invalid_payload"}
    try:
        data = await req.json()
        update_id = (data or {}).get("update_id", "?")
        update_type = next(
            (k for k in (data or {}) if k not in ("update_id",)), "unknown"
        )
        logger.info("[webhook] ingress received update_id=%s type=%s", update_id, update_type)
        logger.debug("[webhook] dispatching update_id=%s type=%s", update_id, update_type)
        if _webhook_dispatch_queue is None:
            if not _append_pending_webhook_update(data):
                return {
                    "ok": False,
                    "error": "queue_full",
                    "bot_ready": True,
                    "status": "queue_full",
                    "queue_backend": "pending",
                }
            logger.warning("[webhook] dispatcher_not_ready — queued in pending buffer")
            return {
                "ok": True,
                "queued": True,
                "bot_ready": True,
                "status": "queued",
                "queue_backend": "pending",
                "queue_size": len(_pending_webhook_updates),
            }

        redis_fallback = False
        redis_enqueue_indeterminate = False
        if _use_redis_webhook_queue:
            enqueued = False
            duplicate = False
            redis_backend = "redis_legacy"
            try:
                if _webhook_stream.configured:
                    enqueue_result = await asyncio.wait_for(
                        _webhook_stream.enqueue(
                            data,
                            idempotency_key=f"telegram-update:{update_id}",
                        ),
                        timeout=0.35,
                    )
                    enqueued = bool(enqueue_result.accepted)
                    duplicate = bool(enqueue_result.duplicate)
                    redis_backend = "redis_stream"
                else:
                    enqueued = await asyncio.wait_for(
                        state.enqueue_webhook_update(
                            data,
                            max_depth=int(os.getenv("REDIS_WEBHOOK_QUEUE_MAX_DEPTH", "2000") or 2000),
                        ),
                        timeout=0.35,
                    )
                    redis_backend = "redis"
            except asyncio.TimeoutError:
                # A Redis timeout is indeterminate: the XADD may have committed
                # after our local wait expired. Falling back immediately to the
                # in-process queue can therefore process the same Telegram
                # update twice. Return a retryable 503 instead; Telegram retries
                # and the stream idempotency key collapses any late success.
                redis_enqueue_indeterminate = True
                logger.warning(
                    "[webhook] redis enqueue timeout update_id=%s action=retry_no_local_fallback",
                    update_id,
                )
            except Exception as exc:
                logger.warning("[webhook] redis enqueue failed update_id=%s err=%s", update_id, exc)
            if enqueued:
                _webhook_enqueue_started_at[str(update_id)] = time.monotonic()
                return {
                    "ok": True,
                    "queued": True,
                    "bot_ready": True,
                    "status": "queued",
                    "queue_backend": redis_backend,
                    "duplicate": duplicate,
                }
            if redis_enqueue_indeterminate:
                return {
                    "ok": False,
                    "error": "redis_enqueue_indeterminate",
                    "bot_ready": True,
                    "status": "retry",
                    "queue_backend": redis_backend,
                    "update_id": update_id,
                }
            logger.warning("[webhook] redis enqueue failed — falling back to in-process queue")
            redis_fallback = True

        try:
            _webhook_dispatch_queue.put_nowait(data)
            _webhook_enqueue_started_at[str(update_id)] = time.monotonic()
            response = {
                "ok": True,
                "queued": True,
                "bot_ready": True,
                "status": "queued",
                "queue_backend": "in_process",
                "queue_size": int(_webhook_dispatch_queue.qsize()),
            }
            if redis_fallback:
                response["redis_fallback"] = True
            return response
        except asyncio.QueueFull:
            webhook_queue_full_total.inc()
            logger.warning("[webhook] queue_full — dropping update_id=%s", update_id)
            return {"ok": False, "error": "queue_full", "status": "queue_full", "queue_backend": "in_process"}
    except Exception as exc:
        logger.error("[webhook] failed to process update: %s", exc)
        return {"ok": False, "error": "invalid_payload", "status": "invalid_payload"}


def _webhook_queue_diagnostics() -> dict[str, object]:
    in_process_size = None
    in_process_capacity = None
    try:
        if _webhook_dispatch_queue is not None:
            in_process_size = int(_webhook_dispatch_queue.qsize())
            in_process_capacity = int(_webhook_dispatch_queue.maxsize)
    except Exception:
        pass
    return {
        "bot_ready": bool(_bot_ready and _bot_application is not None),
        "dispatcher_ready": _webhook_dispatch_queue is not None,
        "redis_queue_enabled": bool(_use_redis_webhook_queue),
        "redis_stream_configured": bool(getattr(_webhook_stream, "configured", False)),
        "in_process_size": in_process_size,
        "in_process_capacity": in_process_capacity,
        "pending_buffer_size": len(_pending_webhook_updates),
        "inflight_updates": len(_inflight_update_tasks),
    }


def _webhook_rejection(
    req: Request,
    *,
    status_code: int,
    reason: str,
    extra: dict[str, object] | None = None,
) -> JSONResponse:
    diagnostics = _webhook_queue_diagnostics()
    if extra:
        diagnostics.update(extra)
    client_host = getattr(getattr(req, "client", None), "host", None)
    logger.warning(
        "[webhook_rejected] reason=%s status=%s client=%s diagnostics=%s",
        reason,
        status_code,
        client_host,
        diagnostics,
    )
    return JSONResponse(
        status_code=status_code,
        content={"ok": False, "error": reason, "diagnostics": diagnostics},
    )


@app.post("/telegram/webhook")
async def _telegram_webhook_http_route(req: Request) -> JSONResponse:
    """Authenticated, bounded Telegram ingress with retryable overload errors."""
    expected_secret = str(os.getenv("TELEGRAM_WEBHOOK_SECRET") or "").strip()
    supplied_secret = str(
        req.headers.get("x-telegram-bot-api-secret-token") or ""
    ).strip()
    if _production_readiness_required() and not expected_secret:
        return _webhook_rejection(
            req,
            status_code=503,
            reason="webhook_secret_not_configured",
        )
    if expected_secret and not hmac.compare_digest(supplied_secret, expected_secret):
        return _webhook_rejection(
            req,
            status_code=401,
            reason="invalid_webhook_secret",
            extra={"secret_header_present": bool(supplied_secret)},
        )

    max_body_bytes = max(
        1024,
        min(
            2 * 1024 * 1024,
            int(os.getenv("WEBHOOK_MAX_BODY_BYTES", str(1024 * 1024)) or 1024 * 1024),
        ),
    )
    content_length = req.headers.get("content-length")
    if content_length:
        try:
            if int(content_length) > max_body_bytes:
                return JSONResponse(
                    status_code=413,
                    content={"ok": False, "error": "payload_too_large"},
                )
        except ValueError:
            return JSONResponse(
                status_code=400,
                content={"ok": False, "error": "invalid_content_length"},
            )
    body = await req.body()
    if not body:
        return JSONResponse(
            status_code=400,
            content={"ok": False, "error": "empty_payload"},
        )
    if len(body) > max_body_bytes:
        return JSONResponse(
            status_code=413,
            content={"ok": False, "error": "payload_too_large"},
        )

    result = await _telegram_webhook_route(req)
    error = str(result.get("error") or "")
    status_code = 200
    if error in {"queue_full", "redis_enqueue_indeterminate"}:
        status_code = 503
    elif error:
        status_code = 400
    if status_code != 200:
        return _webhook_rejection(
            req,
            status_code=status_code,
            reason=error or "webhook_ingress_failed",
            extra={
                "queue_backend": str(result.get("queue_backend") or "unknown"),
                "route_result": {
                    key: value for key, value in result.items()
                    if key not in {"diagnostics"}
                },
            },
        )
    return JSONResponse(status_code=200, content=result)


async def _enqueue_webhook_update_async(data: dict) -> None:
    update_id = (data or {}).get("update_id", "?")
    queue_ref = _webhook_dispatch_queue
    if queue_ref is None:
        if not _append_pending_webhook_update(data):
            logger.error("[webhook] dispatcher_not_ready and pending queue full")
        logger.warning("[webhook] dispatcher_not_ready — queued in pending buffer")
        return

    try:
        enqueued = await asyncio.wait_for(
            state.enqueue_webhook_update(
                data,
                max_depth=int(os.getenv("REDIS_WEBHOOK_QUEUE_MAX_DEPTH", "2000") or 2000),
            ),
            timeout=0.35,
        )
    except asyncio.TimeoutError:
        logger.warning(
            "[webhook] redis enqueue timeout update_id=%s action=retry_no_local_fallback",
            update_id,
        )
        return
    except Exception as exc:
        enqueued = False
        logger.warning("[webhook] redis enqueue failed update_id=%s err=%s", update_id, exc)
    if enqueued:
        _webhook_enqueue_started_at[str(update_id)] = time.monotonic()
        return

    try:
        queue_ref = _webhook_dispatch_queue
        if queue_ref is None:
            if not _append_pending_webhook_update(data):
                logger.error(
                    "[webhook] dispatcher_not_ready during fallback and pending queue full update_id=%s",
                    update_id,
                )
            logger.warning("[webhook] dispatcher_not_ready during fallback enqueue update_id=%s", update_id)
            return
        queue_ref.put_nowait(data)
        _webhook_enqueue_started_at[str(update_id)] = time.monotonic()
        logger.info(
            "[webhook] ingress enqueued update_id=%s backend=in_process size=%s",
            update_id,
            int(queue_ref.qsize()),
        )
    except asyncio.QueueFull:
        webhook_queue_full_total.inc()
        logger.warning("[webhook] queue_full — dropping update_id=%s", update_id)


def _log_webhook_enqueue_task_error(task: asyncio.Task) -> None:
    try:
        if task.cancelled():
            return
        exc = task.exception()
        if exc is not None:
            logger.error(
                "[webhook] async enqueue task failed: %s",
                exc,
                exc_info=(type(exc), exc, exc.__traceback__),
            )
    except Exception:
        pass


@app.get("/telegram/webhook_status")
async def _telegram_webhook_status() -> dict:
    """Runtime diagnostics for Telegram webhook delivery."""
    info = await _safe_get_webhook_info()
    return {
        "ok": True,
        "bot_ready": bool(_bot_ready),
        "queued_updates": len(_pending_webhook_updates),
        "webhook_info": info,
    }


# Mount the existing web app AFTER the webhook route — FastAPI checks routes
# in registration order, so /telegram/webhook is matched before the catch-all.
# ============================================================================
# TradingView Webhook Endpoint
# ============================================================================

@app.post("/webhook/tradingview")
async def tradingview_webhook(payload: dict, secret: str = Header(None)):
    """
    Receive TradingView alerts and process them through the signal ranking engine.
    
    Payload expected from TradingView:
    {
        "ticker": "BTCUSDT",
        "action": "buy",
        "price": 68000,
        "timeframe": "1h",
        "indicator": "RSI_Breakout"
    }
    
    Security: Requires TV_WEBHOOK_SECRET header matching the configured secret.
    """
    import os
    
    # 1. Security Check
    expected_secret = os.getenv("TV_WEBHOOK_SECRET", "")
    if expected_secret and (secret != expected_secret):
        raise HTTPException(status_code=403, detail="Unauthorized")
    
    # 2. Log the incoming webhook
    logger.info("[tradingview] webhook received: %s", payload)
    
    # 3. Extract signal data
    symbol = payload.get("ticker", "")
    action = payload.get("action", "").upper()
    price = payload.get("price", 0)
    timeframe = payload.get("timeframe", "1h")
    indicator = payload.get("indicator", "unknown")
    
    if not symbol or not action:
        return {"status": "invalid_payload", "message": "Missing ticker or action"}
    
    # 4. Determine asset class
    from data.fetcher import get_asset_type
    asset_class = get_asset_type(symbol)
    
    # 5. Hydrate with macro context (news, VIX, DXY) if Gemini is available
    hydrated_payload = {
        "signal": {
            "ticker": symbol,
            "action": action,
            "indicator": indicator,
            "timeframe": timeframe,
            "entry": price,
        },
        "macro_context": {},
        "technical_stats": {},
    }
    
    # Try to get cached macro data
    try:
        from core.redis_cache import cache_get
        cached_news = await cache_get("macro:vix_level")
        cached_dxy = await cache_get("macro:dxy_trend")
        if cached_news or cached_dxy:
            hydrated_payload["macro_context"] = {
                "vix_level": cached_news,
                "dxy_trend": cached_dxy,
            }
    except Exception:
        pass  # Cache miss is OK
    
    # 6. Send to Gemini for signal ranking (if available)
    gemini_result = None
    try:
        from engine.ranking import analyze_signal_for_tradingview
        gemini_result = await analyze_signal_for_tradingview(hydrated_payload)
    except Exception as e:
        logger.warning("[tradingview] Gemini ranking failed: %s", e)
    
    # 7. Process the signal
    if gemini_result:
        score = gemini_result.get("score", 0)
        verdict = gemini_result.get("verdict", "REJECT")
        
        logger.info(
            "[tradingview] Signal processed: ticker=%s action=%s score=%s verdict=%s",
            symbol, action, score, verdict
        )
        
        # Send high-quality signals to Telegram
        if score > 75 and verdict in ("RANK_A", "RANK_B"):
            try:
                from signalrank_telegram.bot import send_signal_alert
                await send_signal_alert(
                    ticker=symbol,
                    action=action,
                    score=score,
                    verdict=verdict,
                    reason=gemini_result.get("reasoning", ""),
                )
            except Exception as e:
                logger.warning("[tradingview] Telegram notification failed: %s", e)
        
        return {
            "status": "processed",
            "score": score,
            "verdict": verdict,
            "reasoning": gemini_result.get("reasoning", ""),
        }
    
    # Fallback: basic signal processing if Gemini not available
    return {
        "status": "received",
        "ticker": symbol,
        "action": action,
        "asset_class": asset_class,
    }


@app.get("/webhook/tradingview_status")
async def tradingview_webhook_status():
    """Check TradingView webhook configuration status."""
    import os
    secret_set = bool(os.getenv("TV_WEBHOOK_SECRET", "").strip())
    return {
        "ok": True,
        "webhook_configured": secret_set,
    }


# Compatibility web/API surface. This catch-all mount must remain the final
# route so it cannot intercept Telegram, TradingView, Paystack, health, or
# readiness endpoints owned by the canonical Railway application.
app.mount("/", _web_app)
