#!/usr/bin/env python3
"""Production simulation test - simulate engine loop conditions."""
import sys
import os
sys.path.insert(0, '.')

# Force short cache
os.environ['CANDLE_REQUEST_CACHE_TTL_SECONDS'] = '0.1'

print('=== Production Simulation Test ===')
try:
    from data.fetcher import get_candles
    from data.indicators import calculate_indicators
    
    # Simulate production asset list
    assets = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'XRPUSDT', 'ADAUSDT',
              'EURUSD', 'GBPUSD', 'USDJPY', 'AUDUSD', 'USDCAD',
              'AAPL', 'MSFT', 'GOOGL', 'AMZN', 'NVDA',
              'XAUUSD', 'XAGUSD']
    
    timeframe = '1h'
    regime = 'TRENDING'
    
    signals_total = 0
    assets_with_data = 0
    assets_with_signals = 0
    
    for asset in assets:
        # Check if market is open
        from data.fetcher import market_closed_reason
        closed = market_closed_reason(asset)
        if closed:
            print(f'SKIP {asset}: {closed}')
            continue
        
        # Fetch data (simulating engine's fetch)
        candles = get_candles(asset, timeframe)
        
        if not candles or len(candles) < 10:
            print(f'SKIP {asset}: insufficient candles ({len(candles) if candles else 0})')
            continue
        
        assets_with_data += 1
        
        # Build market_data as engine does
        indicators = calculate_indicators(candles)
        market_data = {timeframe: {'candles': candles, 'indicators': indicators}}
        
        # Run strategies (imported fresh each time mimics engine behavior)
        from strategies import run_all_strategies
        signals = run_all_strategies(asset, market_data, regime)
        
        if signals:
            signals_total += len(signals)
            assets_with_signals += 1
            print(f'OK {asset}: {len(signals)} signals')
        else:
            print(f'EMPTY {asset}: no strategy signals')
    
    print(f'\n=== Summary ===')
    print(f'Assets processed: {assets_with_data}/{len(assets)}')
    print(f'Assets with signals: {assets_with_signals}')
    print(f'Total signals: {signals_total}')
    
    if signals_total == 0:
        print('\n*** ZERO SIGNALS - Same as production! ***')
        
except Exception as e:
    import traceback
    print(f'Error: {type(e).__name__}: {e}')
    traceback.print_exc()
