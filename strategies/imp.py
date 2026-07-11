from __future__ import annotations

import os
from datetime import datetime
from typing import Any


def _env_bool(name: str, default: bool) -> bool:
    try:
        raw = (os.getenv(name) or str(default)).strip().lower()
        return raw in {"1", "true", "yes", "on"}
    except Exception:
        return default


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _is_fx(symbol: str) -> bool:
    s = str(symbol or "").upper().strip()
    return len(s) == 6 and s.isalpha()


def _is_crypto(symbol: str) -> bool:
    s = str(symbol or "").upper().strip()
    return s.endswith(("USDT", "BUSD", "USDC", "BTC", "ETH"))


def _is_commodity(symbol: str) -> bool:
    s = str(symbol or "").upper().strip()
    return s in {"XAUUSD", "XAGUSD", "WTI", "BRENT", "CL=F", "GC=F", "SI=F"}


def _is_stock(symbol: str) -> bool:
    return not (_is_fx(symbol) or _is_crypto(symbol) or _is_commodity(symbol))


def _utc_hour_now() -> int:
    return int(datetime.utcnow().hour)


def _is_london_ny_overlap() -> bool:
    hour = _utc_hour_now()
    return 13 <= hour < 17


def _is_london_session() -> bool:
    hour = _utc_hour_now()
    return 7 <= hour < 16


def _is_new_york_session() -> bool:
    hour = _utc_hour_now()
    return 13 <= hour < 22


def _fx_session_allowed() -> bool:
    allowed_raw = str(os.getenv("IMP_FX_ALLOWED_SESSIONS") or "london,newyork,overlap").strip().lower()
    allowed = {s.strip() for s in allowed_raw.split(",") if s.strip()}
    checks = {
        "london": _is_london_session(),
        "newyork": _is_new_york_session(),
        "new_york": _is_new_york_session(),
        "ny": _is_new_york_session(),
        "overlap": _is_london_ny_overlap(),
    }
    return any(checks.get(name, False) for name in allowed)


def _rsi_series(closes: list[float], period: int = 14) -> list[float]:
    if len(closes) < period + 1:
        return []
    out: list[float] = []
    gains: list[float] = []
    losses: list[float] = []
    for i in range(1, len(closes)):
        delta = float(closes[i]) - float(closes[i - 1])
        gains.append(max(0.0, delta))
        losses.append(max(0.0, -delta))
        if i >= period:
            window_g = gains[i - period:i]
            window_l = losses[i - period:i]
            avg_g = sum(window_g) / float(period)
            avg_l = sum(window_l) / float(period)
            if avg_l <= 0:
                out.append(100.0)
            else:
                rs = avg_g / avg_l
                out.append(100.0 - (100.0 / (1.0 + rs)))
    return out


def _atr(candles: list[dict], period: int = 14) -> float:
    if len(candles) < period + 1:
        return 0.0
    trs: list[float] = []
    for i in range(1, len(candles)):
        h = _safe_float(candles[i].get("high"))
        l = _safe_float(candles[i].get("low"))
        pc = _safe_float(candles[i - 1].get("close"))
        tr = max(h - l, abs(h - pc), abs(l - pc))
        trs.append(tr)
    tail = trs[-period:] if len(trs) >= period else trs
    if not tail:
        return 0.0
    return float(sum(tail) / float(len(tail)))


def _is_bullish_engulfing(candles: list[dict]) -> bool:
    if len(candles) < 2:
        return False
    prev = candles[-2]
    cur = candles[-1]
    p_open = _safe_float(prev.get("open"))
    p_close = _safe_float(prev.get("close"))
    c_open = _safe_float(cur.get("open"))
    c_close = _safe_float(cur.get("close"))
    prev_bear = p_close < p_open
    cur_bull = c_close > c_open
    body_engulf = (c_open <= p_close) and (c_close >= p_open)
    return bool(prev_bear and cur_bull and body_engulf)


