#!/usr/bin/env python3
"""Quick diagnostic test for data fetching and indicators."""
import sys
sys.path.insert(0, '.')

from data.fetcher import get_candles

# Test fetching candles for a sample crypto asset
asset = 'BTCUSDT'
timeframe = '1h'

print(f'Testing data fetch for {asset} {timeframe}...')
candles = get_candles(asset, timeframe)
print(f'Got {len(candles) if candles else 0} candles')

if candles:
    print(f'First candle timestamp: {candles[0].get("timestamp")}')
    print(f'Last candle: close={candles[-1].get("close")}')
    
    # Test indicators
    from data.indicators import calculate_indicators
    indicators = calculate_indicators(candles)
    print(f'Indicators calculated: {len(indicators)}')
    print(f'RSI: {indicators.get("rsi")}')
    print(f'EMA fast: {indicators.get("ema_fast")}')
    print(f'Trend EMA: {indicators.get("trend_ema")}')
    print(f'Close price: {indicators.get("close_price")}')
else:
    print('ERROR: No candles returned!')
    sys.exit(1)
