"""
Ensemble Confluence Engine — 15 Vectorized Strategies
======================================================
All 15 indicator computations are fully vectorized using pandas/numpy.
No per-candle Python loops — the entire DataFrame is processed in one pass.

Usage:
    from engine.confluence_engine import run_confluence_engine
    result = run_confluence_engine(candles)
    # result = {
    #   'long_votes': 11, 'short_votes': 2, 'total': 15,
    #   'direction': 'LONG', 'score': 11,
    #   'drivers': ['MACD Bullish Crossover', 'RSI Oversold (28)', 'Bullish EMA Stack'],
    #   'passed': True
    # }
"""

import logging
import os
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

CONFLUENCE_TOTAL = 15
_LONG    =  1
_SHORT   = -1
_NEUTRAL =  0


# ─────────────────────────────────────────────────────────────
#  Helpers
# ─────────────────────────────────────────────────────────────

def _env_int(name: str, default: int) -> int:
    try:
        return int((os.getenv(name) or str(default)).strip())
    except Exception:
        return default


def _candles_to_df(candles: list) -> Optional[pd.DataFrame]:
    """Convert raw candle list to a clean OHLCV DataFrame. Returns None if unusable."""
    if not candles or len(candles) < 30:
        return None
    try:
        df = pd.DataFrame(candles)
        for col in ("open", "high", "low", "close", "volume"):
            if col not in df.columns:
                return None
            df[col] = pd.to_numeric(df[col], errors="coerce")
        df.dropna(subset=["open", "high", "low", "close"], inplace=True)
        df["volume"] = df["volume"].fillna(0)
        df.reset_index(drop=True, inplace=True)
        return df if len(df) >= 30 else None
    except Exception as exc:
        logger.debug("[confluence] candles_to_df failed: %s", exc)
        return None


# ─────────────────────────────────────────────────────────────
#  15 Vectorized Strategy Votes  (each returns (vote, reason))
# ─────────────────────────────────────────────────────────────

def _vote_ema_stack(df: pd.DataFrame) -> Tuple[int, str]:
    """1. EMA Stack: 12 > 26 > 50 = LONG; 12 < 26 < 50 = SHORT."""
    fast  = df["close"].ewm(span=12, adjust=False).mean()
    slow  = df["close"].ewm(span=26, adjust=False).mean()
    trend = df["close"].ewm(span=50, adjust=False).mean()
    f, s, t = fast.iloc[-1], slow.iloc[-1], trend.iloc[-1]
    if f > s > t:
        return _LONG,  "Bullish EMA Stack (12>26>50)"
    if f < s < t:
        return _SHORT, "Bearish EMA Stack (12<26<50)"
    return _NEUTRAL, ""


def _vote_ema_cross(df: pd.DataFrame) -> Tuple[int, str]:
    """2. EMA 20/50 Cross — sustained position."""
    e20 = df["close"].ewm(span=20, adjust=False).mean()
    e50 = df["close"].ewm(span=50, adjust=False).mean()
    if len(e20) < 3:
        return _NEUTRAL, ""
    # Fresh cross is stronger signal
    if e20.iloc[-1] > e50.iloc[-1] and e20.iloc[-2] <= e50.iloc[-2]:
        return _LONG,  "EMA 20/50 Bullish Crossover"
    if e20.iloc[-1] > e50.iloc[-1]:
        return _LONG,  "Price Above EMA 50 (bullish)"
    if e20.iloc[-1] < e50.iloc[-1] and e20.iloc[-2] >= e50.iloc[-2]:
        return _SHORT, "EMA 20/50 Bearish Crossover"
    if e20.iloc[-1] < e50.iloc[-1]:
        return _SHORT, "Price Below EMA 50 (bearish)"
    return _NEUTRAL, ""


