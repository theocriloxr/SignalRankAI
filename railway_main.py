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
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, HTTPException
from apscheduler.schedulers.asyncio import AsyncIOScheduler


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


async def _run_startup_ops() -> None:
    """Run DB migrations/startup ops first.

    Uses existing db.auto_ops.run_startup_ops which handles:
    - DB reachability retry
    - advisory lock
    - alembic upgrade head
    - extra safety table/column ensures
    """
    from db.auto_ops import run_startup_ops

    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, lambda: run_startup_ops("all"))


async def _maybe_run_start_fresh_keep_users() -> None:
    """Optional one-time DB refresh: keep users, wipe runtime tables.

    Controlled by env vars:
      START_FRESH_KEEP_USERS_ON_BOOT=1
      START_FRESH_FORCE=1 (optional)
      START_FRESH_RESET_VERSION=v2 (optional marker namespace)
    """
    enabled = str(os.getenv("START_FRESH_KEEP_USERS_ON_BOOT", "0") or "0").strip().lower() in {"1", "true", "yes", "on"}
    if not enabled:
        return

    from db.session import get_session, is_db_configured
    from sqlalchemy import text

    if not is_db_configured():
        logger.warning("[startup] fresh reset requested but DB not configured")
        return

    reset_version = str(os.getenv("START_FRESH_RESET_VERSION", "v1") or "v1").strip()
    force_reset = str(os.getenv("START_FRESH_FORCE", "0") or "0").strip().lower() in {"1", "true", "yes", "on"}
    marker_key = f"startup_reset_done_{reset_version}"

    async with get_session() as session:
        if not force_reset:
            marker = await session.execute(
                text("SELECT value FROM runtime_state WHERE key = :k LIMIT 1"),
                {"k": marker_key},
            )
            if marker.scalar_one_or_none() is not None:
                logger.info("[startup] fresh reset skipped (marker exists): %s", marker_key)
                await session.commit()
                return

        # Cross-replica advisory lock
        lock_ok = True
        try:
            lock_row = await session.execute(text("SELECT pg_try_advisory_lock(739909)"))
            lock_ok = bool((lock_row.scalar_one_or_none() or False))
        except Exception:
            lock_ok = True
        if not lock_ok:
            logger.info("[startup] fresh reset skipped (another instance owns lock)")
            await session.commit()
            return

        # Archive known labeled outcomes before truncate
        await session.execute(
            text(
                """
                INSERT INTO ml_past_training_data (
                    signal_id, asset, timeframe, direction,
                    entry, stop_loss, take_profit,
                    rr_estimate, score, strength, regime, strategy_name, ml_probability,
                    outcome_status, outcome_r_multiple, outcome_percent, outcome_meta,
                    signal_created_at, outcome_closed_at, archived_at
                )
                SELECT
                    s.signal_id, s.asset, s.timeframe, s.direction,
                    s.entry, s.stop_loss, s.take_profit,
                    s.rr_estimate, s.score, s.strength, s.regime, s.strategy_name, s.ml_probability,
                    o.status, o.r_multiple, o.percent, COALESCE(o.meta::jsonb, '{}'::jsonb),
                    s.created_at, o.closed_at, NOW()
                FROM signals s
                JOIN outcomes o ON o.signal_id = s.signal_id
                ON CONFLICT (signal_id) DO NOTHING
                """
            )
        )

        rows = await session.execute(
            text(
                """
                SELECT tablename
                FROM pg_tables
                WHERE schemaname = 'public'
                  AND tablename NOT IN ('users', 'alembic_version', 'ml_past_training_data', 'runtime_state')
                """
            )
        )
        tables = [str(r[0]) for r in rows.all() if r and r[0]]
        if tables:
            quoted = ", ".join('"' + t.replace('"', '""') + '"' for t in tables)
            await session.execute(text(f"TRUNCATE TABLE {quoted} RESTART IDENTITY CASCADE"))

        await session.execute(text("DELETE FROM runtime_state"))
        await session.execute(
            text(
                """
                INSERT INTO runtime_state(key, value, expires_at, updated_at)
                VALUES (:k, :v::jsonb, NULL, NOW())
                ON CONFLICT (key) DO UPDATE
                SET value = EXCLUDED.value, expires_at = NULL, updated_at = NOW()
                """
            ),
            {"k": marker_key, "v": '{"done": true}'},
        )
        await session.commit()
        logger.warning("[startup] START_FRESH_KEEP_USERS_ON_BOOT applied: wiped_tables=%d marker=%s", len(tables), marker_key)


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

    return scheduler


