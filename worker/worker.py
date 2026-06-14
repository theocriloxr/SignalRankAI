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

from core.redis_state import state
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

    def _log_task_result(self, name: str, task: asyncio.Task) -> None:
        try:
            if task.cancelled():
                logger.info("[worker] task cancelled: %s", name)
                return
            exc = task.exception()
            if exc is not None:
                logger.error(
                    "[worker] task crashed: %s err=%s",
                    name,
                    exc,
                    exc_info=(type(exc), exc, exc.__traceback__),
                )
        except Exception as inspect_exc:
            logger.warning("[worker] could not inspect task state for %s: %s", name, inspect_exc)

    def _spawn_task(self, name: str, coro) -> asyncio.Task:
        task = asyncio.create_task(coro)
        task.add_done_callback(lambda t, _name=name: self._log_task_result(_name, t))
        return task

    async def run(self) -> None:
        heartbeat_interval_s = max(60, int(os.getenv("WORKER_HEARTBEAT_INTERVAL_SECONDS", "300") or 300))
        managed_tasks: dict[str, dict[str, object]] = {}

        def _register_task(name: str, factory, restart_on_failure: bool = True) -> None:
            try:
                task = self._spawn_task(name, factory())
                managed_tasks[name] = {
                    "task": task,
                    "factory": factory,
                    "restart": bool(restart_on_failure),
                }
                logger.info("[worker] task started: %s", name)
            except Exception as exc:
                logger.error("[worker] failed to start task %s: %s", name, exc, exc_info=True)

        _register_task("expiry_loop", lambda: self._expiry_loop(), restart_on_failure=True)

        # News sync worker - fetches economic calendar every 6 hours
        # This populates the economic_events table for news filter
        _enable_news_sync = str(os.getenv("WORKER_NEWS_SYNC_ENABLED", "1")).strip().lower() in {"1", "true", "yes", "on"}
        if _enable_news_sync:
            try:
                from worker.news_sync_worker import start_news_sync_worker as _start_news
                _register_task("news_sync", lambda: _start_news(), restart_on_failure=True)
                logger.info("[worker] NewsSyncWorker started")
            except Exception as e:
                logger.warning("[worker] Failed to start news sync worker: %s", e)

        # Start real-time TP/SL outcome tracker
        _enable_worker_tracker = str(os.getenv("WORKER_OUTCOME_TRACKER_ENABLED", "1")).strip().lower() in {"1", "true", "yes", "on"}
        if _enable_worker_tracker:
            try:
                from engine.realtime_outcome_tracker import outcome_tracker
                _register_task("outcome_tracker", lambda: self._outcome_tracker_loop(outcome_tracker), restart_on_failure=True)
                logger.info("[worker] RealtimeOutcomeTracker started")
            except Exception as e:
                logger.warning("[worker] Failed to start outcome tracker: %s", e)
        
        # Start shadow outcome tracker for ML-rejected signals
        _enable_shadow = str(os.getenv("WORKER_SHADOW_TRACKER_ENABLED", "1")).strip().lower() in {"1", "true", "yes", "on"}
        if _enable_shadow:
            try:
                from engine.shadow_outcome_worker import shadow_outcome_worker
                _register_task("shadow_outcome_tracker", lambda: shadow_outcome_worker.start(), restart_on_failure=True)
                logger.info("[worker] ShadowOutcomeTracker started")
            except Exception as e:
                logger.warning("[worker] Failed to start shadow outcome tracker: %s", e)
        else:
            logger.info("[worker] RealtimeOutcomeTracker disabled for this worker instance")

        # Start market monitor for NO TRADE alerts
        if config.MARKET_MONITOR_ENABLED:
            try:
                from worker.market_monitor import start_market_monitor
                _register_task("market_monitor", lambda: start_market_monitor(), restart_on_failure=True)
            except Exception as e:
                logger.warning("[worker] Failed to start market monitor: %s", e)

        # Admin engine pulse (hourly) for owner/admin channels
        _enable_pulse = str(os.getenv("WORKER_ENGINE_PULSE_ENABLED", "1")).strip().lower() in {"1", "true", "yes", "on"}
        if _enable_pulse:
            try:
                from engine.admin_pulse import start_pulse_loop
                _register_task("engine_pulse", lambda: start_pulse_loop(), restart_on_failure=True)
                logger.info("[worker] EnginePulse started")
            except Exception as e:
                logger.warning("[worker] Failed to start EnginePulse: %s", e)

        if config.CRYPTO_WS_ENABLED:
            try:
                from data.ws_ingest import run_ws_ingestor
                _register_task("ws_ingestor", lambda: run_ws_ingestor(self._stop), restart_on_failure=True)
            except Exception:
                logger.exception("[worker] Failed to start WS ingestor")

        # ML daily retrain loop (optional)
        # FIX: ML training runs directly in the async event loop using await
        # Previously used asyncio.to_thread() which doesn't work with async functions
        if config.ML_TRAIN_ENABLED:
            try:
                _register_task("ml_train_loop", lambda: self._ml_train_loop(), restart_on_failure=True)
                logger.info("[worker] ML train loop registered")
            except Exception as e:
                logger.warning("[worker] Failed to start ML train loop: %s", e)

        # Data drift monitor loop (enabled by default)
        if str(os.getenv("ML_DRIFT_MONITOR_ENABLED", "1")).strip().lower() in {"1", "true", "yes", "on"}:
            try:
                _register_task("drift_monitor", lambda: self._drift_monitor_loop(), restart_on_failure=True)
            except Exception as e:
                logger.warning("[worker] Failed to start drift monitor loop: %s", e)
        
        import time
        last_heartbeat = time.time()
        try:
            while not self._stop.is_set():
                await asyncio.sleep(1.0)
                for name, spec in list(managed_tasks.items()):
                    task = spec.get("task")
                    if not isinstance(task, asyncio.Task):
                        continue
                    if not task.done():
                        continue

                    restart = bool(spec.get("restart", False))
                    if restart and not self._stop.is_set():
                        try:
                            factory = spec.get("factory")
                            if factory is None:
                                continue
                            logger.warning("[worker] restarting crashed task: %s", name)
                            new_task = self._spawn_task(name, factory())
                            spec["task"] = new_task
                        except Exception as exc:
                            logger.error("[worker] failed to restart task %s: %s", name, exc, exc_info=True)

                now = time.time()
                if now - last_heartbeat > heartbeat_interval_s:
                    logger.debug("[worker] heartbeat: running (interval=%ss)", heartbeat_interval_s)
                    last_heartbeat = now
        finally:
            if "outcome_tracker" in managed_tasks:
                try:
                    from engine.realtime_outcome_tracker import outcome_tracker
                    await outcome_tracker.stop()
                except Exception:
                    pass

            for name, spec in list(managed_tasks.items()):
                task = spec.get("task")
                if not isinstance(task, asyncio.Task):
                    continue
                task.cancel()
                with contextlib.suppress(BaseException):
                    await task
                logger.info("[worker] task stopped: %s", name)

    async def _expiry_loop(self) -> None:
        """Runs periodically - cleans up expired subscriptions."""
        while not self._stop.is_set():
            try:
                if is_db_configured():
                    async def _do_expire() -> None:
                        async with get_session() as session:
                            _ = await expire_subscriptions(session)
                            await session.commit()
                    await run_with_db_retry(_do_expire)
            except Exception:
                logger.exception("[worker] subscription expiry loop iteration failed")
            await asyncio.sleep(3600)

    async def _ml_train_loop(self) -> None:
        """Periodically retrain the ML model from Postgres outcomes."""
        # ADDED: Debug log to confirm function is being called
        logger.info("[worker] INSIDE ML TRAIN LOOP - function entered")
        
        try:
            from ml import train_model as ml_train
            logger.info("[worker] ML train_model import succeeded")
        except Exception as exc:
            logger.error("[worker] ML train loop disabled (import failed): %s", exc, exc_info=True)
            return

        interval = max(3600, int(getattr(config, "ML_TRAIN_INTERVAL_SECONDS", 86400) or 86400))
        logger.info("[worker] ML train loop interval set to %s seconds", interval)

        while not self._stop.is_set():
            try:
                # FIX: ml_train.main is an async function, so we await it directly
                # Previously used asyncio.to_thread() which doesn't work with async functions
                # and causes silent failures with no logs
                logger.info("[worker] ML training starting...")
                ok = await ml_train.main()
                if ok:
                    logger.info("[worker] ML model retrained successfully")
                else:
                    logger.info("[worker] ML model retrain skipped/failed (insufficient data)")
            except Exception as exc:
                logger.error("[worker] ML train loop error: %s", exc)

            try:
                await asyncio.wait_for(self._stop.wait(), timeout=interval)
            except asyncio.TimeoutError:
                continue

    async def _drift_retrain_once(self, ml_train_module, lookback_days: int = 7) -> None:
        try:
            logger.warning("[worker] starting drift-triggered ML retrain lookback_days=%s", lookback_days)
            ok = await ml_train_module.main(lookback_days=max(1, int(lookback_days or 7)))
            if ok:
                logger.info("[worker] drift-triggered ML retrain completed successfully")
            else:
                logger.info("[worker] drift-triggered ML retrain skipped/failed")
        except Exception as exc:
            logger.error("[worker] drift-triggered ML retrain error: %s", exc)
        finally:
            try:
                state.set_sync("signalrankai:ml:drift:retrain_running", "0", ex=300)
            except Exception:
                pass

    async def _drift_monitor_loop(self) -> None:
        """Compare live feature distributions against baseline and alert admins on drift."""
        import time as drift_time
        interval = max(900, int(os.getenv("ML_DRIFT_CHECK_INTERVAL_SECONDS", "3600") or 3600))
        psi_threshold = float(os.getenv("ML_DRIFT_PSI_THRESHOLD", "0.25") or 0.25)
        retrain_on_drift = str(os.getenv("ML_DRIFT_RETRAIN_ON_DETECT", "1")).strip().lower() in {"1", "true", "yes", "on"}

        while not self._stop.is_set():
            try:
                from ml.drift_monitor import detect_feature_drift
                from ml import train_model as ml_train

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
                    severity = 0.0
                    try:
                        severity = max(float(v) for v in (result.get("psi_scores") or {}).values())
                    except Exception:
                        severity = float(psi_threshold)
                    try:
                        state.set_sync("signalrankai:ml:drift:mode", "penalize", ex=max(1800, interval * 2))
                        state.set_sync("signalrankai:ml:drift:severity", f"{severity:.6f}", ex=max(1800, interval * 2))
                        state.set_sync("signalrankai:ml:drift:detected_at", str(drift_time.time()), ex=max(1800, interval * 2))
                    except Exception:
                        pass
                    await self._notify_admin_drift(result)
                    if retrain_on_drift and str(state.get_sync("signalrankai:ml:drift:retrain_running") or "").strip() != "1":
                        try:
                            state.set_sync("signalrankai:ml:drift:retrain_running", "1", ex=max(1800, interval * 2))
                            asyncio.create_task(self._drift_retrain_once(ml_train, lookback_days=7))
                        except Exception as exc:
                            logger.debug("[worker] could not schedule drift retrain: %s", exc)
                else:
                    try:
                        state.set_sync("signalrankai:ml:drift:mode", "normal", ex=max(600, interval))
                        state.set_sync("signalrankai:ml:drift:severity", "0", ex=max(600, interval))
                    except Exception:
                        pass
            except Exception as exc:
                logger.debug("[worker] drift monitor skipped: %s", exc)

            try:
                await asyncio.wait_for(self._stop.wait(), timeout=interval)
            except asyncio.TimeoutError:
                continue

    async def _outcome_tracker_loop(self, outcome_tracker) -> None:
        await outcome_tracker.start()
        try:
            while not self._stop.is_set():
                task = getattr(outcome_tracker, "_task", None)
                if isinstance(task, asyncio.Task) and task.done():
                    exc = None
                    try:
                        exc = task.exception()
                    except Exception:
                        exc = None
                    if exc is not None:
                        raise exc
                    break
                try:
                    await asyncio.wait_for(self._stop.wait(), timeout=5.0)
                except asyncio.TimeoutError:
                    continue
        finally:
            with contextlib.suppress(Exception):
                await outcome_tracker.stop()

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

    if threading.current_thread() is threading.main_thread():
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, _handle_sig)
            except NotImplementedError:
                pass

    await worker.run()


def main() -> None:
    run_sync(_amain(), timeout=None)


if __name__ == "__main__":
    main()
