#!/usr/bin/env python3
"""
Focused diagnostic to identify where strategy pipeline breaks.
Run this to identify exactly which stage returns empty.
"""
import asyncio
import os
import sys

# Minimal setup
os.environ.setdefault("TRADINGVIEW_ENABLED", "false")
os.environ.setdefault("USE_FALLBACK_STRATEGIES", "true")
os.environ.setdefault("RUN_ALL_STRATEGIES", "true")
os.environ.setdefault("IMP_STRATEGY_ENABLED", "true")
os.environ["PYTHONUNBUFFERED"] = "1"


async def test_pipeline():
    """Test each pipeline stage separately."""
    
    print("\n" + "=" * 60)
    print("ZERO SIGNALS DIAGNOSTIC")
    print("=" * 60 + "\n")
    
    asset = "BTCUSDT"
    tfs = ["1h", "4h"]
    
    # STAGE 1: Data Fetch
    print("[STAGE 1] Fetching market data...")
    try:
        from data.market_data import fetch_market_data_cached
        market_data = await fetch_market_data_cached(asset, tfs)
        
        if not market_data:
            print("  FAIL: No market data returned")
            return
            
        for tf, data in market_data.items():
            candles = data.get("candles", []) if isinstance(data, dict) else []
            inds = data.get("indicators", {}) if isinstance(data, dict) else {}
            print(f"  {tf}: candles={len(candles)}, indicators={len(inds)}")
            
            if candles and not inds:
                print(f"    -> Indicators MISSING, calculating...")
                from data.indicators import calculate_indicators
                inds = calculate_indicators(candles)
                data["indicators"] = inds
                print(f"    -> Calculated {len(inds)} indicators")
                
    except Exception as e:
        print(f"  FAIL: {e}")
        return
        
    # STAGE 2: Regime Detection
    print("\n[STAGE 2] Detecting regime...")
    try:
        from engine.regime import detect_market_regime
        regime = detect_market_regime(market_data)
        print(f"  Regime: {regime}")
    except Exception as e:
        print(f"  FAIL: {e}")
        regime = None
        
    # STAGE 3: Strategy Groups (test each separately)
    print("\n[STAGE 3] Testing strategy groups...")
    
    from strategies import (
        trend_strategies, momentum_strategies, volatility_strategies,
        structure_strategy, liquidity_sweep_strategies, fibonacci_confluence_strategies,
        fallback_strategies, institutional_momentum_pulse_strategies
    )
    
    # Get first timeframe data
    tf = list(market_data.keys())[0] if market_data else "1h"
    data = market_data.get(tf, {})
    candles = data.get("candles", [])
    
    print(f"  Testing with tf={tf}, {len(candles)} candles")
    
    # Test each strategy group
    strategy_groups = {
        "trend": trend_strategies,
        "momentum": momentum_strategies,
        "volatility": volatility_strategies,
        "structure": structure_strategy,
        "liquidity": liquidity_sweep_strategies,
        "fibonacci": fibonacci_confluence_strategies,
        "imp": institutional_momentum_pulse_strategies,
        "fallback": fallback_strategies,
    }
    
    total_signals = 0
    for name, strategy_fn in strategy_groups.items():
        try:
            sigs = strategy_fn(asset, tf, data) if name != "liquidity" else strategy_fn(asset, market_data)
            print(f"    {name}: {len(sigs)} signals")
            total_signals += len(sigs)
        except Exception as e:
            print(f"    {name}: ERROR - {e}")
            
    # STAGE 4: run_all_strategies()
    print("\n[STAGE 4] Testing run_all_strategies()...")
    try:
        from strategies import run_all_strategies
        signals = run_all_strategies(asset, market_data, regime)
        print(f"  Total signals: {len(signals)}")
        
        if signals:
            for s in signals[:3]:
                print(f"    - {s.get('strategy_name')}: {s.get('direction')}")
        else:
            print("  NO SIGNALS - This is why engine reports zero signals!")
            
    except Exception as e:
        print(f"  FAIL: {e}")
        
    print("\n" + "=" * 60)
    print(f"RESULT: {total_signals} signals from individual groups")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    asyncio.run(test_pipeline())
