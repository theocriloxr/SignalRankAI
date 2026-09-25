"""Analytics and learning worker role.

Owns shadow outcomes and bounded all-asset candle collection.  It intentionally
does not own Telegram delivery or live outcome computation.
"""
from __future__ import annotations
import asyncio
import contextlib
import logging
import os
logger=logging.getLogger(__name__)

def _enabled(name: str, default: bool=True) -> bool:
    raw=os.getenv(name); return default if raw is None else raw.strip().lower() in {"1","true","yes","on"}


async def _ml_drift_loop(stop: asyncio.Event) -> None:
    """Observe independent feature drift and model-output starvation health."""
    from core.redis_state import state
    from ml.drift_monitor import detect_feature_drift, detect_prediction_starvation
    from ml.live_drift import (
        load_durable_feature_baseline,
        load_live_feature_samples,
        load_live_prediction_samples,
    )

    interval=max(900, int(os.getenv("ML_DRIFT_CHECK_INTERVAL_SECONDS", "3600") or 3600))
    delay=max(0.0, float(os.getenv("ML_DRIFT_STARTUP_DELAY_SECONDS", "180") or 180))
    if delay > 0:
        try:
            await asyncio.wait_for(stop.wait(), timeout=delay)
            return
        except asyncio.TimeoutError:
            pass

    while not stop.is_set():
        feature_result = {
            "actionable": False,
            "drift_detected": False,
            "psi_scores": {},
            "reason": "not_evaluated",
        }
        prediction_result = {
            "actionable": False,
            "starvation_detected": False,
            "samples": 0,
            "reason": "not_evaluated",
        }
        try:
            # Prediction health is independent of PSI baseline availability.
            # This prevents a missing feature baseline from masking a serving
            # model that rejects every live candidate.
            try:
                predictions=load_live_prediction_samples()
                prediction_result=detect_prediction_starvation(
                    list(predictions or []),
                    minimum_samples=max(
                        10,
                        int(os.getenv("ML_STARVATION_MIN_LIVE_SAMPLES", "50") or 50),
                    ),
                    minimum_pass_rate=max(
                        0.0,
                        min(
                            1.0,
                            float(os.getenv("ML_STARVATION_MIN_PASS_RATE", "0.01") or 0.01),
                        ),
                    ),
                )
            except Exception as exc:
                prediction_result={
                    "actionable": False,
                    "starvation_detected": False,
                    "samples": 0,
                    "reason": f"prediction_health_error:{type(exc).__name__}",
                }

            # PSI remains useful but must not gate prediction-health evaluation.
            try:
                baseline=await load_durable_feature_baseline()
                live=load_live_feature_samples()
                if baseline and live:
                    feature_result=detect_feature_drift(
                        baseline_features=dict(baseline),
                        live_features=dict(live),
                        psi_threshold=float(os.getenv("ML_DRIFT_PSI_THRESHOLD", "0.25") or 0.25),
                        minimum_samples=max(
                            10,
                            int(os.getenv("ML_DRIFT_MIN_LIVE_SAMPLES", "50") or 50),
                        ),
                        minimum_features=max(
                            1,
                            int(os.getenv("ML_DRIFT_MIN_EVALUATED_FEATURES", "5") or 5),
                        ),
                    )
                else:
                    feature_result={
                        "actionable": False,
                        "drift_detected": False,
                        "psi_scores": {},
                        "reason": "baseline_or_live_features_unavailable",
                    }
            except Exception as exc:
                feature_result={
                    "actionable": False,
                    "drift_detected": False,
                    "psi_scores": {},
                    "reason": f"feature_health_error:{type(exc).__name__}",
                }

            logger.info(
                "[analytics_ml_drift] feature_actionable=%s feature_drift=%s feature_reason=%s "
                "prediction_actionable=%s prediction_starvation=%s samples=%s pass_rate=%s "
                "raw_max=%s threshold_min=%s prediction_reason=%s",
                feature_result.get("actionable"),
                feature_result.get("drift_detected"),
                feature_result.get("reason"),
                prediction_result.get("actionable"),
                prediction_result.get("starvation_detected"),
                prediction_result.get("samples"),
                prediction_result.get("pass_rate"),
                prediction_result.get("raw_max"),
                prediction_result.get("threshold_min"),
                prediction_result.get("reason"),
            )

            feature_drift=bool(feature_result.get("drift_detected"))
            starvation=bool(prediction_result.get("starvation_detected"))
            ttl=max(1800, interval * 2)
            state.set_sync(
                "signalrankai:ml:drift:mode",
                "penalize" if feature_drift else "normal",
                ex=ttl,
            )
            try:
                severity=(
                    max(float(v) for v in (feature_result.get("psi_scores") or {}).values())
                    if feature_drift
                    else 0.0
                )
            except Exception:
                severity=(
                    float(os.getenv("ML_DRIFT_PSI_THRESHOLD", "0.25") or 0.25)
                    if feature_drift
                    else 0.0
                )
            state.set_sync(
                "signalrankai:ml:drift:severity",
                f"{severity:.6f}",
                ex=ttl,
            )
            state.set_sync(
                "signalrankai:ml:starvation:mode",
                "detected" if starvation else "normal",
                ex=ttl,
            )
            state.set_sync(
                "signalrankai:ml:starvation:summary",
                __import__("json").dumps(
                    prediction_result,
                    separators=(",", ":"),
                    default=str,
                ),
                ex=ttl,
            )
            if starvation:
                logger.warning(
                    "[analytics_ml_prediction_starvation] %s",
                    prediction_result,
                )

            should_retrain=(
                feature_drift and _enabled("ML_DRIFT_RETRAIN_ON_DETECT", True)
            ) or (
                starvation and _enabled("ML_STARVATION_RETRAIN_ON_DETECT", False)
            )
            active_reason=(
                "feature_drift"
                if feature_drift
                else "prediction_starvation"
                if starvation
                else ""
            )
            if should_retrain and active_reason:
                key=f"signalrankai:ml:{active_reason}:consecutive"
                prior=int(state.get_sync(key) or 0)
                consecutive=prior+1
                state.set_sync(key, str(consecutive), ex=max(1800, interval * 4))
                required=max(
                    1,
                    int(os.getenv("ML_DRIFT_REQUIRED_CONSECUTIVE_CHECKS", "2") or 2),
                )
                if (
                    consecutive >= required
                    and str(
                        state.get_sync("signalrankai:ml:drift:retrain_running") or ""
                    ) != "1"
                ):
                    state.set_sync(
                        "signalrankai:ml:drift:retrain_running",
                        "1",
                        ex=ttl,
                    )
                    try:
                        from ml import train_model as ml_train

                        ok=await ml_train.main(
                            lookback_days=max(
                                1,
                                int(os.getenv("ML_DRIFT_RETRAIN_LOOKBACK_DAYS", "7") or 7),
                            )
                        )
                        logger.info(
                            "[analytics_ml_drift_retrain] reason=%s status=%s",
                            active_reason,
                            "success" if ok else "skipped_or_failed",
                        )
                    finally:
                        state.set_sync(
                            "signalrankai:ml:drift:retrain_running",
                            "0",
                            ex=300,
                        )
            else:
                if not feature_drift:
                    state.set_sync(
                        "signalrankai:ml:feature_drift:consecutive",
                        "0",
                        ex=max(600, interval),
                    )
                if not starvation:
                    state.set_sync(
                        "signalrankai:ml:prediction_starvation:consecutive",
                        "0",
                        ex=max(600, interval),
                    )
        except Exception as exc:
            logger.exception(
                "[analytics_ml_drift] cycle_failed error=%s",
                type(exc).__name__,
            )

        try:
            await asyncio.wait_for(stop.wait(), timeout=interval)
        except asyncio.TimeoutError:
            pass