def _vote_sma_cross(df: pd.DataFrame) -> Tuple[int, str]:
    """3. SMA 20/50 Golden / Death Cross."""
    s20 = df["close"].rolling(20).mean()
    s50 = df["close"].rolling(50).mean()
    if pd.isna(s50.iloc[-1]):
        return _NEUTRAL, ""
    if s20.iloc[-1] > s50.iloc[-1]:
        return _LONG,  "SMA Golden Cross (20>50)"
    if s20.iloc[-1] < s50.iloc[-1]:
        return _SHORT, "SMA Death Cross (20<50)"
    return _NEUTRAL, ""


def _vote_macd_cross(df: pd.DataFrame) -> Tuple[int, str]:
    """4. MACD Signal-Line Cross & Histogram."""
    ema12 = df["close"].ewm(span=12, adjust=False).mean()
    ema26 = df["close"].ewm(span=26, adjust=False).mean()
    macd  = ema12 - ema26
    sig   = macd.ewm(span=9, adjust=False).mean()
    hist  = macd - sig
    if len(hist) < 3:
        return _NEUTRAL, ""
    # Fresh cross is highest priority
    if hist.iloc[-1] > 0 and hist.iloc[-2] <= 0:
        return _LONG,  "MACD Bullish Crossover"
    if hist.iloc[-1] < 0 and hist.iloc[-2] >= 0:
        return _SHORT, "MACD Bearish Crossover"
    if hist.iloc[-1] > 0:
        return _LONG,  "MACD Bullish Histogram"
    if hist.iloc[-1] < 0:
        return _SHORT, "MACD Bearish Histogram"
    return _NEUTRAL, ""


def _vote_rsi_trend(df: pd.DataFrame) -> Tuple[int, str]:
    """5. RSI Trend Zone: >55 = bullish momentum, <45 = bearish momentum."""
    delta = df["close"].diff()
    gain  = delta.clip(lower=0).rolling(14).mean()
    loss  = (-delta.clip(upper=0)).rolling(14).mean()
    rs    = gain / loss.replace(0, np.nan)
    rsi   = 100 - 100 / (1 + rs)
    val   = rsi.iloc[-1]
    if pd.isna(val):
        return _NEUTRAL, ""
    if val > 55:
        return _LONG,  f"RSI Bullish Zone ({val:.0f})"
    if val < 45:
        return _SHORT, f"RSI Bearish Zone ({val:.0f})"
    return _NEUTRAL, ""


def _vote_rsi_extreme(df: pd.DataFrame) -> Tuple[int, str]:
    """6. RSI Extreme Reversal: <30 oversold = LONG, >70 overbought = SHORT."""
    delta = df["close"].diff()
    gain  = delta.clip(lower=0).rolling(14).mean()
    loss  = (-delta.clip(upper=0)).rolling(14).mean()
    rs    = gain / loss.replace(0, np.nan)
    rsi   = 100 - 100 / (1 + rs)
    val   = rsi.iloc[-1]
    if pd.isna(val):
        return _NEUTRAL, ""
    if val < 30:
        return _LONG,  f"RSI Oversold ({val:.0f})"
    if val > 70:
        return _SHORT, f"RSI Overbought ({val:.0f})"
    return _NEUTRAL, ""


def _vote_bollinger(df: pd.DataFrame) -> Tuple[int, str]:
    """7. Bollinger Band Position: near lower band = LONG, near upper = SHORT."""
    sma   = df["close"].rolling(20).mean()
    std   = df["close"].rolling(20).std()
    upper = sma + 2 * std
    lower = sma - 2 * std
    price = df["close"].iloc[-1]
    u, l  = upper.iloc[-1], lower.iloc[-1]
    if pd.isna(u) or pd.isna(l):
        return _NEUTRAL, ""
    width = u - l
    if width == 0:
        return _NEUTRAL, ""
    pct = (price - l) / width
    if pct < 0.20:
        return _LONG,  "Bollinger Lower Band Bounce"
    if pct > 0.80:
        return _SHORT, "Bollinger Upper Band Rejection"
    return _NEUTRAL, ""


