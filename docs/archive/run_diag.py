#!/usr/bin/env python3
"""
Diagnostic script to test the full engine pipeline and identify where signals are failing.
"""
import asyncio
import logging
import os
import sys

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(name)s [%(levelname)s] %(message)s',
    stream=sys.stdout
)
logger = logging.getLogger(__name__)

# Set test environment
os.environ.setdefault("TRADINGVIEW_ENABLED", "false")
os.environ.setdefault("USE_FALLBACK_STRATEGIES", "true")
os.environ.setdefault("RUN_ALL_STRATEGIES", "true")
os.environ.setdefault("IMP_STRATEGY_ENABLED", "true")


async def run_full_diagnostic():
    """Test the full pipeline for one asset."""
    
    # Import after env vars set
    from data.fetcher import is_crypto
    from data.market_data import fetch_market_data_cached
    from data.indicators import calculate_indicators
    from engine.regime import detect_market_regime
    from strategies import run_all_strategies
    
    # Test with BTCUSDT
    asset = "BTCUSDT"
    tfs = ["1h", "4h"]
    
    logger.info("=" * 60)
    logger.info(f"DIAGNOSTIC: Testing full pipeline for {asset}")
    logger.info("=" * 60)
    
    # Step 1: Data fetch
    logger.info("[STEP 1] Fetching market data...")
    market_data = await fetch_market_data_cached(asset, tfs)
    
    if not market_data:
        logger.error("[STEP 1 FAILED] No market data returned!")
        return
    
    logger.info(f"[STEP 1 OK] Got data for timeframes: {list(market_data.keys())}")
    
    # Step 2: Check data structure
    logger.info("[STEP 2] Checking data structure...")
    for tf_name, tf_data in market_data.items():
        candles = tf_data.get("candles", []) if isinstance(tf_data, dict) else []
        inds = tf_data.get("indicators", {}) if isinstance(tf_data, dict) else {}
        
        logger.info(f"  {tf_name}: candles={len(candles)}, indicators={len(inds)}")
        
        if not candles:
            logger.warning(f"    WARNING: No candles for {tf_name}!")
        
        if inds:
            # Check key indicators exist
            required = ["rsi", "ema_fast", "ema_slow", "sma_20"]
            missing = [k for k in required if k not in inds or inds[k] is None]
            if missing:
                logger.warning(f"    WARNING: Missing indicators: {missing}")
        elif candles:
            # Calculate indicators if missing
            logger.info(f"    Calculating indicators...")
            inds = calculate_indicators(candles)
            tf_data["indicators"] = inds
            logger.info(f"    Calculated: {list(inds.keys())[:10]}")
    
    # Step 3: Regime detection
    logger.info("[STEP 3] Detecting market regime...")
    regime = detect_market_regime(market_data)
    logger.info(f"[STEP 3 OK] Regime: {regime}")
    
    # Step 4: Run strategies
    logger.info("[STEP 4] Running strategies...")
    signals = run_all_strategies(asset, market_data, regime)
    
    logger.info(f"[STEP 4 RESULT] Signals returned: {len(signals)}")
    
    if not signals:
        logger.error("[STEP 4 FAILED] NO SIGNALS GENERATED!")
        logger.error("This is why the engine reports generated_signals=0")
        
        # Try to identify why
        logger.info("[DEBUG] Checking individual strategy groups...")
        
        # Check each timeframe for basic data
        for tf_name, tf_data in market_data.items():
            if not isinstance(tf_data, dict):
                continue
                
            candles = tf_data.get("candles", [])
            inds = tf_data.get("indicators", {})
            
            if not candles:
                logger.warning(f"  {tf_name}: NO CANDLES")
                continue
                
            if not inds:
                logger.warning(f"  {tf_name}: NO INDICATORS")
                continue
            
            # Check basic conditions for any signal
            close = candles[-1].get("close") if candles else None
            sma_20 = inds.get("sma_20")
            ema_fast = inds.get("ema_fast")
            ema_slow = inds.get("ema_slow")
            
            logger.info(f"  {tf_name}: close={close}, sma_20={sma_20}, ema_fast={ema_fast}, ema_slow={ema_slow}")
            
            # Simple signal check
            if close and ema_fast and ema_slow:
                if close > ema_fast > ema_slow:
                    logger.info(f"    -> Simple LONG condition met (price > ema_fast > ema_slow)")
                elif close < ema_fast < ema_slow:
                    logger.info(f"    -> Simple SHORT condition met (price < ema_fast < ema_slow)")
        
    else:
        logger.info("[STEP 4 OK] Signals generated:")
        for i, sig in enumerate(signals[:5]):
            logger.info(f"  Signal {i+1}: {sig.get('strategy_name')} {sig.get('direction')} conf={sig.get('confidence')}")
    
    logger.info("=" * 60)
    logger.info("DIAGNOSTIC COMPLETE")
    logger.info("=" * 60)
    
    return len(signals) > 0


if __name__ == "__main__":
    result = asyncio.run(run_full_diagnostic())
    sys.exit(0 if result else 1)
