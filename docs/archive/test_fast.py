#!/usr/bin/env python3
"""Quick diagnostic test - minimal."""
import sys
import os
sys.path.insert(0, '.')

# Force timeout on requests
os.environ['CANDLE_REQUEST_TIMEOUT_SECONDS'] = '3'

print('Starting...')
try:
    from data.fetcher import _fetch_crypto_multi_provider
    print('Fetching BTCUSDT 1h...')
    import requests
    url = "https://api.binance.com/api/v3/klines"
    params = {"symbol": "BTCUSDT", "interval": "1h", "limit": 10}
    resp = requests.get(url, params=params, timeout=3)
    print(f'HTTP {resp.status_code}')
    if resp.status_code == 200:
        data = resp.json()
        print(f'Got {len(data) if isinstance(data, list) else 0} klines')
except Exception as e:
    print(f'Error: {type(e).__name__}: {e}')