def _vote_bb_squeeze(df: pd.DataFrame) -> Tuple[int, str]:
    """8. Bollinger Band Squeeze Breakout: tight band expanding in price direction."""
    sma   = df["close"].rolling(20).mean()
    std   = df["close"].rolling(20).std()
    upper = sma + 2 * std
    lower = sma - 2 * std
    width = (upper - lower) / sma.replace(0, np.nan)
    w_clean = width.dropna()
    if len(w_clean) < 20:
        return _NEUTRAL, ""
    squeeze_lvl  = w_clean.quantile(0.20)
    prev_avg     = width.iloc[-6:-1].mean()
    current_w    = width.iloc[-1]
    if prev_avg < squeeze_lvl and current_w > prev_avg:
        price = df["close"].iloc[-1]
        mid   = sma.iloc[-1]
        if pd.isna(mid):
            return _NEUTRAL, ""
        if price > mid:
            return _LONG,  "Bollinger Squeeze Breakout (bullish)"
        return _SHORT, "Bollinger Squeeze Breakout (bearish)"
    return _NEUTRAL, ""


def _vote_stochastic(df: pd.DataFrame) -> Tuple[int, str]:
    """9. Stochastic %K/%D Cross in non-extreme zone."""
    period = 14
    low_min  = df["low"].rolling(period).min()
    high_max = df["high"].rolling(period).max()
    denom    = (high_max - low_min).replace(0, np.nan)
    k = 100 * (df["close"] - low_min) / denom
    d = k.rolling(3).mean()
    k_val, d_val = k.iloc[-1], d.iloc[-1]
    if pd.isna(k_val) or pd.isna(d_val):
        return _NEUTRAL, ""
    if k_val > d_val and k_val < 80:
        return _LONG,  f"Stochastic Bullish ({k_val:.0f}/{d_val:.0f})"
    if k_val < d_val and k_val > 20:
        return _SHORT, f"Stochastic Bearish ({k_val:.0f}/{d_val:.0f})"
    return _NEUTRAL, ""


def _vote_adx_di(df: pd.DataFrame) -> Tuple[int, str]:
    """10. ADX Trend with DI+/DI-: strong trend direction confirmation."""
    period   = 14
    plus_dm  = df["high"].diff().clip(lower=0)
    minus_dm = df["low"].diff().clip(upper=0).abs()
    tr = pd.concat([
        df["high"] - df["low"],
        (df["high"] - df["close"].shift(1)).abs(),
        (df["low"]  - df["close"].shift(1)).abs(),
    ], axis=1).max(axis=1)
    atr      = tr.rolling(period).mean().replace(0, np.nan)
    plus_di  = 100 * plus_dm.rolling(period).sum() / atr
    minus_di = 100 * minus_dm.rolling(period).sum() / atr
    dx       = (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan) * 100
    adx      = dx.rolling(period).mean()
    adx_val  = adx.iloc[-1]
    di_p, di_m = plus_di.iloc[-1], minus_di.iloc[-1]
    if pd.isna(adx_val) or adx_val < 20:
        return _NEUTRAL, ""
    if di_p > di_m:
        return _LONG,  f"ADX Bullish Trend (ADX={adx_val:.0f})"
    if di_m > di_p:
        return _SHORT, f"ADX Bearish Trend (ADX={adx_val:.0f})"
    return _NEUTRAL, ""


def _vote_obv(df: pd.DataFrame) -> Tuple[int, str]:
    """11. OBV Trend: rising OBV confirms buyers; falling confirms sellers."""
    sign = np.sign(df["close"].diff().fillna(0))
    obv  = (sign * df["volume"]).cumsum()
    if len(obv) < 12:
        return _NEUTRAL, ""
    slope = obv.iloc[-1] - obv.iloc[-10]
    if slope > 0:
        return _LONG,  "OBV Rising (buyer volume dominance)"
    if slope < 0:
        return _SHORT, "OBV Falling (seller volume dominance)"
    return _NEUTRAL, ""


