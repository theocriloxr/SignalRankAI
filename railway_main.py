"""Railway Free Tier monolith entrypoint.

Runs FastAPI + APScheduler + python-telegram-bot polling in a single asyncio event loop using FastAPI lifespan.

Start with:
  uvicorn railway_main:app --host 0.0.0.0 --port ${PORT:-8000}

This keeps existing main.py intact.
"""

from __future__ import annotations

import os
import asyncio
import logging
from collections import deque
from contextlib import asynccontextmanager
import time
from typing import Iterable

from fastapi import FastAPI, Request, HTTPException
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from prometheus_client import Counter, Gauge, Histogram


logger = logging.getLogger(__name__)

# Ensure INFO-level logs are visible in Railway regardless of uvicorn's logging config.
try:
    from utils.logging_config import setup_logging as _setup_logging
    _setup_logging()
except Exception:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s [%(name)s] %(message)s")

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
    """Best-effort readiness check for PTB Application handler registration."""
    if app_obj is None:
        return False
    try:
        handlers_map = getattr(app_obj, "handlers", None)
        if not isinstance(handlers_map, dict):
            return False
        for _group, handler_list in handlers_map.items():
            try:
                if handler_list and len(handler_list) > 0:
                    return True
            except Exception:
                continue
    except Exception:
        return False
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
    """Derive the public HTTPS URL for the Telegram webhook.

    Uses RAILWAY_PUBLIC_DOMAIN (set automatically by Railway) or the
    explicit WEBHOOK_DOMAIN / WEBHOOK_URL env var as a fallback.
    """
    domain = (
        os.getenv("RAILWAY_PUBLIC_DOMAIN")
        or os.getenv("WEBHOOK_DOMAIN")
        or os.getenv("WEBHOOK_URL")
        or ""
    ).strip()
    if not domain:
        return ""
    if not domain.startswith("https://"):
        domain = f"https://{domain}"
    return domain.rstrip("/")


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return bool(default)
    return raw.strip().lower() in {"1", "true", "yes", "y", "on"}


def _log_railway_env_readiness() -> None:
    """Log deployment-critical env readiness for Railway."""
    running_on_railway = bool((os.getenv("RAILWAY_SERVICE_NAME") or "").strip() or (os.getenv("RAILWAY_ENVIRONMENT") or "").strip())
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


async def _archive_ml_history_job() -> None:
    """Backfill ml_past_training_data from finalized outcomes (idempotent)."""
    try:
        from ml.schema_version import MODEL_FORMAT_VERSION, get_current_schema_version
        from db.session import get_session, is_db_configured
        from sqlalchemy import text
        if not is_db_configured():
            return

        async with get_session() as session:
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
    from web.app import (
        _check_waitlist_capacity_job,
        _monitor_expired_invites_job,
    )

    scheduler = AsyncIOScheduler(timezone="UTC")

    # VIP waitlist TTL — web layer only, not present in run_bot()
    try:
        scheduler.add_job(
            _check_waitlist_capacity_job,
            "interval",
            hours=1,
            id="wl_capacity",
            replace_existing=True,
            max_instances=1,
        )
    except Exception as exc:
        logger.warning(f"[sched] could not add wl_capacity job: {exc}")
    try:
        scheduler.add_job(
            _monitor_expired_invites_job,
            "interval",
            minutes=15,
            id="wl_monitor",
            replace_existing=True,
            max_instances=1,
        )
    except Exception as exc:
        logger.warning(f"[sched] could not add wl_monitor job: {exc}")

    # ML archive backfill (idempotent): keep historical training table populated.
    try:
        scheduler.add_job(
            _archive_ml_history_job,
            "interval",
            minutes=10,
            id="ml_archive_backfill",
            replace_existing=True,
            max_instances=1,
        )
    except Exception as exc:
        logger.warning(f"[sched] could not add ml_archive_backfill job: {exc}")

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
        print(f"[bot] webhook setup import error: {exc}", flush=True)
        logger.warning(f"[bot] Could not import run_bot: {exc}; skipping webhook setup")
        return None, False

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
            handlers_ready = handlers_flag or handlers_detected
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

    # Fallback: if an application object exists and handlers are attached,
    # proceed even if the explicit readiness flag never flipped.
    if app_obj is not None and not handlers_ready:
        handlers_ready = _app_has_registered_handlers(app_obj)
        if handlers_ready:
            logger.warning(
                "[bot] readiness flag missing but handlers detected; proceeding with webhook startup"
            )

    if app_obj is None or not handlers_ready:
        print("[bot] webhook setup failed: handlers not ready", flush=True)
        logger.warning(
            "[bot] webhook application/handlers not ready after discovery window; skipping webhook setup"
        )
        return None, False

    # Initialize and start the Application on uvicorn's event loop
    try:
        await app_obj.initialize()
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

    # Register webhook with Telegram
    webhook_url = _get_webhook_url()
    if webhook_url:
        webhook_endpoint = f"{webhook_url}/telegram/webhook"
        try:
            await app_obj.bot.delete_webhook(drop_pending_updates=True)
            await app_obj.bot.set_webhook(webhook_endpoint)
            print(f"[bot] webhook registered: {webhook_endpoint}", flush=True)
            logger.info("[bot] webhook registered: %s", webhook_endpoint)
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
                logger.warning("[webhook] get_webhook_info failed after set_webhook: %s", _wh_exc)
        except Exception as exc:
            print(f"[bot] set_webhook failed: {exc}", flush=True)
            logger.warning(
                f"[bot] set_webhook failed: {exc} — bot initialized but Telegram may not route updates here"
            )
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


