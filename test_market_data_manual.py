#!/usr/bin/env python3
"""
Manual test for market data fetching.
Run this to diagnose why "No candles found" occurs.

Usage:
    python test_market_data_manual.py BTCUSDT 1h
    python test_market_data_manual.py ETHUSDT 1h
    python test_market_data_manual.py AAVEUSDT 1h
"""
import os
import sys
import time

# Add project to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Force debug mode
os.environ["DEBUG_MARKET_DATA"] = "true"
os.environ["USE_MULTI_PROVIDER_DATA"] = "true"
os.environ["YFINANCE_ENABLED"] = "true"

def test_single(asset: str, timeframe: str = "1h"):
    """Test fetching candles for a single asset."""
    from data.fetcher import get_candles, _get_provider_errors
    
    print(f"\n{'='*60}")
    print(f"Testing: {asset} {timeframe}")
    print(f"{'='*60}")
    
    start = time.time()
    candles = get_candles(asset, timeframe)
    elapsed = time.time() - start
    
    print(f"\nResult:")
    print(f"  - Candles returned: {len(candles) if candles else 0}")
    print(f"  - Time elapsed: {elapsed:.2f}s")
    
    if candles:
        print(f"  - First candle: {candles[0]}")
        print(f"  - Last candle: {candles[-1]}")
    else:
        print(f"  - NO CANDLES RETURNED!")
        
    # Get any tracked errors
    errors = _get_provider_errors(asset, timeframe)
    if errors:
        print(f"\n  - Tracked errors: {errors}")
    
    # Check what provider was used
    from data.fetcher import _get_last_provider_used
    provider = _get_last_provider_used(asset, timeframe)
    print(f"  - Provider used: {provider}")
    
    return len(candles) > 0


def test_all_providers(asset: str, timeframe: str = "1h"):
    """Test individual providers."""
    import requests
    from data.connectors.binance_adapter import get_candles as binance_get
    from data.connectors.yfinance_adapter import get_candles as yf_get
    
    print(f"\nTesting individual providers for {asset} {timeframe}:")
    
    providers = [
        ("binance", lambda: binance_get(asset, timeframe, limit=50)),
        ("yfinance", lambda: yf_get(asset, timeframe, limit=50)),
    ]
    
    for name, fetch_fn in providers:
        try:
            start = time.time()
            result = fetch_fn()
            elapsed = time.time() - start
            count = len(result) if result else 0
            print(f"  - {name}: {count} candles in {elapsed:.2f}s")
            if result:
                print(f"      First: {result[0].get('close')}, Last: {result[-1].get('close')}")
        except Exception as e:
            print(f"  - {name}: ERROR - {e}")


def test_binance_direct():
    """Test Binance API directly."""
    import requests
    
    symbol = "BTCUSDT"
    interval = "1h"
    
    url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval={interval}&limit=5"
    print(f"\nTesting Binance directly: {url}")
    
    try:
        resp = requests.get(url, timeout=10)
        print(f"  Status: {resp.status_code}")
        
        if resp.status_code == 200:
            data = resp.json()
            print(f"  Candles: {len(data)}")
            if data:
                print(f"  First: {data[0][1:5]}")  # open, high, low, close
        else:
            print(f"  Error: {resp.text[:200]}")
    except Exception as e:
        print(f"  Exception: {e}")


if __name__ == "__main__":
    asset = sys.argv[1] if len(sys.argv) > 1 else "BTCUSDT"
    tf = sys.argv[2] if len(sys.argv) > 2 else "1h"
    
    # Test Binance directly first
    test_binance_direct()
    
    # Test the full pipeline
    has_data = test_single(asset, tf)
    
    if not has_data:
        # Try individual providers
        test_all_providers(asset, tf)
    
    # Summary
    print(f"\n{'='*60}")
    if has_data:
        print("✓ Market data is WORKING")
    else:
        print("✗ Market data is NOT WORKING - check logs above for errors")
    print(f"{'='*60}\n")
