#!/usr/bin/env python3
"""Quick diagnostic to test strategy signal generation."""
import asyncio
import logging
import os

logging.basicConfig(
    level=logging.INFO,
    format='%(name)s [%(levelname)s] %(message)s'
)
logger = logging.getLogger(__name__)

# Set minimal env for testing
os.environ.setdefault("TRADINGVIEW_ENABLED", "false")
os.environ.setdefault("USE_FALLBACK_STRATEGIES", "true")


async def test_signal_generation():
    from data.fetcher import is_crypto
    from data.market_data import fetch_market_data_cached
    from data.indicators import calculate_indicators
    from strategies import run_all_strategies
    from engine.regime import detect_market_regime

    # Test with BTCUSDT 
    asset = "BTCUSDT"
    tfs = ["1h", "4h"]

    logger.info(f"Testing signal generation for {asset}")
    logger.info(f"is_crypto: {is_crypto(asset)}")

    # Fetch data
    logger.info(f"Fetching market data for {asset}...")
    data = await fetch_market_data_cached(asset, tfs)

    if not data:
        logger.error(f"No data returned for {asset}")
        return

    logger.info(f"Market data keys: {list(data.keys())}")
    
    for tf, tf_data in data.items():
        if not isinstance(tf_data, dict):
            logger.warning(f"  {tf}: not a dict, skipping")
            continue
            
        candles = tf_data.get("candles", [])
        inds = tf_data.get("indicators", {})
        
        logger.info(f"  {tf}: candles={len(candles)}, indicators={len(inds) if inds else 0}")
        
        if inds:
            # Check key indicators
            rsi = inds.get("rsi", "N/A")
            ema_fast = inds.get("ema_fast", "N/A")
            ema_slow = inds.get("ema_slow", "N/A")
            macd = inds.get("macd", "N/A")
            logger.info(f"    RSI: {rsi}, EMA_fast: {ema_fast}, EMA_slow: {ema_slow}, MACD: {macd}")
        elif candles:
            # Calculate indicators if missing
            logger.info(f"    Calculating indicators...")
            inds = calculate_indicators(candles)
            tf_data["indicators"] = inds
            logger.info(f"    Calculated indicators: {list(inds.keys())[:10]}")

    regime = detect_market_regime(data)
    logger.info(f"Detected regime: {regime}")

    # Run strategies
    logger.info(f"Running strategies...")
    signals = run_all_strategies(asset, data, regime)
    logger.info(f"Total signals returned: {len(signals)}")

    for i, sig in enumerate(signals[:5]):
        logger.info(f"  Signal {i+1}: strategy={sig.get('strategy_name')}, dir={sig.get('direction')}, conf={sig.get('confidence')}")
    
    if not signals:
        logger.warning(f"NO SIGNALS GENERATED for {asset}!")
        logger.warning(f"This explains why the engine reports generated_signals=0")


if __name__ == "__main__":
    asyncio.run(test_signal_generation())
