import pandas as pd
import numpy as np
from typing import Dict, List, Tuple, Optional

def calculate_indicators(candles):
    """Calculate all technical indicators for a given set of candles."""
    df = pd.DataFrame(candles)
    if len(df) < 50:
        return {}
    
    indicators = {}
    
    # Trend Indicators
    indicators['ema_20'] = df['close'].ewm(span=20, adjust=False).mean().iloc[-1]
    indicators['ema_50'] = df['close'].ewm(span=50, adjust=False).mean().iloc[-1]
    indicators['ema_200'] = df['close'].ewm(span=200, adjust=False).mean().iloc[-1]
    indicators['sma_20'] = df['close'].rolling(window=20).mean().iloc[-1]
    indicators['sma_50'] = df['close'].rolling(window=50).mean().iloc[-1]
    indicators['sma_200'] = df['close'].rolling(window=200).mean().iloc[-1]
    
    # Trend Direction
    indicators['trend_ema'] = determine_trend_ema(df['close'].iloc[-50:].values)
    indicators['trend_sma'] = determine_trend_sma(df['close'].iloc[-50:].values)
    
    # Momentum Indicators
    indicators['rsi'] = RSI(df['close'], 14)
    indicators['rsi_fast'] = RSI(df['close'], 7)
    
    macd, macd_signal, macd_hist = MACD(df['close'])
    indicators['macd'] = {'macd': macd, 'signal': macd_signal, 'hist': macd_hist}
    indicators['macd_trend'] = 1 if macd > macd_signal else -1
    
    indicators['stoch_rsi'] = STOCH_RSI(df['close'], 14)
    
    # Volatility Indicators
    indicators['atr'] = ATR(df, 14)
    indicators['atr_percent'] = (indicators['atr'] / df['close'].iloc[-1]) * 100
    
    bb = BOLLINGER_BANDS(df['close'])
    indicators['bollinger'] = bb
    
    indicators['adx'] = ADX(df, 14)
    indicators['adx_trend'] = get_adx_trend(df, 14)
    
    # Volume Indicators
    indicators['volume'] = df['volume'].iloc[-1]
    indicators['volume_avg'] = df['volume'].rolling(window=20).mean().iloc[-1]
    indicators['volume_ratio'] = indicators['volume'] / indicators['volume_avg'] if indicators['volume_avg'] > 0 else 1.0
    indicators['obv'] = OBV(df['close'], df['volume']).iloc[-1]
    
    # Market Structure
    indicators['higher_highs'] = detect_higher_highs(df['high'].iloc[-20:].values)
    indicators['lower_lows'] = detect_lower_lows(df['low'].iloc[-20:].values)
    indicators['market_structure'] = get_market_structure(df)
    
    # Support & Resistance
    sr_zones = find_support_resistance(df)
    indicators['support_levels'] = sr_zones['support']
    indicators['resistance_levels'] = sr_zones['resistance']
    indicators['nearest_support'] = sr_zones['nearest_support']
    indicators['nearest_resistance'] = sr_zones['nearest_resistance']
    
    # Breakout Detection
    indicators['breakout'] = detect_breakout(df)
    indicators['retest'] = detect_retest(df)
    
    # Regime Detection
    indicators['regime'] = detect_market_regime(df)
    indicators['volatility_regime'] = classify_volatility(indicators['atr_percent'])
    
    # Price Action
    indicators['close_price'] = df['close'].iloc[-1]
    indicators['high_price'] = df['high'].iloc[-1]
    indicators['low_price'] = df['low'].iloc[-1]
    indicators['range'] = indicators['high_price'] - indicators['low_price']
    indicators['range_percent'] = (indicators['range'] / indicators['close_price']) * 100 if indicators['close_price'] > 0 else 0
    
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


# ==================== NEW INDICATORS ====================

