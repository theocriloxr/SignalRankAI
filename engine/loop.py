"""Engine loop: async runner that periodically runs strategies over assets."""
import asyncio
import logging
import os
import time
from typing import Iterable, List, Dict

from utils.async_runner import run_sync
from engine.strategies.signal_generator import SignalGenerator, StrategySelector
from engine.signal_deduplicator import SignalDeduplicator, MLRejectionTracker
from engine.market_state import get_market_state_async
from db.repository import persist_signal, persist_decision_log
from db import models
from db.session import async_session
from datetime import datetime

logger = logging.getLogger(__name__)

# Global instances
signal_gen = SignalGenerator()
dedup = SignalDeduplicator()
ml_tracker = MLRejectionTracker()


async def _process_asset_timeframe(asset: str, timeframe: str, include_ml: bool = False) -> list:
    signals: list = []
    try:
        market_state = await get_market_state_async(asset, [timeframe], include_ml=include_ml)
        tf_data = market_state.get("timeframes", {}).get(timeframe)
        if not tf_data:
            return signals
        candles = tf_data.get("candles", [])
        indicators = tf_data.get("indicators", {})
        ml_prob = tf_data.get("ml_score") or tf_data.get("ml_probability")
        if len(candles) < 50:
            return signals
        market_data = {"candles": candles, "indicators": indicators, "ml_probability": ml_prob}
        strategy_signals = signal_gen.generate_signals(asset, timeframe, market_data)
        threshold_raw = str(os.getenv("ML_REJECTION_THRESHOLD") or "").strip()
        ml_threshold = float(threshold_raw) if threshold_raw else None
        for sig in strategy_signals:
            is_dup = await dedup.is_duplicate(asset, timeframe, sig.direction, sig.entry)
            if is_dup:
                logger.debug("Duplicate signal skipped: %s %s %s", asset, timeframe, sig.direction)
                continue
            ml_prob_value = ml_prob
            if ml_prob_value is None and include_ml:
                try:
                    from engine.ml import score_signal as _score_signal
                    ml_prob_value = _score_signal({
                        "asset": asset,
                        "timeframe": timeframe,
                        "direction": sig.direction,
                        "entry": sig.entry,
                        "stop_loss": sig.stop_loss,
                        "take_profit": sig.take_profit,
                        "score": sig.score,
                        "strategy_name": sig.strategy_name,
                        "strategy_group": sig.strategy_group,
                        "confidence": sig.confidence,
                    })
                except Exception:
                    ml_prob_value = None
            if include_ml and ml_threshold is not None and ml_prob_value is not None and ml_prob_value < ml_threshold:
                await ml_tracker.persist_rejection(
                    asset=asset,
                    timeframe=timeframe,
                    direction=sig.direction,
                    entry_price=sig.entry,
                    stop_loss=sig.stop_loss,
                    take_profit_levels=sig.take_profit,
                    ml_probability=ml_prob_value,
                    rejection_reason="low_ml_score",
                    features=sig.ml_features,
                )
                await persist_decision_log(
                    None,
                    asset,
                    timeframe,
                    "rejected",
                    reason=f"ML score {ml_prob_value:.2f} < {ml_threshold:.2f}",
                    meta={"ml_probability": ml_prob_value, "ml_threshold": ml_threshold},
                )
                continue
            try:
                signal_data = {
                    "asset": asset,
                    "timeframe": timeframe,
                    "direction": sig.direction,
                    "entry": sig.entry,
                    "stop_loss": sig.stop_loss,
                    "take_profit": sig.take_profit,
                    "score": sig.score,
                    "strategy_name": sig.strategy_name,
                    "strategy_group": sig.strategy_group,
                    "ml_probability": ml_prob_value,
                    "confidence": sig.confidence,
                }
                signal_obj = await persist_signal(signal_data)
                if signal_obj:
                    signals.append(signal_obj)
                    await dedup.register_signal(asset, timeframe, sig.direction, sig.entry)
                    await persist_decision_log(
                        signal_obj.signal_id,
                        asset,
                        timeframe,
                        "issued",
                        reason=f"{sig.strategy_name} ({sig.score:.0f})",
                        meta={"strategy_group": sig.strategy_group},
                    )
            except Exception as e:
                logger.error("Failed to persist signal: %s", e)
    except Exception as e:
        logger.error("Error processing %s %s: %s", asset, timeframe, e)
        await persist_decision_log(None, asset, timeframe, "error", reason=str(e)[:100], meta={})
    return signals


