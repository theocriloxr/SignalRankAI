import os
from .indicators import calculate_indicators
import pandas as pd
import time
import os
from .indicators import calculate_indicators
import pandas as pd
import time

def fetch_market_data(asset, timeframes):
    data = {}
    for tf in timeframes:
        candles = get_candles(asset, tf)
        # Validate candles: must be non-empty and have 'close' key in first row
        if not candles or 'close' not in candles[0]:
            continue
        indicators = calculate_indicators(candles)
        data[tf] = {
            'candles': candles,
            'indicators': indicators
        }
    return data

def get_candles(asset, timeframe):
    if is_crypto(asset):
        return get_crypto_candles(asset, timeframe)
    else:
        return get_fx_candles(asset, timeframe)

def is_crypto(asset):
    # Simple check: if asset ends with 'USDT' or 'USD' and is in top crypto list
    cryptos = ['BTC', 'ETH', 'BNB', 'SOL', 'ADA', 'XRP', 'DOGE', 'MATIC', 'DOT', 'LTC', 'TRX', 'AVAX', 'SHIB', 'LINK', 'ATOM', 'XMR', 'ETC', 'FIL', 'APT', 'ARB', 'OP']
    return any(asset.startswith(c) for c in cryptos)

def get_crypto_candles(asset, timeframe):
    import ccxt
    exchange = ccxt.binance()
    symbol = asset.replace('USD', '/USDT') if not asset.endswith('USDT') else asset.replace('USDT', '/USDT')
    tf_map = {'5m': '5m', '15m': '15m', '1h': '1h', '4h': '4h', '1d': '1d'}
    ohlcv = exchange.fetch_ohlcv(symbol, timeframe=tf_map.get(timeframe, '1h'), limit=100)
    candles = []
    for o in ohlcv:
        candles.append({'timestamp': o[0], 'open': o[1], 'high': o[2], 'low': o[3], 'close': o[4], 'volume': o[5]})
    return candles

def get_fx_candles(asset, timeframe):
    import requests
    import datetime
    base, quote = asset[:3], asset[3:]
    # Map timeframe to period (exchangerate.host supports 1m, 5m, 15m, 30m, 1h, 4h, 1d)
    tf_map = {'5m': '5m', '15m': '15m', '1h': '1h', '4h': '4h', '1d': '1d'}
    period = tf_map.get(timeframe, '1h')
    end = datetime.datetime.utcnow()
    start = end - datetime.timedelta(days=5)  # last 5 days
    url = f"https://api.exchangerate.host/timeseries?start_date={start.date()}&end_date={end.date()}&base={base}&symbols={quote}"
    resp = requests.get(url)
    data = resp.json()
    candles = []
    if 'rates' not in data:
        # API error or unsupported pair
        return []
    # Simulate OHLCV from daily close (exchangerate.host gives only close, so OHLC=close, V=0)
    for ts, v in sorted(data['rates'].items()):
        close = v.get(quote)
        if close is None:
            continue
        candles.append({'timestamp': ts, 'open': close, 'high': close, 'low': close, 'close': close, 'volume': 0})
    return candles
