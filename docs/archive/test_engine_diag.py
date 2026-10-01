#!/usr/bin/env python3
"""Quick diagnostic test to verify engine diagnostic logging."""

import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.INFO, format='%(message)s')
    
    print("=" * 60)
    print("DIAGNOSTIC TEST: Engine Market Data Check")
    print("=" * 60)
    
    # Simulate what the engine logs when processing an asset
    market_data = {'1h': {'candles': [], 'indicators': {}}}
    
    # Test case 1: Empty market data (what causes strategy_signals=0)
    print("\n[TEST 1] Empty market_data")
    _tf_count = len(market_data) if isinstance(market_data, dict) else 0
    _candle_counts = {}
    _indicator_counts = {}
    for _tf, _tf_data in (market_data or {}).items():
        if isinstance(_tf_data, dict):
            _candles = _tf_data.get('candles') or []
            _inds = _tf_data.get('indicators') or {}
            _candle_counts[_tf] = len(_candles) if isinstance(_candles, list) else 0
            _indicator_counts[_tf] = len(_inds) if isinstance(_inds, dict) else 0
    
    print(f"  [engine][DIAGNOSTIC] market_data_check asset=BTCUSDT tfs={_tf_count} "
          f"candle_counts={_candle_counts} indicator_counts={_indicator_counts}")
    print(f"  Result: Would SKIP asset due to no candles!")
    
    # Test case 2: Valid market data
    print("\n[TEST 2] Valid market_data")
    market_data_2 = {
        '1h': {
            'candles': [{'close': 50000, 'open': 49000, 'high': 51000, 'low': 48000}] * 100,
            'indicators': {'rsi': 55, 'ema_fast': 50000}
        }
    }
    
    _tf_count = len(market_data_2) if isinstance(market_data_2, dict) else 0
    _candle_counts = {}
    _indicator_counts = {}
    for _tf, _tf_data in (market_data_2 or {}).items():
        if isinstance(_tf_data, dict):
            _candles = _tf_data.get('candles') or []
            _inds = _tf_data.get('indicators') or {}
            _candle_counts[_tf] = len(_candles) if isinstance(_candles, list) else 0
            _indicator_counts[_tf] = len(_inds) if isinstance(_inds, dict) else 0
    
    print(f"  [engine][DIAGNOSTIC] market_data_check asset=BTCUSDT tfs={_tf_count} "
          f"candle_counts={_candle_counts} indicator_counts={_indicator_counts}")
    print(f"  Result: Would CONTINUE with strategies!")
    
    print("\n" + "=" * 60)
    print("DIAGNOSTIC TEST COMPLETE")
    print("=" * 60)
    print("\nTo debug why strategy_signals=0 in production:")
    print("1. Look for '[engine][DIAGNOSTIC] market_data_check' in logs")
    print("2. If candle_counts={} or indicator_counts={} -> data provider issue")
    print("3. Check '[fetcher]' logs to see which providers succeeded")
    print("4. Check '[strategies]' logs to see strategy output")