async def run_once(assets: Iterable[str], timeframes: Iterable[str], include_ml: bool = False) -> Dict[str, List]:
    """Run one cycle across assets and strategies with bounded concurrency."""
    max_concurrency = max(1, int(os.getenv("ENGINE_MAX_CONCURRENCY", "8")))
    timeout_seconds = max(5, int(os.getenv("ENGINE_TASK_TIMEOUT_SECONDS", "45")))
    retries = max(0, int(os.getenv("ENGINE_TASK_RETRIES", "3")))
    sem = asyncio.Semaphore(max_concurrency)
    results: Dict[str, List] = {str(a): [] for a in assets}

    async def _run_task(asset: str, timeframe: str) -> list:
        async with sem:
            for attempt in range(retries + 1):
                started = time.perf_counter()
                try:
                    out = await asyncio.wait_for(
                        _process_asset_timeframe(asset, timeframe, include_ml=include_ml),
                        timeout=timeout_seconds,
                    )
                    elapsed = (time.perf_counter() - started) * 1000.0
                    logger.info(
                        "engine task completed asset=%s timeframe=%s latency_ms=%.1f attempt=%s",
                        asset,
                        timeframe,
                        elapsed,
                        attempt + 1,
                    )
                    return out
                except asyncio.TimeoutError:
                    logger.warning(
                        "engine task timeout asset=%s timeframe=%s timeout=%ss attempt=%s",
                        asset,
                        timeframe,
                        timeout_seconds,
                        attempt + 1,
                    )
                except Exception as exc:
                    logger.warning(
                        "engine task failed asset=%s timeframe=%s attempt=%s err=%s",
                        asset,
                        timeframe,
                        attempt + 1,
                        exc,
                    )
                await asyncio.sleep(min(2**attempt, 30))
        return []

    tasks: list[tuple[str, asyncio.Task]] = []
    for asset in assets:
        for timeframe in timeframes:
            tasks.append((str(asset), asyncio.create_task(_run_task(str(asset), str(timeframe)))))

    for asset, task in tasks:
        out = await task
        if out:
            results[asset].extend(out)
    return results


async def main_loop(assets: Iterable[str], timeframes: Iterable[str], include_ml: bool = False, interval_seconds: int = 120):
    logger.info("engine loop starting assets=%s tf=%s interval=%s", assets, timeframes, interval_seconds)
    
    # Start signal monitor
    try:
        from engine.signal_monitor import start_signal_monitor
        await start_signal_monitor()
        logger.info("Signal monitor started alongside main loop")
    except Exception as e:
        logger.error(f"Failed to start signal monitor: {e}")
    
    while True:
        try:
            res = await run_once(assets, timeframes, include_ml=include_ml)
            total_signals = sum(len(v) for v in res.values())
            logger.info(f"engine cycle completed: {total_signals} signals generated")
            
            # Track ML rejection outcomes
            try:
                tracked = await ml_tracker.track_rejection_outcomes()
                if tracked > 0:
                    logger.info(f"Tracked {tracked} ML rejection outcomes")
            except Exception as e:
                logger.warning(f"ML outcome tracking failed: {e}")
        
        except Exception:
            logger.exception("engine main loop failed")
        
        await asyncio.sleep(interval_seconds)


def start_engine_loop(assets: Iterable[str], timeframes: Iterable[str], include_ml: bool = False, interval_seconds: int = 120):
    """Sync entrypoint to run the async main loop using `run_sync` shim."""
    return run_sync(main_loop(assets, timeframes, include_ml=include_ml, interval_seconds=interval_seconds))


def demo_start():
    assets = (os.getenv("DEMO_ASSETS") or "XAUUSD").split(",")
    timeframes = (os.getenv("DEMO_TIMEFRAMES") or "1h,1d").split(",")
    start_engine_loop(assets, timeframes, include_ml=False, interval_seconds=60)


if __name__ == "__main__":
    demo_start()
