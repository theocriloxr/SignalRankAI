
#
# SignalRankAI Async Worker Entrypoint
#
# This module manages all background processing: market data polling, strategy execution,
# ML retraining, and outcome tracking. All features are controlled by config toggles.
# Each background task is launched as an async coroutine and is gracefully cancelled on shutdown.
#
# Example config toggles: config.MARKET_MONITOR_ENABLED, config.CRYPTO_WS_ENABLED, config.ML_TRAIN_ENABLED
#
import asyncio
from utils.async_runner import run_sync
import contextlib
import logging
from config import config
import signal
import threading
from typing import Optional

from db.session import get_session
from db.repository import expire_subscriptions

logger = logging.getLogger(__name__)




class Worker:
    """Async worker process skeleton.

    Responsibilities (to be implemented incrementally):
    - Poll market data / consume WS ticks
    - Run strategy engine
    - Call engine.signal_controller.SignalController to approve + persist + dispatch
    - Run outcome tracking loop
    """

    def __init__(self) -> None:
        self._stop = asyncio.Event()
        self.dry_run = config.DRY_RUN

    def request_stop(self) -> None:
        self._stop.set()

    async def run(self) -> None:
        expiry_task = asyncio.create_task(self._expiry_loop())
        ml_task: Optional[asyncio.Task] = None
        market_monitor_task: Optional[asyncio.Task] = None
        ws_task: Optional[asyncio.Task] = None

        # Start market monitor for NO TRADE alerts
        if config.MARKET_MONITOR_ENABLED:
            try:
                from worker.market_monitor import start_market_monitor
                market_monitor_task = asyncio.create_task(start_market_monitor())
            except Exception as e:
                print(f"[worker] Failed to start market monitor: {e}", flush=True)
                market_monitor_task = None

        if config.CRYPTO_WS_ENABLED:
            try:
                from data.ws_ingest import run_ws_ingestor

                ws_task = asyncio.create_task(run_ws_ingestor(self._stop))
            except Exception:
                ws_task = None

        # ML daily retrain loop (optional)
        if config.ML_TRAIN_ENABLED:
            try:
                ml_task = asyncio.create_task(self._ml_train_loop())
            except Exception as e:
                print(f"[worker] Failed to start ML train loop: {e}", flush=True)
                ml_task = None
        import time
        last_heartbeat = time.time()
        try:
            while not self._stop.is_set():
                await asyncio.sleep(1.0)
                now = time.time()
                if now - last_heartbeat > 30:
                    print(f"[worker] heartbeat: running", flush=True)
                    logger.info(f"[worker] heartbeat: running")
                    last_heartbeat = now
        finally:
            if market_monitor_task is not None:
                market_monitor_task.cancel()
                with contextlib.suppress(Exception):
                    await market_monitor_task
            if ws_task is not None:
                ws_task.cancel()
                with contextlib.suppress(Exception):
                    await ws_task
            if ml_task is not None:
                ml_task.cancel()
                with contextlib.suppress(Exception):
                    await ml_task
            expiry_task.cancel()
            with contextlib.suppress(Exception):
                await expiry_task

    async def _expiry_loop(self) -> None:
        # Runs periodically; safe no-op when DATABASE_URL not configured.
        while not self._stop.is_set():
            try:
                if ENGINE is not None:
                    async with get_session() as session:
                        _ = await expire_subscriptions(session)
                        await session.commit()
            except Exception:
                # Keep worker alive; production version should log structured errors.
                pass
            await asyncio.sleep(3600)

    async def _ml_train_loop(self) -> None:
        """Periodically retrain the ML model from Postgres outcomes."""
        # Import inside to avoid startup failures if deps missing in minimal envs
        try:
            from ml import train_model as ml_train
        except Exception as exc:  # pragma: no cover
            print(f"[worker] ML train loop disabled (import failed): {exc}", flush=True)
            return

        interval = max(3600, int(getattr(config, "ML_TRAIN_INTERVAL_SECONDS", 86400) or 86400))

        while not self._stop.is_set():
            try:
                ok = await ml_train.main()
                if ok:
                    print("[worker] ML model retrained successfully", flush=True)
                else:
                    print("[worker] ML model retrain skipped/failed (insufficient data)", flush=True)
            except Exception as exc:  # pragma: no cover
                print(f"[worker] ML train loop error: {exc}", flush=True)

            # Sleep until next window or until stop requested
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=interval)
            except asyncio.TimeoutError:
                continue


async def _amain() -> None:
    worker = Worker()

    loop = asyncio.get_running_loop()

    def _handle_sig(*_: object) -> None:
        worker.request_stop()

    # NOTE: `loop.add_signal_handler` only works in the main thread on Unix.
    # In RUN_MODE=all we run the worker in a background thread, so skip
    # installing signal handlers there.
    if threading.current_thread() is threading.main_thread():
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, _handle_sig)
            except NotImplementedError:
                # Windows event loop may not support add_signal_handler
                pass

    await worker.run()


def main() -> None:
    # Worker is a long-running loop; do not apply run_sync timeout.
    run_sync(_amain(), timeout=None)


if __name__ == "__main__":
    main()
