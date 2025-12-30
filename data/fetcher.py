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
    from alpha_vantage.foreignexchange import ForeignExchange
    key = os.getenv('ALPHA_VANTAGE_KEY', '')
    fx = ForeignExchange(key)
    base, quote = asset[:3], asset[3:]
    tf_map = {'5m': 'FX_INTRADAY', '15m': 'FX_INTRADAY', '1h': 'FX_INTRADAY', '4h': 'FX_DAILY', '1d': 'FX_DAILY'}
    if timeframe in ['5m', '15m', '1h']:
        data, _ = fx.get_currency_exchange_intraday(from_symbol=base, to_symbol=quote, interval='5min', outputsize='compact')
    else:
        data, _ = fx.get_currency_exchange_daily(from_symbol=base, to_symbol=quote, outputsize='compact')
    candles = []
    for ts, v in list(data.items())[-100:]:
        candles.append({'timestamp': ts, 'open': float(v['1. open']), 'high': float(v['2. high']), 'low': float(v['3. low']), 'close': float(v['4. close']), 'volume': 0})
    candles = sorted(candles, key=lambda x: x['timestamp'])
    return candles