def _is_bearish_engulfing(candles: list[dict]) -> bool:
    if len(candles) < 2:
        return False
    prev = candles[-2]
    cur = candles[-1]
    p_open = _safe_float(prev.get("open"))
    p_close = _safe_float(prev.get("close"))
    c_open = _safe_float(cur.get("open"))
    c_close = _safe_float(cur.get("close"))
    prev_bull = p_close > p_open
    cur_bear = c_close < c_open
    body_engulf = (c_open >= p_close) and (c_close <= p_open)
    return bool(prev_bull and cur_bear and body_engulf)


def _is_bullish_pin_bar(candles: list[dict]) -> bool:
    if not candles:
        return False
    c = candles[-1]
    o = _safe_float(c.get("open"))
    h = _safe_float(c.get("high"))
    l = _safe_float(c.get("low"))
    cl = _safe_float(c.get("close"))
    body = abs(cl - o)
    rng = max(1e-9, h - l)
    lower_wick = min(o, cl) - l
    upper_wick = h - max(o, cl)
    return bool((lower_wick >= (2.0 * body)) and (upper_wick <= body) and (body / rng <= 0.4))


def _is_bearish_pin_bar(candles: list[dict]) -> bool:
    if not candles:
        return False
    c = candles[-1]
    o = _safe_float(c.get("open"))
    h = _safe_float(c.get("high"))
    l = _safe_float(c.get("low"))
    cl = _safe_float(c.get("close"))
    body = abs(cl - o)
    rng = max(1e-9, h - l)
    lower_wick = min(o, cl) - l
    upper_wick = h - max(o, cl)
    return bool((upper_wick >= (2.0 * body)) and (lower_wick <= body) and (body / rng <= 0.4))


def _volume_profile_poc(candles: list[dict], bins: int = 24) -> float | None:
    if not candles:
        return None
    highs = [_safe_float(c.get("high")) for c in candles]
    lows = [_safe_float(c.get("low")) for c in candles]
    min_p = min(lows)
    max_p = max(highs)
    if max_p <= min_p:
        return None
    bin_count = max(8, int(bins))
    step = (max_p - min_p) / float(bin_count)
    if step <= 0:
        return None
    volume_bins = [0.0 for _ in range(bin_count)]
    for c in candles:
        high = _safe_float(c.get("high"))
        low = _safe_float(c.get("low"))
        close = _safe_float(c.get("close"))
        vol = max(0.0, _safe_float(c.get("volume"), 0.0))
        typical = (high + low + close) / 3.0
        idx = int((typical - min_p) / step)
        idx = max(0, min(bin_count - 1, idx))
        volume_bins[idx] += vol
    max_idx = int(max(range(len(volume_bins)), key=lambda i: volume_bins[i]))
    return float(min_p + ((max_idx + 0.5) * step))


def _ema_bias(candles: list[dict], indicators: dict, ema_key: str = "ema_200") -> str | None:
    if not candles or not isinstance(indicators, dict):
        return None
    close = _safe_float(candles[-1].get("close"))
    ema_value = _safe_float(indicators.get(ema_key))
    if close <= 0 or ema_value <= 0:
        return None
    if close > ema_value:
        return "LONG"
    if close < ema_value:
        return "SHORT"
    return None


