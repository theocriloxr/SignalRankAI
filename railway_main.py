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

from fastapi import FastAPI
from apscheduler.schedulers.asyncio import AsyncIOScheduler


logger = logging.getLogger(__name__)


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


def _build_scheduler() -> AsyncIOScheduler:
    """Create scheduler and register jobs.

    Reuses existing jobs already defined in web.app and signalrank_telegram.bot.
    Each job is added in its own try/except so a missing function doesn't abort
    the entire scheduler.
    """
    from web.app import (
        _check_waitlist_capacity_job,
        _monitor_expired_invites_job,
    )

    scheduler = AsyncIOScheduler(timezone="UTC")

    # Web waitlist jobs (currently in web.app lifespan)
    try:
        scheduler.add_job(_check_waitlist_capacity_job, "interval", hours=1, id="wl_capacity")
    except Exception as exc:
        logger.warning(f"[sched] could not add wl_capacity job: {exc}")
    try:
        scheduler.add_job(_monitor_expired_invites_job, "interval", minutes=15, id="wl_monitor")
    except Exception as exc:
        logger.warning(f"[sched] could not add wl_monitor job: {exc}")

    # Bot/ops jobs — import lazily so a bot import error doesn't crash the scheduler
    try:
        from signalrank_telegram.bot import (
            downgrade_expired_subscriptions_job,
            auto_delete_old_signals_job,
            distribute_random_signals_to_free_users_job,
            resend_unsent_signals_job,
        )
        scheduler.add_job(downgrade_expired_subscriptions_job, "cron", hour=0, minute=0, id="downgrade_expired")
        scheduler.add_job(auto_delete_old_signals_job, "cron", day_of_week="sun", hour=3, minute=0, id="delete_old_signals")
        scheduler.add_job(distribute_random_signals_to_free_users_job, "interval", minutes=30, id="free_random_distribution")
        scheduler.add_job(resend_unsent_signals_job, "interval", minutes=10, id="resend_unsent")
    except Exception as exc:
        logger.warning(f"[sched] could not add bot jobs (bot import may have failed): {exc}")

    return scheduler


async def _start_telegram_polling() -> "tuple[object, bool]":
    """Start PTB polling using the existing global Application.

    The repo defines `signalrank_telegram.bot.application` at import time.
    We start it using the explicit initialize/start/updater.start_polling API.

    Returns (application, started_bool).  Never raises — failures are logged
    as warnings so the web server continues to run even without the bot.
    """
    try:
        from signalrank_telegram import bot as bot_module
    except Exception as exc:
        logger.warning(f"[bot] Could not import signalrank_telegram.bot: {exc}; skipping polling")
        return None, False

    application = getattr(bot_module, "application", None)

    # If the module built a Dummy app (DRY_RUN or missing token), do nothing.
    if application is None or not hasattr(application, "initialize"):
        logger.warning("[bot] Telegram application not available (no token or DRY_RUN); skipping polling")
        return application, False

    # If DRY_RUN, do not start polling
    if _env_bool("DRY_RUN", False):
        logger.warning("[bot] DRY_RUN enabled; skipping polling")
        return application, False

    try:
        await application.initialize()
        await application.start()
    except Exception as exc:
        logger.warning(f"[bot] application.initialize/start failed: {exc}; skipping polling")
        return application, False

    # updater must exist for polling
    updater = getattr(application, "updater", None)
    if updater is None:
        logger.warning("[bot] Telegram Application.updater is None; skipping polling (use run_bot() for webhook mode)")
        return application, False

    try:
        await updater.start_polling()
        logger.info("[bot] polling started")
        return application, True
    except Exception as exc:
        logger.warning(f"[bot] updater.start_polling failed: {exc}; skipping polling")
        return application, False


async def _stop_telegram_polling(application: object) -> None:
    """Stop PTB polling gracefully."""
    if application is None:
        return
    updater = getattr(application, "updater", None)
    try:
        if updater is not None and hasattr(updater, "stop"):
            await updater.stop()
    finally:
        if hasattr(application, "stop"):
            await application.stop()


def _start_engine_loop_in_background() -> asyncio.Task:
    """Start the blocking engine.main_loop in a thread executor."""
    from config import config
    from engine.core import main_loop

    dry_run = bool(getattr(config, "DRY_RUN", False))

    async def _runner() -> None:
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, lambda: main_loop(dry_run))

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

    # ── 2) Engine loop (long-running background task) ─────────────────────────
    engine_task = None
    try:
        engine_task = _start_engine_loop_in_background()
        logger.info("[startup] Engine loop task created")
    except Exception as exc:
        logger.warning(f"[startup] Could not start engine loop: {exc}")

    # ── 3) APScheduler jobs ───────────────────────────────────────────────────
    scheduler = None
    try:
        scheduler = _build_scheduler()
        scheduler.start()
        logger.info("[sched] started")
    except Exception as exc:
        logger.warning(f"[startup] Scheduler failed to start: {exc}")
        scheduler = None

    # ── 4) Telegram polling ───────────────────────────────────────────────────
    application, bot_started = None, False
    try:
        application, bot_started = await _start_telegram_polling()
    except Exception as exc:
        logger.warning(f"[startup] Telegram polling setup error (caught at lifespan level): {exc}")

    logger.info(
        f"[startup] complete — engine={'ok' if engine_task else 'skipped'} "
        f"scheduler={'ok' if scheduler else 'skipped'} "
        f"bot={'polling' if bot_started else 'skipped'}"
    )

    try:
        yield
    finally:
        # ── Shutdown order: bot → scheduler → engine task ─────────────────────
        if bot_started and application is not None:
            try:
                await _stop_telegram_polling(application)
                logger.info("[bot] stopped")
            except Exception as exc:
                logger.warning(f"[shutdown] bot stop error: {exc}")

        if scheduler is not None:
            try:
                scheduler.shutdown(wait=False)
                logger.info("[sched] shutdown")
            except Exception as exc:
                logger.warning(f"[shutdown] scheduler shutdown error: {exc}")

        if engine_task is not None:
            try:
                engine_task.cancel()
            except Exception:
                pass


# Serve the existing FastAPI app from web.app, but wrap with our monolith lifespan.
# This ensures routes/middleware remain unchanged.
from web.app import app as _web_app

# Recreate a FastAPI instance isn't necessary; we can reuse the existing one by swapping lifespan.
# FastAPI doesn't officially support reassigning lifespan after creation, so we create a new app
# and mount the existing app.
app = FastAPI(lifespan=lifespan)
app.mount("/", _web_app)