def _vote_supertrend(df: pd.DataFrame) -> Tuple[int, str]:
    """12. Supertrend (ATR-based 10/3): price above lower band = LONG."""
    period, mult = 10, 3.0
    hl2 = (df["high"] + df["low"]) / 2
    tr  = pd.concat([
        df["high"] - df["low"],
        (df["high"] - df["close"].shift(1)).abs(),
        (df["low"]  - df["close"].shift(1)).abs(),
    ], axis=1).max(axis=1)
    atr         = tr.rolling(period).mean()
    upper_basic = hl2 + mult * atr
    lower_basic = hl2 - mult * atr
    close_val   = df["close"].iloc[-1]
    lower_val   = lower_basic.iloc[-1]
    upper_val   = upper_basic.iloc[-1]
    if pd.isna(lower_val) or pd.isna(upper_val):
        return _NEUTRAL, ""
    if close_val > lower_val:
        return _LONG,  "Supertrend Bullish Signal"
    if close_val < upper_val:
        return _SHORT, "Supertrend Bearish Signal"
    return _NEUTRAL, ""


def _vote_vwap(df: pd.DataFrame) -> Tuple[int, str]:
    """13. VWAP: price above VWAP = institutional buy-side bias."""
    typical = (df["high"] + df["low"] + df["close"]) / 3
    vol     = df["volume"].replace(0, np.nan)
    vwap    = (typical * vol).cumsum() / vol.cumsum()
    price   = df["close"].iloc[-1]
    vwap_v  = vwap.iloc[-1]
    if pd.isna(vwap_v) or vwap_v == 0:
        return _NEUTRAL, ""
    if price > vwap_v:
        return _LONG,  "Price Above VWAP (buy-side pressure)"
    if price < vwap_v:
        return _SHORT, "Price Below VWAP (sell-side pressure)"
    return _NEUTRAL, ""


def _vote_engulfing(df: pd.DataFrame) -> Tuple[int, str]:
    """14. Candlestick Pattern: engulfing candles and hammer/shooting star."""
    if len(df) < 3:
        return _NEUTRAL, ""
    o1, c1 = df["open"].iloc[-2], df["close"].iloc[-2]
    o0, c0 = df["open"].iloc[-1], df["close"].iloc[-1]
    h0, l0 = df["high"].iloc[-1], df["low"].iloc[-1]
    body     = abs(c0 - o0)
    high_wk  = h0 - max(o0, c0)
    low_wk   = min(o0, c0) - l0
    # Bullish engulfing
    if c1 < o1 and c0 > o0 and c0 > o1 and o0 < c1:
        return _LONG,  "Bullish Engulfing Candle"
    # Bearish engulfing
    if c1 > o1 and c0 < o0 and c0 < o1 and o0 > c1:
        return _SHORT, "Bearish Engulfing Candle"
    # Hammer (bullish reversal)
    if body > 0 and low_wk > body * 2 and high_wk < body and c0 > o0:
        return _LONG,  "Bullish Hammer Pattern"
    # Shooting star (bearish reversal)
    if body > 0 and high_wk > body * 2 and low_wk < body and c0 < o0:
        return _SHORT, "Bearish Shooting Star"
    return _NEUTRAL, ""


