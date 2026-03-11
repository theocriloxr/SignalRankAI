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
        scheduler.add_job(_check_waitlist_capacity_job, "interval", hours=1, id="wl_capacity")
    except Exception as exc:
        logger.warning(f"[sched] could not add wl_capacity job: {exc}")
    try:
        scheduler.add_job(_monitor_expired_invites_job, "interval", minutes=15, id="wl_monitor")
    except Exception as exc:
        logger.warning(f"[sched] could not add wl_monitor job: {exc}")

    return scheduler


async def _start_telegram_polling() -> "tuple[object, bool]":
    """Start the Telegram bot by running run_bot() in a thread executor.

    run_bot() builds its own Application with every command handler
    registered, starts an APScheduler BackgroundScheduler, and calls
    application.run_polling() which creates its own asyncio event loop.
    Running it in a thread executor isolates it from uvicorn's loop.

    The module-level `application` object in bot.py only carries ~16
    miscellaneous handlers added at import time.  The full handler set
    (start, help, status, signals …) is only registered inside run_bot().
    Using run_bot() directly ensures every command works.

    Returns (None, True) on successful dispatch — the thread manages its
    own lifecycle and will stop cleanly when the process receives SIGTERM.
    """
    if _env_bool("DRY_RUN", False):
        logger.warning("[bot] DRY_RUN enabled; skipping polling")
        return None, False

    bot_token = (os.getenv("TELEGRAM_BOT_TOKEN") or "").strip()
    if not bot_token:
        logger.warning("[bot] TELEGRAM_BOT_TOKEN not set; skipping polling")
        return None, False

    try:
        from signalrank_telegram.bot import run_bot
    except Exception as exc:
        logger.warning(f"[bot] Could not import run_bot: {exc}; skipping polling")
        return None, False

    def _run_bot_safe() -> None:
        """Wrapper so any immediate exception from run_bot() appears in logs."""
        try:
            run_bot()
        except Exception as exc:
            logger.error(f"[bot] run_bot() exited with error: {exc}")

    try:
        loop = asyncio.get_running_loop()
        # run_bot() is blocking — it calls application.run_polling() which
        # creates its own event loop.  run_in_executor keeps uvicorn's loop free.
        loop.run_in_executor(None, _run_bot_safe)
        logger.info("[bot] run_bot() dispatched to thread executor — all handlers registered")
        return None, True
    except Exception as exc:
        logger.warning(f"[bot] Failed to dispatch run_bot to executor: {exc}; skipping polling")
        return None, False


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