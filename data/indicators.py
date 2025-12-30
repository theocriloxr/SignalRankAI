import pandas as pd
import numpy as np

def calculate_indicators(candles):
    df = pd.DataFrame(candles)
    indicators = {}
    indicators['ema_fast'] = df['close'].ewm(span=20, adjust=False).mean().iloc[-1]
    indicators['ema_slow'] = df['close'].ewm(span=50, adjust=False).mean().iloc[-1]
    indicators['ema_trend'] = df['close'].ewm(span=200, adjust=False).mean().iloc[-1]
    indicators['rsi'] = RSI(df['close'], 14)
    macd, macd_signal, macd_hist = MACD(df['close'])
    indicators['macd'] = {'macd': macd, 'signal': macd_signal, 'hist': macd_hist}
    indicators['stoch_rsi'] = STOCH_RSI(df['close'], 14)
    indicators['atr'] = ATR(df, 14)
    bb = BOLLINGER_BANDS(df['close'])
    indicators['bollinger'] = bb
    indicators['adx'] = ADX(df, 14)
    indicators['volume_avg'] = df['volume'].rolling(window=20).mean().iloc[-1]
    return indicators

def RSI(series, period):
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    return rsi.iloc[-1] if not rsi.isna().all() else 50

def MACD(series, fast=12, slow=26, signal=9):
    ema_fast = series.ewm(span=fast, adjust=False).mean()
    ema_slow = series.ewm(span=slow, adjust=False).mean()
    macd = ema_fast - ema_slow
    macd_signal = macd.ewm(span=signal, adjust=False).mean()
    macd_hist = macd - macd_signal
    return macd.iloc[-1], macd_signal.iloc[-1], macd_hist.iloc[-1]

def STOCH_RSI(series, period):
    min_val = series.rolling(window=period).min()
    max_val = series.rolling(window=period).max()
    stoch_rsi = (series - min_val) / (max_val - min_val)
    return stoch_rsi.iloc[-1] if not stoch_rsi.isna().all() else 0.5

def ATR(df, period):
    high = df['high']
    low = df['low']
    close = df['close']
    prev_close = close.shift(1)
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low - prev_close).abs()
    ], axis=1).max(axis=1)
    atr = tr.rolling(window=period).mean()
    return atr.iloc[-1] if not atr.isna().all() else 0

def BOLLINGER_BANDS(series, period=20, num_std=2):
    sma = series.rolling(window=period).mean()
    std = series.rolling(window=period).std()
    upper = sma + (num_std * std)
    lower = sma - (num_std * std)
    width = (upper - lower).iloc[-1] / sma.iloc[-1] if not sma.isna().all() else 0
    return {'upper': upper.iloc[-1], 'lower': lower.iloc[-1], 'width': width}

def ADX(df, period):
    high = df['high']
    low = df['low']
    close = df['close']
    plus_dm = high.diff()
    minus_dm = low.diff()
    plus_dm[plus_dm < 0] = 0
    minus_dm[minus_dm > 0] = 0
    tr = pd.concat([
        high - low,
        (high - close.shift(1)).abs(),
        (low - close.shift(1)).abs()
    ], axis=1).max(axis=1)
    atr = tr.rolling(window=period).mean()
    plus_di = 100 * (plus_dm.rolling(window=period).sum() / atr)
    minus_di = 100 * (abs(minus_dm).rolling(window=period).sum() / atr)
    dx = (abs(plus_di - minus_di) / (plus_di + minus_di)) * 100
    adx = dx.rolling(window=period).mean()
    return adx.iloc[-1] if not adx.isna().all() else 20