def _vote_fibonacci(df: pd.DataFrame, lookback: int = 50) -> Tuple[int, str]:
    """15. Fibonacci Retracement Zone: price near 50-61.8% = LONG support; 23.6-38.2% = SHORT resistance."""
    n          = min(lookback, len(df))
    swing_high = df["high"].iloc[-n:].max()
    swing_low  = df["low"].iloc[-n:].min()
    price      = df["close"].iloc[-1]
    rng        = swing_high - swing_low
    if rng == 0:
        return _NEUTRAL, ""
    fib_236  = swing_high - 0.236 * rng
    fib_382  = swing_high - 0.382 * rng
    fib_500  = swing_high - 0.500 * rng
    fib_618  = swing_high - 0.618 * rng
    tol      = rng * 0.03  # ±3% tolerance
    # LONG: price in 50–61.8% support retracement zone
    if fib_618 - tol <= price <= fib_500 + tol:
        return _LONG,  "Fibonacci 50–61.8% Support Zone"
    # SHORT: price in 23.6–38.2% resistance retracement zone
    if fib_382 - tol <= price <= fib_236 + tol:
        return _SHORT, "Fibonacci 23.6–38.2% Resistance Zone"
    return _NEUTRAL, ""


# ─────────────────────────────────────────────────────────────
#  Registry of all 15 vote functions (order matters for labels)
# ─────────────────────────────────────────────────────────────
_VOTE_FNS = [
    _vote_ema_stack,    # 1
    _vote_ema_cross,    # 2
    _vote_sma_cross,    # 3
    _vote_macd_cross,   # 4
    _vote_rsi_trend,    # 5
    _vote_rsi_extreme,  # 6
    _vote_bollinger,    # 7
    _vote_bb_squeeze,   # 8
    _vote_stochastic,   # 9
    _vote_adx_di,       # 10
    _vote_obv,          # 11
    _vote_supertrend,   # 12
    _vote_vwap,         # 13
    _vote_engulfing,    # 14
    _vote_fibonacci,    # 15
]


# ─────────────────────────────────────────────────────────────
#  Public API
# ─────────────────────────────────────────────────────────────

def run_confluence_engine(candles: list) -> Dict:
    """Run all 15 vectorized strategies and return a confluence result dict.

    Args:
        candles: List of OHLCV dicts with keys open/high/low/close/volume.

    Returns:
        {
            'long_votes':  int,        # strategies voting LONG
            'short_votes': int,        # strategies voting SHORT
            'total':       int,        # always 15
            'direction':   str,        # 'LONG' | 'SHORT' | 'NEUTRAL'
            'score':       int,        # max(long_votes, short_votes)
            'drivers':     list[str],  # top-3 reason strings
            'passed':      bool,       # True if score >= CONFLUENCE_MIN_VOTES env var (default 10)
        }
    """
    min_votes = _env_int("CONFLUENCE_MIN_VOTES", 10)
    df = _candles_to_df(candles)
    if df is None:
        return {
            "long_votes": 0, "short_votes": 0, "total": CONFLUENCE_TOTAL,
            "direction": "NEUTRAL", "score": 0, "drivers": [], "passed": False,
        }

    long_reasons:  List[str] = []
    short_reasons: List[str] = []

    for fn in _VOTE_FNS:
        try:
            vote, reason = fn(df)
        except Exception as exc:
            logger.debug("[confluence] %s failed: %s", fn.__name__, exc)
            vote, reason = _NEUTRAL, ""
        if vote == _LONG and reason:
            long_reasons.append(reason)
        elif vote == _SHORT and reason:
            short_reasons.append(reason)

    n_long  = len(long_reasons)
    n_short = len(short_reasons)

    if n_long >= n_short and n_long >= min_votes:
        direction = "LONG"
        score     = n_long
        drivers   = long_reasons[:3]
    elif n_short > n_long and n_short >= min_votes:
        direction = "SHORT"
        score     = n_short
        drivers   = short_reasons[:3]
    else:
        direction = "NEUTRAL"
        score     = max(n_long, n_short)
        drivers   = (long_reasons if n_long >= n_short else short_reasons)[:3]

    return {
        "long_votes":  n_long,
        "short_votes": n_short,
        "total":       CONFLUENCE_TOTAL,
        "direction":   direction,
        "score":       score,
        "drivers":     drivers,
        "passed":      direction != "NEUTRAL",
    }