def institutional_momentum_pulse_strategies(asset: str, market_data: dict) -> list[dict]:
    """Institutional Momentum Pulse (IMP).

    Rule set:
    - H4 trend must align with 200 EMA.
    - H1 must pull back to 50 EMA.
    - Trigger requires engulfing/pin bar + RSI cross around 50.
    - Uses ATR stop model and asset-class-specific RR.
    
    PHASE 1 FIX #4: Includes stale data consistency check (24-hour freshness).
    """
    if not isinstance(market_data, dict):
        return []

    h4 = market_data.get("4h") or {}
    h1 = market_data.get("1h") or {}
    if not isinstance(h4, dict) or not isinstance(h1, dict):
        return []

    h4_candles = list(h4.get("candles") or [])
    h1_candles = list(h1.get("candles") or [])
    h4_ind = dict(h4.get("indicators") or {})
    h1_ind = dict(h1.get("indicators") or {})
    
    # PHASE 1 FIX #4: Stale Data Consistency - Check both H4 and H1 data freshness
    for tf_name, candles in [("4h", h4_candles), ("1h", h1_candles)]:
        if candles and len(candles) > 0:
            try:
                from datetime import datetime, timedelta, timezone
                last_ts = candles[-1].get('timestamp', 0)
                if last_ts > 0:
                    last_time = datetime.fromtimestamp(last_ts / 1000, tz=timezone.utc)
                    age = datetime.now(timezone.utc) - last_time
                    if age > timedelta(hours=24):
                        import logging
                        logging.getLogger(__name__).debug(
                            f"[imp] Stale data for {asset} {tf_name}: {age.total_seconds()/3600:.1f} hours old"
                        )
                        return []  # Stale data, skip signal
            except Exception:
                pass  # If timestamp check fails, proceed anyway

    # FIX: Reduced from 220/120 to 50/30 for degraded mode operation
    # The fetcher only gets 200 candles max, so 220 requirement always fails
    # Also allow fallback to 1d/4h if 4h/1h not available
    _min_h4_candles = 50
    _min_h1_candles = 30
    
    if len(h4_candles) < _min_h4_candles:
        # Try fallback to 1d for H4 data
        d1 = market_data.get("1d") or {}
        if isinstance(d1, dict) and d1.get("candles"):
            h4_candles = list(d1.get("candles") or [])
            h4_ind = dict(d1.get("indicators") or {})
    
    if len(h1_candles) < _min_h1_candles:
        # Try fallback to 4h for H1 data
        f4h = market_data.get("4h") or {}
        if isinstance(f4h, dict) and f4h.get("candles"):
            h1_candles = list(f4h.get("candles") or [])
            h1_ind = dict(f4h.get("indicators") or {})
    
    if len(h4_candles) < _min_h4_candles or len(h1_candles) < _min_h1_candles:
        import logging
        logging.getLogger(__name__).debug(
            f"[imp] Insufficient candles: h4={len(h4_candles)} (need {_min_h4_candles}), h1={len(h1_candles)} (need {_min_h1_candles})"
        )
        return []

    symbol = str(asset or "").upper().strip()
    if _is_fx(symbol):
        if _env_bool("IMP_FX_OVERLAP_ONLY", False):
            if not _is_london_ny_overlap():
                return []
        elif _env_bool("IMP_FX_SESSION_FILTER_ENABLED", "IMP_FX_ALLOWED_SESSIONS" in os.environ):
            if not _fx_session_allowed():
                return []

    h4_bias = _ema_bias(h4_candles, h4_ind, "ema_200")
    if h4_bias is None:
        return []

    direction = h4_bias

    d1 = market_data.get("1d") or {}
    if isinstance(d1, dict):
        d1_bias = _ema_bias(list(d1.get("candles") or []), dict(d1.get("indicators") or {}), "ema_200")
        if d1_bias is not None and d1_bias != direction:
            return []
    h4_close = _safe_float(h4_candles[-1].get("close"))
    h4_ema200 = _safe_float(h4_ind.get("ema_200"))
    if h4_ema200 <= 0 or h4_close <= 0:
        return []

    # Asset-class adaptation: optional stock relative-strength filter
    # (example: avoid longs when broad market momentum is bearish).
    if _is_stock(symbol) and _env_bool("IMP_STOCK_RS_STRICT", False):
        spx_trend = _safe_float(h1_ind.get("spx_trend"), _safe_float(h4_ind.get("spx_trend"), 0.0))
        if direction == "LONG" and spx_trend < 0:
            return []
        if direction == "SHORT" and spx_trend > 0:
            return []

    # Asset-class adaptation: optional commodity gate using DXY momentum,
    # primarily for metals (e.g. Gold longs favor bearish DXY).
    if symbol in {"XAUUSD", "XAGUSD"} and _env_bool("IMP_GOLD_DXY_FILTER", False):
        dxy_trend = _safe_float(h1_ind.get("dxy_trend"), _safe_float(h4_ind.get("dxy_trend"), 0.0))
        if direction == "LONG" and dxy_trend > 0:
            return []
        if direction == "SHORT" and dxy_trend < 0:
            return []

    h1_close = _safe_float(h1_candles[-1].get("close"))
    h1_high = _safe_float(h1_candles[-1].get("high"))
    h1_low = _safe_float(h1_candles[-1].get("low"))
    h1_ema50 = _safe_float(h1_ind.get("ema_50"))
    if h1_ema50 <= 0 or h1_close <= 0:
        return []

    touch_tolerance = max(h1_ema50 * 0.0015, _safe_float(h1_ind.get("atr"), 0.0) * 0.20)
    if direction == "LONG":
        touched = h1_low <= (h1_ema50 + touch_tolerance)
    else:
        touched = h1_high >= (h1_ema50 - touch_tolerance)
    if not touched:
        return []

    poc = _volume_profile_poc(h1_candles[-80:], bins=24)
    if poc is None:
        return []
    if direction == "LONG" and not (poc <= h1_close):
        return []
    if direction == "SHORT" and not (poc >= h1_close):
        return []

    h1_closes = [_safe_float(c.get("close")) for c in h1_candles]
    rsi_hist = _rsi_series(h1_closes, period=14)
    if len(rsi_hist) < 2:
        return []
    prev_rsi = _safe_float(rsi_hist[-2], 50.0)
    curr_rsi = _safe_float(rsi_hist[-1], _safe_float(h1_ind.get("rsi"), 50.0))

    bull_trigger = _is_bullish_engulfing(h1_candles) or _is_bullish_pin_bar(h1_candles)
    bear_trigger = _is_bearish_engulfing(h1_candles) or _is_bearish_pin_bar(h1_candles)

    if direction == "LONG":
        if not (bull_trigger and prev_rsi <= 50.0 < curr_rsi):
            return []
    else:
        if not (bear_trigger and prev_rsi >= 50.0 > curr_rsi):
            return []

    atr14 = _safe_float(h1_ind.get("atr"), 0.0)
    if atr14 <= 0:
        atr14 = _atr(h1_candles, period=14)
    if atr14 <= 0:
        return []

    entry = h1_close
    recent_swing_lookback = 8
    recent = h1_candles[-recent_swing_lookback:]
    if direction == "LONG":
        swing = min(_safe_float(c.get("low"), entry) for c in recent)
        atr_stop = entry - (1.5 * atr14)
        stop_loss = min(swing, atr_stop)
    else:
        swing = max(_safe_float(c.get("high"), entry) for c in recent)
        atr_stop = entry + (1.5 * atr14)
        stop_loss = max(swing, atr_stop)

    risk = abs(entry - stop_loss)
    if risk <= 0:
        return []

    rr = 2.0 if _is_crypto(symbol) else 1.5
    if direction == "LONG":
        take_profit = entry + (rr * risk)
    else:
        take_profit = entry - (rr * risk)

    confidence = 0.70
    if direction == "LONG" and curr_rsi >= 54:
        confidence += 0.05
    if direction == "SHORT" and curr_rsi <= 46:
        confidence += 0.05
    if abs(h4_close - h4_ema200) / h4_close >= 0.004:
        confidence += 0.03
    confidence = min(0.90, max(0.65, confidence))

    strategy_name = "Institutional Momentum Pulse"
    reasoning = (
        f"IMP {direction}: 1D/4H bias aligned with EMA200, H1 pullback to EMA50, "
        f"POC support/resistance check passed, candle trigger confirmed, RSI crossed 50."
    )

    return [
        {
            "asset": symbol,
            "symbol": symbol,
            "timeframe": "1h",
            "direction": direction,
            "entry": float(entry),
            "stop_loss": float(stop_loss),
            "take_profit": float(take_profit),
            "targets": [float(take_profit)],
            "confidence": float(confidence),
            "strength": float(confidence),
            "rr_ratio": float(rr),
            "strategy_name": strategy_name,
            "strategy_group": "impulse",
            "reasoning": reasoning,
            "atr": float(atr14),
            "imp_poc": float(poc),
            "imp_h4_ema200": float(h4_ema200),
            "imp_h1_ema50": float(h1_ema50),
            "imp_rsi_prev": float(prev_rsi),
            "imp_rsi_curr": float(curr_rsi),
        }
    ]
