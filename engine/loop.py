"""Engine loop: async runner that periodically runs strategies over assets."""
import asyncio
import logging
import os
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


async def run_once(assets: Iterable[str], timeframes: Iterable[str], include_ml: bool = False) -> Dict[str, List]:
    """Run one cycle across assets and strategies; returns mapping asset->signals."""
    results = {}
    
    for asset in assets:
        signals = []
        
        for timeframe in timeframes:
            try:
                # Get market data for this specific timeframe
                market_state = await get_market_state_async(asset, [timeframe], include_ml=include_ml)
                
                # Extract timeframe-specific data
                tf_data = market_state.get('timeframes', {}).get(timeframe)
                if not tf_data:
                    continue
                
                candles = tf_data.get('candles', [])
                indicators = tf_data.get('indicators', {})
                ml_prob = tf_data.get('ml_score', 0.7)
                
                if len(candles) < 50:
                    continue
                
                # Prepare market_data dict for signal generator
                market_data = {
                    'candles': candles,
                    'indicators': indicators,
                    'ml_probability': ml_prob,
                }
                
                # Generate signals from all 20 strategies
                strategy_signals = signal_gen.generate_signals(asset, timeframe, market_data)
                
                # Deduplication & ML filtering
                for sig in strategy_signals:
                    # Check for duplicates
                    is_dup = await dedup.is_duplicate(asset, timeframe, sig.direction, sig.entry)
                    if is_dup:
                        logger.debug(f"Duplicate signal skipped: {asset} {timeframe} {sig.direction}")
                        continue
                    
                    # Check ML score if enabled
                    if include_ml and ml_prob < 0.7:  # 70% threshold
                        await ml_tracker.persist_rejection(
                            asset=asset,
                            timeframe=timeframe,
                            direction=sig.direction,
                            entry_price=sig.entry,
                            stop_loss=sig.stop_loss,
                            take_profit_levels=sig.take_profit,
                            ml_probability=ml_prob,
                            rejection_reason="low_ml_score",
                            features=sig.ml_features
                        )
                        await persist_decision_log(
                            None, asset, timeframe, "rejected",
                            reason=f"ML score {ml_prob:.2f} < 0.70",
                            meta={'ml_probability': ml_prob}
                        )
                        continue
                    
                    # Persist signal
                    try:
                        signal_data = {
                            'asset': asset,
                            'timeframe': timeframe,
                            'direction': sig.direction,
                            'entry': sig.entry,
                            'stop_loss': sig.stop_loss,
                            'take_profit': sig.take_profit,
                            'score': sig.score,
                            'strategy_name': sig.strategy_name,
                            'strategy_group': sig.strategy_group,
                            'ml_probability': ml_prob,
                            'confidence': sig.confidence,
                        }
                        signal_obj = await persist_signal(signal_data)
                        if signal_obj:
                            signals.append(signal_obj)
                            await dedup.register_signal(asset, timeframe, sig.direction, sig.entry)
                            await persist_decision_log(
                                signal_obj.signal_id, asset, timeframe, "issued",
                                reason=f"{sig.strategy_name} ({sig.score:.0f})",
                                meta={'strategy_group': sig.strategy_group}
                            )
                    except Exception as e:
                        logger.error(f"Failed to persist signal: {e}")
                
            except Exception as e:
                logger.error(f"Error processing {asset} {timeframe}: {e}")
                await persist_decision_log(
                    None, asset, timeframe, "error",
                    reason=str(e)[:100],
                    meta={}
                )
        
        results[asset] = signals
    
    return results


async def main_loop(assets: Iterable[str], timeframes: Iterable[str], include_ml: bool = False, interval_seconds: int = 300):
    logger.info("engine loop starting assets=%s tf=%s interval=%s", assets, timeframes, interval_seconds)
    
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


def start_engine_loop(assets: Iterable[str], timeframes: Iterable[str], include_ml: bool = False, interval_seconds: int = 300):
    """Sync entrypoint to run the async main loop using `run_sync` shim."""
    return run_sync(main_loop(assets, timeframes, include_ml=include_ml, interval_seconds=interval_seconds))


def demo_start():
    assets = (os.getenv("DEMO_ASSETS") or "XAUUSD").split(",")
    timeframes = (os.getenv("DEMO_TIMEFRAMES") or "1h,1d").split(",")
    start_engine_loop(assets, timeframes, include_ml=False, interval_seconds=60)


if __name__ == "__main__":
    demo_start()
