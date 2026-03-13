def timeframe_to_int(tf):
    mapping = {"5m": 1, "15m": 2, "1h": 3, "4h": 4, "1d": 5}
    return mapping.get(tf, 0)

def strategy_to_int(name):
    mapping = {"ATR Breakout": 1, "EMA Trend": 2, "Structure Bull": 3, "RSI Momentum": 4}
    return mapping.get(name, 0)

def regime_to_int(regime):
    mapping = {"TRENDING": 1, "RANGING": 2, "VOLATILE": 3}
    return mapping.get(regime, 0)


def _safe_float(v, default=0.0):
    try:
        return float(v)
    except Exception:
        return float(default)


def _pct_change(closes, n):
    try:
        if len(closes) <= n:
            return 0.0
        prev = float(closes[-(n + 1)])
        cur = float(closes[-1])
        if prev <= 0:
            return 0.0
        return (cur - prev) / prev
    except Exception:
        return 0.0


def _atr(highs, lows, closes, period=14):
    try:
        if len(closes) < period + 1:
            return 0.0
        trs = []
        for i in range(1, len(closes)):
            h = float(highs[i])
            l = float(lows[i])
            pc = float(closes[i - 1])
            trs.append(max(h - l, abs(h - pc), abs(l - pc)))
        tail = trs[-period:] if len(trs) >= period else trs
        return sum(tail) / max(1, len(tail))
    except Exception:
        return 0.0


def _mtf_trend(market_data, tf: str) -> float:
    try:
        candles = ((market_data or {}).get(tf) or {}).get("candles") or []
        closes = [
            _safe_float(c.get("close"), 0.0)
            for c in candles
            if isinstance(c, dict) and c.get("close") is not None
        ]
        if len(closes) < 50:
            return 0.0
        sma20 = sum(closes[-20:]) / 20.0
        sma50 = sum(closes[-50:]) / 50.0
        if sma20 > sma50:
            return 1.0
        if sma20 < sma50:
            return -1.0
        return 0.0
    except Exception:
        return 0.0

def extract_features(signal, market_data):
    tf = signal.get("timeframe")
    tf_data = (market_data or {}).get(tf) or {}
    ind = (tf_data or {}).get("indicators") or {}
    bb = (ind or {}).get("bollinger") or {}

    candles = (tf_data or {}).get("candles") or []
    closes = [
        _safe_float(c.get("close"), 0.0)
        for c in candles
        if isinstance(c, dict) and c.get("close") is not None
    ]
    highs = [
        _safe_float(c.get("high"), 0.0)
        for c in candles
        if isinstance(c, dict) and c.get("high") is not None
    ]
    lows = [
        _safe_float(c.get("low"), 0.0)
        for c in candles
        if isinstance(c, dict) and c.get("low") is not None
    ]
    vols = [
        _safe_float(c.get("volume"), 0.0)
        for c in candles
        if isinstance(c, dict) and c.get("volume") is not None
    ]

    vel3 = _pct_change(closes, 3)
    vel5 = _pct_change(closes, 5)
    vel10 = _pct_change(closes, 10)
    atr14 = _atr(highs, lows, closes, period=14)
    atr50 = _atr(highs, lows, closes, period=50)
    atr_regime = (atr14 / atr50) if atr50 > 0 else 0.0
    rel_vol = 0.0
    if len(vols) >= 21:
        ma20v = sum(vols[-21:-1]) / 20.0
        rel_vol = (vols[-1] / ma20v) if ma20v > 0 else 0.0

    confluence_score = _safe_float(signal.get("confluence_vote_count") or signal.get("confluence_score"), 0.0)
    confluence_total = _safe_float(signal.get("confluence_total"), 15.0)
    confluence_norm = (confluence_score / confluence_total) if confluence_total > 0 else 0.0

    return {
        "rsi": float(signal.get("rsi") if signal.get("rsi") is not None else (ind.get("rsi") or 0)),
        "atr": float(signal.get("atr") if signal.get("atr") is not None else (ind.get("atr") or 0)),
        "trend_strength": float(signal.get("trend_strength") if signal.get("trend_strength") is not None else (ind.get("adx") or 0)),
        "volatility": float(signal.get("volatility") if signal.get("volatility") is not None else (bb.get("width") or ind.get("bollinger_width") or 0)),
        "rr": float(signal.get("rr") if signal.get("rr") is not None else (signal.get("rr_ratio") or 0)),
        "timeframe": timeframe_to_int(tf),
        "strategy_id": strategy_to_int(signal.get("strategy") or signal.get("strategy_name") or ""),
        "regime": regime_to_int(signal.get("regime", "")),
        "news_sentiment": float(market_data.get("news_sentiment", 0.0)),
        # Candle-derived momentum context
        "price_velocity_3": float(signal.get("price_velocity_3") if signal.get("price_velocity_3") is not None else vel3),
        "price_velocity_5": float(signal.get("price_velocity_5") if signal.get("price_velocity_5") is not None else vel5),
        "price_velocity_10": float(signal.get("price_velocity_10") if signal.get("price_velocity_10") is not None else vel10),
        "price_acceleration_3_10": float(signal.get("price_acceleration_3_10") if signal.get("price_acceleration_3_10") is not None else (vel3 - vel10)),
        # Volatility context
        "atr_rel": float(signal.get("atr_rel") if signal.get("atr_rel") is not None else ((atr14 / closes[-1]) if closes and closes[-1] > 0 else 0.0)),
        "atr_regime": float(signal.get("atr_regime") if signal.get("atr_regime") is not None else atr_regime),
        # Volume context
        "relative_volume": float(signal.get("relative_volume") if signal.get("relative_volume") is not None else rel_vol),
        # MTF alignment (macro trend inputs)
        "mtf_4h_trend": float(signal.get("mtf_4h_trend") if signal.get("mtf_4h_trend") is not None else _mtf_trend(market_data, "4h")),
        "mtf_1d_trend": float(signal.get("mtf_1d_trend") if signal.get("mtf_1d_trend") is not None else _mtf_trend(market_data, "1d")),
        # Confluence/meta-model context
        "confluence_score_norm": float(signal.get("confluence_score_norm") if signal.get("confluence_score_norm") is not None else confluence_norm),
        "long_votes_norm": float(signal.get("long_votes_norm") if signal.get("long_votes_norm") is not None else (_safe_float(signal.get("long_votes"), 0.0) / max(confluence_total, 1.0))),
        "short_votes_norm": float(signal.get("short_votes_norm") if signal.get("short_votes_norm") is not None else (_safe_float(signal.get("short_votes"), 0.0) / max(confluence_total, 1.0))),
        # Optional alpha generators (if upstream providers inject values)
        "funding_rate": float(signal.get("funding_rate") or 0.0),
        "open_interest_change": float(signal.get("open_interest_change") or 0.0),
        "dxy_trend": float(signal.get("dxy_trend") or 0.0),
        "spx_trend": float(signal.get("spx_trend") or 0.0),
        "btc_corr": float(signal.get("btc_corr") or 0.0),
    }