def _start_engine_loop_in_background() -> asyncio.Task:
    """Start the blocking engine.main_loop in a thread executor."""
    from config import config
    from engine.core import main_loop

    dry_run = bool(getattr(config, "DRY_RUN", False))

    async def _runner() -> None:
        loop = asyncio.get_running_loop()
        print("[engine] background loop starting", flush=True)
        logger.info("[engine] background loop starting")
        try:
            await loop.run_in_executor(None, lambda: main_loop(dry_run))
        except Exception as exc:
            print(f"[engine] background loop crashed: {exc}", flush=True)
            logger.exception(f"[engine] background loop crashed: {exc}")
            raise

    return asyncio.create_task(_runner())


def _start_worker_loop_in_background() -> asyncio.Task:
    """Start the worker.main loop in a thread executor."""
    from worker.worker import main as worker_main

    async def _runner() -> None:
        loop = asyncio.get_running_loop()
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

    return asyncio.create_task(_runner())


@asynccontextmanager
async def lifespan(_: FastAPI):
    _log_railway_env_readiness()
    # ── Lifespan heartbeat: confirm event loop is alive ──
    async def _lifespan_heartbeat():
        import time
        while True:
            logger.info(f"[lifespan] heartbeat: event loop alive at {time.strftime('%Y-%m-%d %H:%M:%S')}")
            await asyncio.sleep(60)
    asyncio.create_task(_lifespan_heartbeat())
    # ── 1) DB startup/background maintenance ───────────────────────────────────
    # Keep startup healthcheck-friendly: schedule DB-heavy work in background,
    # and only wait for bounded time when explicitly configured.
    startup_ops_task: asyncio.Task | None = None
    startup_maintenance_tasks: list[asyncio.Task] = []

    # On Railway, default to non-blocking startup unless user explicitly sets a value.
    _default_ops_timeout = "0" if os.getenv("RAILWAY_SERVICE_NAME") else "35"
    startup_ops_timeout_s = int(os.getenv("STARTUP_OPS_TIMEOUT_SECONDS", _default_ops_timeout) or 0)

    try:
        startup_ops_task = asyncio.create_task(_run_startup_ops())
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
        logger.error(f"[startup] DB startup ops failed: {exc}; continuing anyway — web endpoints will serve degraded responses")

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

        # Always run archive pass afterwards to keep ml_past_training_data filled.
        try:
            await _archive_ml_history_job()
            logger.info("[startup] post-maintenance: ml archive backfill step complete")
        except Exception as exc:
            logger.warning(f"[startup] ml archive initial backfill failed: {exc}")

        logger.info("[startup] post-maintenance end")

    # Keep maintenance non-blocking by default on Railway, with optional bounded wait.
    _default_maintenance_timeout = "0" if os.getenv("RAILWAY_SERVICE_NAME") else "15"
    maintenance_timeout_s = int(
        os.getenv("STARTUP_MAINTENANCE_TIMEOUT_SECONDS", _default_maintenance_timeout) or 0
    )
    try:
        maintenance_task = asyncio.create_task(_run_post_startup_maintenance())
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


    # ── 2) Engine loop (long-running background task) ─────────────────────────
    engine_task = None
    try:
        engine_task = _start_engine_loop_in_background()
        print("[startup] Engine loop task created", flush=True)
        logger.info("[startup] Engine loop task created")
    except Exception as exc:
        print(f"[startup] Could not start engine loop: {exc}", flush=True)
        logger.warning(f"[startup] Could not start engine loop: {exc}")

    # ── 2b) Worker loop (long-running background task) ───────────────────────
    worker_task = None
    try:
        worker_task = _start_worker_loop_in_background()
        print("[startup] Worker loop task created", flush=True)
        logger.info("[startup] Worker loop task created")
    except Exception as exc:
        print(f"[startup] Could not start worker loop: {exc}", flush=True)
        logger.warning(f"[startup] Could not start worker loop: {exc}")

    # ── Crash detection for background tasks ─────────────────────────────────
    async def _monitor_background_tasks():
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
                    logger.warning("[monitor] %s task failed: %s", name, exc)
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

    async def _monitor_telegram_webhook_health():
        while True:
            await asyncio.sleep(60)
            if (not _bot_ready) or (_bot_application is None):
                continue
            try:
                queue_size = 0
                queue_util = 0.0
                if _webhook_dispatch_queue is not None:
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
                            await _bot_application.bot.set_webhook(_endpoint)
                            logger.warning("[webhook] periodic self-heal: webhook was unset, re-registered=%s", _endpoint)
                            print(f"[webhook] periodic self-heal: re-registered={_endpoint}", flush=True)
                    except Exception as _heal_exc:
                        logger.warning("[webhook] periodic self-heal failed: %s", _heal_exc)
            except Exception as exc:
                logger.warning("[webhook] periodic status check failed: %s", exc)

    async def _webhook_worker(worker_id: int) -> None:
        """Background worker: process Telegram updates from queue."""
        while True:
            payload = await _webhook_dispatch_queue.get()
            payload_update_id = (payload or {}).get("update_id", "?")
            started_at = _webhook_enqueue_started_at.pop(str(payload_update_id), None)
            try:
                if (not _bot_ready) or (_bot_application is None):
                    _pending_webhook_updates.append(payload)
                    continue
                from telegram import Update
                update_type = next((k for k in (payload or {}) if k not in ("update_id",)), "unknown")
                logger.info("[webhook] worker=%s processing update_id=%s type=%s", worker_id, payload_update_id, update_type)
                update = Update.de_json(payload, _bot_application.bot)
                await _bot_application.process_update(update)
                _record_dispatch_latency(str(payload_update_id), started_at)
            except Exception as exc:
                logger.error("[webhook] worker=%s failed processing update: %s", worker_id, exc)
            finally:
                try:
                    _webhook_dispatch_queue.task_done()
                except Exception:
                    pass

    asyncio.create_task(_monitor_background_tasks())
    asyncio.create_task(_monitor_telegram_webhook_health())

    # Bounded queue + worker pool to sustain high concurrent webhook traffic.
    global _webhook_dispatch_queue, _webhook_dispatch_workers
    _queue_size = int(os.getenv("WEBHOOK_UPDATE_QUEUE_SIZE", "5000") or 5000)
    _worker_count = int(os.getenv("WEBHOOK_UPDATE_WORKERS", "64") or 64)
    _webhook_dispatch_queue = asyncio.Queue(maxsize=max(100, _queue_size))
    _webhook_dispatch_workers = [
        asyncio.create_task(_webhook_worker(i + 1))
        for i in range(max(4, _worker_count))
    ]
    logger.info(
        "[webhook] dispatcher started workers=%s queue_size=%s",
        len(_webhook_dispatch_workers),
        _webhook_dispatch_queue.maxsize,
    )

    # ── 3) APScheduler jobs ───────────────────────────────────────────────────
    scheduler = None
    try:
        scheduler = _build_scheduler()
        scheduler.start()
        logger.info("[sched] started")
    except Exception as exc:
        logger.warning(f"[startup] Scheduler failed to start: {exc}")
        scheduler = None

    # ── 4) Telegram webhook ───────────────────────────────────────────────────
    # Keep startup fast for Railway healthchecks; initialize bot in background
    # with retries until it is ready.
    application, bot_started = None, False
    bot_start_task: asyncio.Task | None = None
    bot_stop_event = asyncio.Event()

    async def _start_bot_bg() -> None:
        nonlocal application, bot_started
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

    try:
        bot_start_task = asyncio.create_task(_start_bot_bg())
        print("[startup] Telegram webhook setup scheduled in background", flush=True)
    except Exception as exc:
        print(f"[startup] Could not schedule Telegram webhook setup: {exc}", flush=True)
        logger.warning(f"[startup] Could not schedule Telegram webhook setup: {exc}")

    logger.info(
        f"[startup] complete — engine={'ok' if engine_task else 'skipped'} "
        f"worker={'ok' if worker_task else 'skipped'} "
        f"scheduler={'ok' if scheduler else 'skipped'} "
        f"bot={'webhook' if bot_started else 'initializing'}"
    )

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


