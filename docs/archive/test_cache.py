#!/usr/bin/env python3
"""Diagnostic test - check cache and force fresh fetch."""
import sys
import os
import time
sys.path.insert(0, '.')

# Force short cache to ensure fresh data
os.environ['CANDLE_REQUEST_CACHE_TTL_SECONDS'] = '0.1'

print('Starting...')
try:
    from data.fetcher import get_candles, _read_cached_candles, _CANDLE_CACHE
    
    asset = 'BTCUSDT'
    timeframe = '1h'
    
    # Clear cache first
    print(f'Cache before: {len(_CANDLE_CACHE)} entries')
    
    print(f'Fetching {asset} {timeframe} with short cache TTL...')
    candles = get_candles(asset, timeframe)
    print(f'Got {len(candles)} candles')
    
    if candles:
        print(f'First timestamp: {candles[0].get("timestamp")}')
        print(f'Last close: {candles[-1].get("close")}')
        
        # Check indicators
        from data.indicators import calculate_indicators
        ind = calculate_indicators(candles)
        print(f'Indicators: RSI={ind.get("rsi")}, EMA_fast={ind.get("ema_fast")}, Close={ind.get("close_price")}')
    else:
        print('ERROR: No candles!')
        
except Exception as e:
    import traceback
    print(f'Error: {type(e).__name__}: {e}')
    traceback.print_exc()
