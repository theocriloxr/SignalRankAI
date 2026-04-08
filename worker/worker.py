
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
import json
from utils.async_runner import run_sync
import contextlib
import logging
import os
from config import config
import signal
import threading
from typing import Optional

from db.session import get_session, run_with_db_retry, is_db_configured
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
        heartbeat_interval_s = max(60, int(os.getenv("WORKER_HEARTBEAT_INTERVAL_SECONDS", "300") or 300))
        expiry_task = asyncio.create_task(self._expiry_loop())
        ml_task: Optional[asyncio.Task] = None
        market_monitor_task: Optional[asyncio.Task] = None
        ws_task: Optional[asyncio.Task] = None
        outcome_tracker_task: Optional[asyncio.Task] = None
        drift_task: Optional[asyncio.Task] = None

        # Start real-time TP/SL outcome tracker — this is the core monitoring loop
        # that detects when signals hit their targets and notifies users.
        # Default to ON in all deployments so every generated signal is tracked.
        # Override with WORKER_OUTCOME_TRACKER_ENABLED=0 to explicitly disable.
        _enable_worker_tracker = str(os.getenv("WORKER_OUTCOME_TRACKER_ENABLED", "1")).strip().lower() in {"1", "true", "yes", "on"}
        if _enable_worker_tracker:
            try:
                from engine.realtime_outcome_tracker import outcome_tracker
                outcome_tracker_task = asyncio.create_task(outcome_tracker.start())
                print("[worker] RealtimeOutcomeTracker started", flush=True)
                logger.info("[worker] RealtimeOutcomeTracker started")
            except Exception as e:
                print(f"[worker] Failed to start outcome tracker: {e}", flush=True)
                logger.warning("[worker] Failed to start outcome tracker: %s", e)
                outcome_tracker_task = None
        else:
            logger.info("[worker] RealtimeOutcomeTracker disabled for this worker instance")

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

        # Data drift monitor loop (enabled by default).
        if str(os.getenv("ML_DRIFT_MONITOR_ENABLED", "1")).strip().lower() in {"1", "true", "yes", "on"}:
            try:
                drift_task = asyncio.create_task(self._drift_monitor_loop())
            except Exception as e:
                print(f"[worker] Failed to start drift monitor loop: {e}", flush=True)
                drift_task = None
        import time
        last_heartbeat = time.time()
        try:
            while not self._stop.is_set():
                await asyncio.sleep(1.0)
                now = time.time()
                if now - last_heartbeat > heartbeat_interval_s:
                    logger.debug("[worker] heartbeat: running (interval=%ss)", heartbeat_interval_s)
                    last_heartbeat = now
        finally:
            if outcome_tracker_task is not None:
                try:
                    from engine.realtime_outcome_tracker import outcome_tracker
                    await outcome_tracker.stop()
                except Exception:
                    pass
                outcome_tracker_task.cancel()
                with contextlib.suppress(Exception):
                    await outcome_tracker_task
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
            if drift_task is not None:
                drift_task.cancel()
                with contextlib.suppress(Exception):
                    await drift_task
            expiry_task.cancel()
            with contextlib.suppress(Exception):
                await expiry_task

    async def _expiry_loop(self) -> None:
        # Runs periodically; safe no-op when DATABASE_URL not configured.
        while not self._stop.is_set():
            try:
                if is_db_configured():
                    async def _do_expire() -> None:
                        async with get_session() as session:
                            _ = await expire_subscriptions(session)
                            await session.commit()
                    await run_with_db_retry(_do_expire)
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

    async def _drift_monitor_loop(self) -> None:
        """Compare live feature distributions against baseline and alert admins on drift."""
        interval = max(900, int(os.getenv("ML_DRIFT_CHECK_INTERVAL_SECONDS", "3600") or 3600))
        psi_threshold = float(os.getenv("ML_DRIFT_PSI_THRESHOLD", "0.25") or 0.25)

        while not self._stop.is_set():
            try:
                from ml.drift_monitor import detect_feature_drift

                baseline_path = os.getenv("ML_BASELINE_FEATURE_STATS_PATH", "ml/baseline_feature_stats.json")
                live_path = os.getenv("ML_LIVE_FEATURE_STATS_PATH", "ml/live_feature_stats.json")

                if not (os.path.exists(baseline_path) and os.path.exists(live_path)):
                    raise FileNotFoundError("baseline/live feature stats files not found")

                with open(baseline_path, "r", encoding="utf-8") as fb:
                    baseline = json.load(fb) or {}
                with open(live_path, "r", encoding="utf-8") as fl:
                    live = json.load(fl) or {}

                result = detect_feature_drift(
                    baseline_features=dict(baseline),
                    live_features=dict(live),
                    psi_threshold=psi_threshold,
                )

                if bool(result.get("drift_detected")):
                    await self._notify_admin_drift(result)
            except Exception as exc:
                logger.debug("[worker] drift monitor skipped: %s", exc)

            try:
                await asyncio.wait_for(self._stop.wait(), timeout=interval)
            except asyncio.TimeoutError:
                continue

    async def _notify_admin_drift(self, result: dict) -> None:
        token = (os.getenv("TELEGRAM_BOT_TOKEN") or "").strip()
        if not token:
            return

        try:
            import requests
            from config import OWNER_IDS, ADMIN_IDS

            recipients = sorted({int(x) for x in ((OWNER_IDS or set()) | (ADMIN_IDS or set()))})
            if not recipients:
                return

            drifting = list(result.get("drifting_features") or [])
            top = ", ".join(drifting[:8]) if drifting else "unknown"
            text = (
                "⚠️ ML Data Drift Detected\n"
                f"Features drifting: {top}\n"
                "Action: trigger retraining with hyperparameter tuning."
            )
            for rid in recipients:
                try:
                    requests.post(
                        f"https://api.telegram.org/bot{token}/sendMessage",
                        json={"chat_id": int(rid), "text": text},
                        timeout=8,
                    )
                except Exception:
                    continue
        except Exception:
            return


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