from web.app import app as _web_app

app = FastAPI(lifespan=lifespan)


@app.post("/telegram/webhook")
async def _telegram_webhook_route(req: Request) -> dict:
    """Receive Telegram updates and dispatch them to the bot application.

    Telegram POSTs to this URL for every incoming message or command.
    PTB's Application.process_update() dispatches the update to the
    correct CommandHandler on uvicorn's event loop — no polling conflict.
    """
    logger.info("[webhook] Telegram webhook endpoint hit")
    print("[webhook] Telegram webhook endpoint hit", flush=True)
    logger.info(
        "[webhook] incoming update — content_type=%s",
        req.headers.get("content-type", ""),
    )
    if (not _bot_ready) or (_bot_application is None):
        try:
            payload = await req.json()
            _pending_webhook_updates.append(payload)
            logger.warning(
                "[webhook] bot_not_ready — update queued size=%d",
                len(_pending_webhook_updates),
            )
            return {"ok": True, "queued": True, "bot_ready": False}
        except Exception:
            # Return 503 only if payload could not be parsed/queued.
            raise HTTPException(status_code=503, detail="bot_initializing")
    try:
        from telegram import Update
        data = await req.json()
        update_id = (data or {}).get("update_id", "?")
        update_type = next(
            (k for k in (data or {}) if k not in ("update_id",)), "unknown"
        )
        logger.info("[webhook] dispatching update_id=%s type=%s", update_id, update_type)
        if _webhook_dispatch_queue is None:
            _pending_webhook_updates.append(data)
            logger.warning("[webhook] dispatcher_not_ready — queued in pending buffer")
            return {"ok": True, "queued": True, "dispatcher": "pending_buffer"}

        try:
            _webhook_dispatch_queue.put_nowait(data)
            # Removed by worker pop(update_id) when processed; unmatched IDs are bounded by queue volume.
            _webhook_enqueue_started_at[str(update_id)] = time.monotonic()
            return {
                "ok": True,
                "dispatched": True,
                "queue_size": int(_webhook_dispatch_queue.qsize()),
            }
        except asyncio.QueueFull:
            webhook_queue_full_total.inc()
            logger.warning("[webhook] queue_full — dropping update_id=%s", update_id)
            return {"ok": False, "error": "queue_full"}
    except Exception as exc:
        logger.error("[webhook] failed to process update: %s", exc)
        return {"ok": False, "error": str(exc)}


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
app.mount("/", _web_app)