async def _start_telegram_bot() -> "tuple[object, bool]":
    """Configure the Telegram bot for webhook mode and register the webhook URL.

    Process:
      1. Set TELEGRAM_USE_WEBHOOK so run_bot() registers all handlers, stores
         the Application in bot._webhook_application, and returns immediately
         instead of blocking in run_polling().
      2. Await run_bot() in a thread executor so we know all handlers are
         registered before proceeding.
      3. Initialize + start the Application on uvicorn's event loop.
      4. Delete any stale webhook, then register the new one with Telegram.

    Returns (application, True) on success, (None, False) on any failure.
    Never raises — failures are logged so the web server keeps running.
    """
    global _bot_application
    print("[bot] webhook setup starting", flush=True)

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
            print(f"[bot] run_bot() setup error: {exc}", flush=True)
            logger.error(f"[bot] run_bot() setup error: {exc}")
            return str(exc)

    # Await the executor so all handlers are registered before we call initialize()
    try:
        loop = asyncio.get_running_loop()
        setup_error = await loop.run_in_executor(None, _run_bot_safe)
    except Exception as exc:
        print(f"[bot] run_bot setup executor failed: {exc}", flush=True)
        logger.warning(f"[bot] run_bot() executor failed: {exc}; skipping webhook setup")
        return None, False

    if setup_error:
        logger.warning(f"[bot] run_bot() returned setup error: {setup_error}")

    # Retrieve the fully-configured Application stored by run_bot()
    try:
        from signalrank_telegram import bot as _bot_module
        app_obj = getattr(_bot_module, "_webhook_application", None)
    except Exception as exc:
        logger.warning(f"[bot] Could not access _webhook_application: {exc}; skipping webhook setup")
        return None, False

    if app_obj is None:
        try:
            # Best-effort second read in case another import path set it.
            import importlib
            _bot_module = importlib.import_module("signalrank_telegram.bot")
            app_obj = getattr(_bot_module, "_webhook_application", None)
        except Exception:
            app_obj = None

    if app_obj is None:
        print("[bot] webhook setup failed: _webhook_application is None", flush=True)
        logger.warning("[bot] _webhook_application is None after run_bot(); skipping webhook setup")
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

    # Register webhook with Telegram
    webhook_url = _get_webhook_url()
    if webhook_url:
        webhook_endpoint = f"{webhook_url}/telegram/webhook"
        try:
            await app_obj.bot.delete_webhook(drop_pending_updates=True)
            await app_obj.bot.set_webhook(webhook_endpoint)
            print(f"[bot] webhook registered: {webhook_endpoint}", flush=True)
            logger.info("[bot] webhook registered: %s", webhook_endpoint)
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
    # Delete webhook first so Telegram stops queuing updates during shutdown
    if os.getenv("TELEGRAM_USE_WEBHOOK"):
        try:
            await application.bot.delete_webhook()
        except Exception:
            pass
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
            print(f"[worker] background loop crashed: {exc}", flush=True)
            logger.exception(f"[worker] background loop crashed: {exc}")
            raise

    return asyncio.create_task(_runner())


@asynccontextmanager
async def lifespan(_: FastAPI):
    # ── 1) DB auto-migration / startup ops ────────────────────────────────────
    # Must succeed — if DB is truly unreachable after retries, let it propagate
    # so Railway shows a clear failure reason rather than a silent crash loop.
    try:
        await _run_startup_ops()
    except Exception as exc:
        logger.error(f"[startup] DB startup ops failed: {exc}; continuing anyway — web endpoints will serve degraded responses")

    # Optional one-time fresh reset (users preserved) runs before engine/worker/bot.
    try:
        await _maybe_run_start_fresh_keep_users()
    except Exception as exc:
        logger.warning(f"[startup] fresh reset step failed: {exc}")

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
        while not bot_stop_event.is_set() and not bot_started:
            try:
                print("[startup] Telegram webhook setup attempt", flush=True)
                application, bot_started = await _start_telegram_bot()
                print(f"[startup] Telegram webhook setup completed: started={bot_started}", flush=True)
                if bot_started:
                    return
            except Exception as exc:
                print(f"[startup] Telegram webhook setup error (background): {exc}", flush=True)
                logger.warning(f"[startup] Telegram webhook setup error (background): {exc}")

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


from web.app import app as _web_app

app = FastAPI(lifespan=lifespan)


@app.post("/telegram/webhook")
async def _telegram_webhook_route(req: Request) -> dict:
    """Receive Telegram updates and dispatch them to the bot application.

    Telegram POSTs to this URL for every incoming message or command.
    PTB's Application.process_update() dispatches the update to the
    correct CommandHandler on uvicorn's event loop — no polling conflict.
    """
    logger.info(
        "[webhook] incoming update — content_type=%s",
        req.headers.get("content-type", ""),
    )
    if _bot_application is None:
        print("[webhook] bot_not_initialized — update dropped", flush=True)
        logger.warning("[webhook] _bot_application not initialized — dropping update")
        # Return 503 so Telegram retries instead of losing updates.
        raise HTTPException(status_code=503, detail="bot_initializing")
    try:
        from telegram import Update
        data = await req.json()
        update_id = (data or {}).get("update_id", "?")
        update_type = next(
            (k for k in (data or {}) if k not in ("update_id",)), "unknown"
        )
        logger.info("[webhook] dispatching update_id=%s type=%s", update_id, update_type)
        update = Update.de_json(data, _bot_application.bot)
        await _bot_application.process_update(update)
        return {"ok": True}
    except Exception as exc:
        logger.error("[webhook] failed to process update: %s", exc)
        return {"ok": False, "error": str(exc)}


# Mount the existing web app AFTER the webhook route — FastAPI checks routes
# in registration order, so /telegram/webhook is matched before the catch-all.
app.mount("/", _web_app)