def determine_trend_ema(closes: np.ndarray) -> int:
    """Determine trend direction using EMA: 1=uptrend, -1=downtrend, 0=neutral"""
    if len(closes) < 50:
        return 0
    ema20 = pd.Series(closes).ewm(span=20, adjust=False).mean().iloc[-1]
    ema50 = pd.Series(closes).ewm(span=50, adjust=False).mean().iloc[-1]
    ema200 = pd.Series(closes).ewm(span=200, adjust=False).mean().iloc[-1]
    close = closes[-1]
    
    if close > ema20 > ema50 > ema200:
        return 1  # Strong uptrend
    elif close < ema20 < ema50 < ema200:
        return -1  # Strong downtrend
    elif ema20 > ema50:
        return 1  # Mild uptrend
    elif ema20 < ema50:
        return -1  # Mild downtrend
    return 0


def determine_trend_sma(closes: np.ndarray) -> int:
    """Determine trend direction using SMA"""
    if len(closes) < 50:
        return 0
    sma20 = pd.Series(closes).rolling(window=20).mean().iloc[-1]
    sma50 = pd.Series(closes).rolling(window=50).mean().iloc[-1]
    sma200 = pd.Series(closes).rolling(window=200).mean().iloc[-1]
    close = closes[-1]
    
    if close > sma20 > sma50 > sma200:
        return 1
    elif close < sma20 < sma50 < sma200:
        return -1
    elif sma20 > sma50:
        return 1
    elif sma20 < sma50:
        return -1
    return 0


def get_adx_trend(df: pd.DataFrame, period: int) -> str:
    """Get ADX trend strength: 'strong', 'moderate', 'weak'"""
    adx = ADX(df, period)
    if adx >= 40:
        return 'strong'
    elif adx >= 25:
        return 'moderate'
    else:
        return 'weak'


def OBV(close: pd.Series, volume: pd.Series) -> pd.Series:
    """On-Balance Volume indicator"""
    obv = pd.Series(index=close.index, dtype='float64')
    obv.iloc[0] = volume.iloc[0]
    
    for i in range(1, len(close)):
        if close.iloc[i] > close.iloc[i-1]:
            obv.iloc[i] = obv.iloc[i-1] + volume.iloc[i]
        elif close.iloc[i] < close.iloc[i-1]:
            obv.iloc[i] = obv.iloc[i-1] - volume.iloc[i]
        else:
            obv.iloc[i] = obv.iloc[i-1]
    
    return obv


def detect_higher_highs(highs: np.ndarray) -> bool:
    """Detect if price is making higher highs (uptrend signal)"""
    if len(highs) < 3:
        return False
    return highs[-1] > highs[-2] and highs[-2] > highs[-3]


def detect_lower_lows(lows: np.ndarray) -> bool:
    """Detect if price is making lower lows (downtrend signal)"""
    if len(lows) < 3:
        return False
    return lows[-1] < lows[-2] and lows[-2] < lows[-3]


def get_market_structure(df: pd.DataFrame) -> str:
    """Analyze market structure: 'bullish', 'bearish', 'neutral'"""
    if len(df) < 20:
        return 'neutral'
    
    hh = detect_higher_highs(df['high'].iloc[-20:].values)
    ll = detect_higher_lows(df['low'].iloc[-20:].values)
    
    lh = detect_lower_highs(df['high'].iloc[-20:].values)
    ll_down = detect_lower_lows(df['low'].iloc[-20:].values)
    
    if hh and ll:
        return 'bullish'
    elif lh and ll_down:
        return 'bearish'
    else:
        return 'neutral'


def detect_higher_lows(lows: np.ndarray) -> bool:
    """Detect higher lows (bullish structure)"""
    if len(lows) < 3:
        return False
    return lows[-1] > lows[-2] and lows[-2] > lows[-3]


def detect_lower_highs(highs: np.ndarray) -> bool:
    """Detect lower highs (bearish structure)"""
    if len(highs) < 3:
        return False
    return highs[-1] < highs[-2] and highs[-2] < highs[-3]