async def run_async(stop_event: asyncio.Event | None=None) -> None:
    stop=stop_event or asyncio.Event()
    tasks=[]
    shadow=None
    if _enabled("SHADOW_TRACKING_ENABLED", True):
        from engine.shadow_outcome_worker import shadow_outcome_worker
        shadow=shadow_outcome_worker
        await shadow.start()
    if _enabled("ASSET_LEARNING_ENABLED", True):
        from worker.asset_learning_worker import asset_learning_worker
        tasks.append(asyncio.create_task(asset_learning_worker.run(stop),name="asset-learning"))
    if _enabled("DYNAMIC_INSTRUMENT_DISCOVERY_ENABLED", True):
        from services.instrument_catalogue_refresh import instrument_catalogue_refresh_loop
        tasks.append(
            asyncio.create_task(
                instrument_catalogue_refresh_loop(stop),
                name="instrument-catalogue-refresh",
            )
        )
    if _enabled("ML_DRIFT_MONITOR_ENABLED", False):
        tasks.append(asyncio.create_task(_ml_drift_loop(stop),name="analytics-ml-drift"))
    if _enabled("ANALYTICS_ML_TRAIN_ENABLED", True):
        async def _ml_loop() -> None:
            delay=max(60, int(os.getenv("ANALYTICS_ML_TRAIN_STARTUP_DELAY_SECONDS", "900") or 900))
            interval=max(3600, int(os.getenv("ML_TRAIN_INTERVAL_SECONDS", "86400") or 86400))
            try:
                await asyncio.wait_for(stop.wait(), timeout=delay)
                return
            except asyncio.TimeoutError:
                pass
            while not stop.is_set():
                try:
                    from ml import train_model as ml_train
                    ok=await ml_train.main()
                    logger.info("[analytics] ml_train status=%s", "success" if ok else "skipped_or_failed")
                except Exception as exc:
                    logger.error("[analytics] ml_train failed err=%s", exc)
                try:
                    await asyncio.wait_for(stop.wait(), timeout=interval)
                except asyncio.TimeoutError:
                    pass
        tasks.append(asyncio.create_task(_ml_loop(),name="analytics-ml-train"))
    if _enabled("LEARNING_HISTORY_RETENTION_ENABLED", False):
        from db.storage_maintenance import learning_history_maintenance_loop
        tasks.append(
            asyncio.create_task(
                learning_history_maintenance_loop(),
                name="learning-history-retention",
            )
        )
    if _enabled("CONTINUOUS_IMPROVEMENT_REVIEW_ENABLED", True):
        from services.continuous_improvement.scheduler import continuous_improvement_loop
        tasks.append(
            asyncio.create_task(
                continuous_improvement_loop(stop),
                name="continuous-improvement-review",
            )
        )
    logger.info("[analytics] started shadow=%s tasks=%s",bool(shadow),[task.get_name() for task in tasks])
    try:
        await stop.wait()
    finally:
        if shadow is not None: await shadow.stop()
        for task in tasks: task.cancel()
        for task in tasks:
            with contextlib.suppress(asyncio.CancelledError): await task

def run() -> None: asyncio.run(run_async())
start=run
__all__=["run","run_async","start"]
