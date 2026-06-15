#!/usr/bin/env python3
"""Diagnostic test - check strategy signals."""
import sys
import os
sys.path.insert(0, '.')

# Force short cache
os.environ['CANDLE_REQUEST_CACHE_TTL_SECONDS'] = '0.1'

print('=== Strategy Signal Test ===')
try:
    from data.fetcher import get_candles
    
    asset = 'BTCUSDT'
    timeframe = '1h'
    
    print(f'Fetching {asset} {timeframe}...')
    candles = get_candles(asset, timeframe)
    print(f'Got {len(candles)} candles')
    
    if not candles:
        print('ERROR: No candles!')
        sys.exit(1)
    
    # Build market_data as engine does
    from data.indicators import calculate_indicators
    indicators = calculate_indicators(candles)
    
    market_data = {
        timeframe: {
            'candles': candles,
            'indicators': indicators,
        }
    }
    
    regime = 'TRENDING'  # Test regime
    print(f'Indicators: RSI={indicators.get("rsi")}, EMA_fast={indicators.get("ema_fast")}, EMA_slow={indicators.get("ema_slow")}')
    
    # Test IMP strategy (the primary one)
    print(f'\nRunning IMP strategy for {asset}...')
    from strategies.imp import institutional_momentum_pulse_strategies
    imp_signals = list(institutional_momentum_pulse_strategies(asset, market_data))
    print(f'IMP signals: {len(imp_signals)}')
    if imp_signals:
        for sig in imp_signals[:3]:
            print(f'  - {sig.get("strategy_name")}: dir={sig.get("direction")} conf={sig.get("confidence")}')
    
    # Test trend strategies  
    print(f'\nRunning trend strategies for {asset}...')
    from strategies.trend import trend_strategies
    trend_signals = list(trend_strategies(asset, timeframe, market_data[timeframe]))
    print(f'Trend signals: {len(trend_signals)}')
    if trend_signals:
        for sig in trend_signals[:3]:
            print(f'  - {sig.get("strategy_name")}: dir={sig.get("direction")} conf={sig.get("confidence")}')
    
    # Test run_all_strategies  
    print(f'\nRunning run_all_strategies for {asset}...')
    from strategies import run_all_strategies
    all_signals = run_all_strategies(asset, market_data, regime)
    print(f'All signals: {len(all_signals)}')
    if all_signals:
        for sig in all_signals[:5]:
            print(f'  - {sig.get("strategy_name")}: dir={sig.get("direction")}')
    else:
        print('WARNING: No signals generated!')
        
except Exception as e:
    import traceback
    print(f'Error: {type(e).__name__}: {e}')
    traceback.print_exc()