def find_support_resistance(df: pd.DataFrame, lookback: int = 50) -> Dict:
    """Find support and resistance levels using pivot points"""
    if len(df) < lookback:
        lookback = len(df) - 1
    
    recent = df.iloc[-lookback:]
    high = recent['high']
    low = recent['low']
    close = recent['close']
    
    pivot = (high + low + close) / 3
    support1 = (2 * pivot) - high
    resistance1 = (2 * pivot) - low
    support2 = pivot - (resistance1 - support1)
    resistance2 = pivot + (resistance1 - support1)
    
    current_price = close.iloc[-1]
    
    support_levels = [support2.iloc[-1], support1.iloc[-1]]
    resistance_levels = [resistance1.iloc[-1], resistance2.iloc[-1]]
    
    # Find nearest S/R
    nearest_support = max([s for s in support_levels if s < current_price], default=support_levels[0])
    nearest_resistance = min([r for r in resistance_levels if r > current_price], default=resistance_levels[1])
    
    return {
        'support': support_levels,
        'resistance': resistance_levels,
        'nearest_support': nearest_support,
        'nearest_resistance': nearest_resistance,
        'distance_to_support_pct': ((current_price - nearest_support) / current_price * 100) if nearest_support > 0 else 0,
        'distance_to_resistance_pct': ((nearest_resistance - current_price) / current_price * 100) if nearest_resistance > 0 else 0,
    }


def detect_breakout(df: pd.DataFrame, lookback: int = 20) -> Dict:
    """Detect if price is breaking out above resistance or below support"""
    if len(df) < lookback + 5:
        return {'breakout': False, 'direction': None, 'type': None}
    
    recent = df.iloc[-lookback:]
    resistance = recent['high'].max()
    support = recent['low'].min()
    
    current_high = df['high'].iloc[-1]
    current_low = df['low'].iloc[-1]
    current_close = df['close'].iloc[-1]
    
    breakout_high = current_high > resistance
    breakout_low = current_low < support
    
    # Check for breakout with volume confirmation
    volume_current = df['volume'].iloc[-1]
    volume_avg = df['volume'].iloc[-lookback:].mean()
    volume_confirmed = volume_current > volume_avg * 1.5
    
    if breakout_high and volume_confirmed:
        return {'breakout': True, 'direction': 'up', 'type': 'resistance_breakout', 'level': resistance}
    elif breakout_low and volume_confirmed:
        return {'breakout': True, 'direction': 'down', 'type': 'support_breakout', 'level': support}
    
    return {'breakout': False, 'direction': None, 'type': None}


def detect_retest(df: pd.DataFrame, lookback: int = 20) -> Dict:
    """Detect retest of broken level (price returns to level and bounces)"""
    if len(df) < lookback + 5:
        return {'retest': False, 'direction': None}
    
    breakout_info = detect_breakout(df, lookback)
    
    if not breakout_info['breakout']:
        return {'retest': False, 'direction': None}
    
    # Check if price is retesting the broken level
    broken_level = breakout_info['level']
    current_price = df['close'].iloc[-1]
    tolerance_pct = 0.5  # 0.5% tolerance for retest
    tolerance = broken_level * (tolerance_pct / 100)
    
    if abs(current_price - broken_level) <= tolerance:
        return {'retest': True, 'direction': breakout_info['direction'], 'level': broken_level}
    
    return {'retest': False, 'direction': None}


def detect_market_regime(df: pd.DataFrame) -> str:
    """Detect if market is trending or ranging"""
    if len(df) < 50:
        return 'unknown'
    
    # Calculate ADX
    adx = ADX(df, 14)
    
    # Calculate momentum
    closes = df['close'].iloc[-50:].values
    momentum = (closes[-1] - closes[0]) / closes[0] * 100
    
    # Trending if ADX > 25 and momentum is strong
    if adx > 25 and abs(momentum) > 2:
        return 'trending'
    
    # Ranging if ADX < 20
    if adx < 20:
        return 'ranging'
    
    return 'neutral'


def classify_volatility(atr_percent: float) -> str:
    """Classify volatility level: 'low', 'medium', 'high'"""
    if atr_percent < 1.0:
        return 'low'
    elif atr_percent < 3.0:
        return 'medium'
    else:
        return 'high'
