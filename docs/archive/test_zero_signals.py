#!/usr/bin/env python3
"""
Diagnostic test for zero signal generation.
Tests the signal pipeline to find where signals=0.
"""

import sys
import os
import logging

# Setup path
sys.path.insert(0, os.path.dirname(__file__))
logging.basicConfig(level=logging.INFO, format='%(name)s %(levelname)s: %(message)s')
logger = logging.getLogger(__name__)


def test_fallback_strategies():
    """Test fallback strategies directly."""
    from strategies.fallback import fallback_strategies
    
    # Create mock market data
    candles = [
        {'open': 50000 + i*10, 'high': 50100 + i*10, 'low': 49900 + i*10, 'close': 50050 + i*10, 'volume': 1000000}
        for i in range(30)
    ]
    
    indicators = {
        'close_price': 50050,
        'ema_fast': 50000,
        'ema_slow': 49900,
        'sma_20': 50000,
        'rsi': 55,
        'volume_ratio': 1.2,
        'volume': 1000000,
        'volume_avg': 900000,
        'regime': 'trending'
    }
    
    market_data = {'candles': candles, 'indicators': indicators}
    
    # Test fallback strategies
    sigs = fallback_strategies('BTCUSDT', '1h', market_data)
    print(f'[test_fallback] Returned {len(sigs)} signals')
    for s in sigs[:3]:
        print(f'  - direction={s.get("direction")} entry={s.get("entry")} conf={s.get("confidence")}')
    
    return len(sigs) > 0


def test_run_all_strategies():
    """Test run_all_strategies function."""
    from strategies import run_all_strategies
    
    # Create mock market data with indicators
    candles = [
        {'open': 50000 + i*10, 'high': 50100 + i*10, 'low': 49900 + i*10, 'close': 50050 + i*10, 'volume': 1000000, 'timestamp': i}
        for i in range(60)
    ]
    
    indicators = {
        'close_price': 50050,
        'ema_fast': 50000,
        'ema_slow': 49900,
        'sma_20': 50000,
        'sma_50': 49800,
        'rsi': 55,
        'volume_ratio': 1.2,
        'volume': 1000000,
        'volume_avg': 900000,
        'regime': 'trending',
        'trend_ema': 1,
        'macd_trend': 1,
        'atr': 100,
    }
    
    market_data = {
        '1h': {'candles': candles, 'indicators': indicators}
    }
    
    # Test run_all_strategies
    sigs = run_all_strategies('BTCUSDT', market_data, 'trending')
    print(f'[test_run_all] Returned {len(sigs)} signals')
    
    if not sigs:
        print('[test_run_all] WARNING: No signals generated!')
        # Debug: check what's in market_data
        for tf, data in market_data.items():
            ind = data.get('indicators', {})
            print(f'  TF={tf}: candles={len(data.get("candles", []))}, indicators={len(ind)}')
            if ind:
                print(f'    ema_fast={ind.get("ema_fast")}, ema_slow={ind.get("ema_slow")}, rsi={ind.get("rsi")}')
                print(f'    sma_20={ind.get("sma_20")}, regime={ind.get("regime")}')
    
    for s in sigs[:3]:
        print(f'  - {s.get("strategy_name")} dir={s.get("direction")} conf={s.get("confidence")}')
    
    return len(sigs) > 0


def test_indicators_calculation():
    """Test indicator calculation."""
    from data.indicators import calculate_indicators
    
    candles = [
        {'open': 50000 + i*10, 'high': 50100 + i*10, 'low': 49900 + i*10, 'close': 50050 + i*10, 'volume': 1000000}
        for i in range(60)
    ]
    
    indicators = calculate_indicators(candles)
    print(f'[test_indicators] Calculated {len(indicators)} indicators')
    print(f'  ema_fast={indicators.get("ema_fast")}, ema_slow={indicators.get("ema_slow")}')
    print(f'  rsi={indicators.get("rsi")}, sma_20={indicators.get("sma_20")}')
    print(f'  regime={indicators.get("regime")}')
    
    return len(indicators) > 0


if __name__ == '__main__':
    print('='* 60)
    print('DIAGNOSTIC: Testing signal generation pipeline')
    print('='* 60)
    
    results = []
    
    # Test 1: Indicators calculation
    print('\n--- Test 1: Indicators Calculation ---')
    results.append(('indicators', test_indicators_calculation()))
    
    # Test 2: Fallback strategies
    print('\n--- Test 2: Fallback Strategies ---')
    results.append(('fallback', test_fallback_strategies()))
    
    # Test 3: run_all_strategies
    print('\n--- Test 3: run_all_strategies ---')
    results.append(('run_all', test_run_all_strategies()))
    
    # Summary
    print('\n' + '='*60)
    print('SUMMARY:')
    for name, passed in results:
        status = 'PASS' if passed else 'FAIL'
        print(f'  {name}: {status}')
    
    if all(r[1] for r in results):
        print('\nAll tests passed - pipeline is working!')
        sys.exit(0)
    else:
        print('\nSome tests FAILED - this explains zero signal generation')
        sys.exit(1)
