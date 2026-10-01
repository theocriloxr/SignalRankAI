#!/usr/bin/env python3
"""Quick diagnostic to check indicator types."""
import asyncio
import os
import logging

logging.basicConfig(level=logging.INFO, format='%(name)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

os.environ.setdefault("TRADINGVIEW_ENABLED", "false")
os.environ.setdefault("USE_FALLBACK_STRATEGIES", "true")

async def main():
    from data.market_data import fetch_market_data_cached
    from data.indicators import calculate_indicators
    
    asset = "BTCUSDT"
    tfs = ["1h", "4h"]
    
    logger.info(f"Fetching data for {asset}")
    data = await fetch_market_data_cached(asset, tfs)
    
    if not data:
        logger.error("No data returned")
        return
    
    for tf, tf_data in data.items():
        inds = tf_data.get("indicators", {}) if isinstance(tf_data, dict) else {}
        if inds:
            logger.info(f"\n{tf} indicator types:")
            for key in ["atr", "ema_fast", "ema_slow", "macd", "macd_hist", "rsi", "sma_20", "sma_50"]:
                val = inds.get(key)
                if val is not None:
                    logger.info(f"  {key}: {type(val).__name__} = {str(val)[:60]}")
    
    # Now test signal scoring
    regime = "TRENDING"
    from strategies import run_all_strategies
    
    signals = run_all_strategies(asset, data, regime)
    logger.info(f"Generated {len(signals)} signals")
    
    for sig in signals[:5]:
        logger.info(f"  {sig.get('strategy_name')}: dir={sig.get('direction')}")
    
# Test scoring
    from engine.scoring import score_signal
    for sig in signals[:5]:
        name = sig.get('strategy_name')
        logger.info(f"\n=== {name} ===")
        # Check key fields
        for k in ['entry', 'stop', 'stop_loss', 'targets', 'take_profit', 'confidence']:
            v = sig.get(k)
            logger.info(f"  {k}: {type(v).__name__} = {str(v)[:60]}")
        
        try:
            score = score_signal(sig)
            logger.info(f"  Score: {score}")
        except Exception as e:
            logger.error(f"  ERROR: {type(e).__name__}: {e}")
            # Add more detail
            import traceback
            traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())
