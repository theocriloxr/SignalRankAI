"""Signal-engine role adapter."""

from __future__ import annotations

import asyncio
import logging
import os
import threading

logger = logging.getLogger(__name__)


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return bool(default)
    return raw.strip().lower() in {"1", "true", "yes", "on", "y"}


def _start_adaptive_candle_persistence() -> threading.Thread | None:
    """Drain adaptive candle snapshots in the process that produces them.

    The scanner and generic worker are separate Railway services. The adaptive
    candle queue is intentionally process-local, so a worker process cannot
    consume snapshots enqueued by the dedicated engine process. Run one daemon
    consumer alongside the synchronous engine loop to preserve full-market
    candle evidence without blocking strategy evaluation.
    """
    if not _env_bool("ADAPTIVE_CANDLE_CAPTURE_ENABLED", True):
        return None
    if not _env_bool("ADAPTIVE_CANDLE_ENGINE_DRAIN_ENABLED", True):
        return None

    def _target() -> None:
        async def _run() -> None:
            from engine.adaptive.candle_store import candle_capture_loop

            stop_event = asyncio.Event()
            await candle_capture_loop(stop_event)

        try:
            asyncio.run(_run())
        except Exception as exc:
            logger.exception("[adaptive_candles] engine drain stopped unexpectedly: %s", exc)

    thread = threading.Thread(
        target=_target,
        name="adaptive-candle-engine-drain",
        daemon=True,
    )
    thread.start()
    logger.info("[adaptive_candles] engine-local persistence consumer started")
    return thread


def run(*, dry_run: bool | None = None) -> None:
    from config import config
    from engine.core import main_loop

    _start_adaptive_candle_persistence()
    main_loop(config.DRY_RUN if dry_run is None else bool(dry_run))


start = run

__all__ = ["run", "start"]
