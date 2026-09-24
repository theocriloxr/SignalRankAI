import os
import hashlib


FEATURE_ENCODING_VERSION = "stable-sha256-v1"


def stable_category_to_int(value, buckets=1024):
    """Deterministic categorical encoder shared by training and inference."""
    raw = str(value or "").strip().lower().encode("utf-8")
    digest = hashlib.sha256(raw).digest()
    return int.from_bytes(digest[:4], "big") % int(buckets)


def direction_to_int(value):
    return stable_category_to_int(str(value or "long").lower())


def regime_model_to_int(value):
    return stable_category_to_int(str(value or "neutral").lower())


def strategy_model_to_int(value):
    return stable_category_to_int(str(value or "unknown").lower())


def build_model_feature_values(signal, market_data=None):
    """Build the exact v3 model feature contract for one inference candidate."""
    signal = dict(signal or {})
    market_data = market_data or {}
    tf = str(signal.get("timeframe") or "1h").lower()
    tf_data = market_data.get(tf) or {}
    candles = tf_data.get("candles") or []
    closes = [_safe_float(x.get("close"), 0.0) for x in candles if isinstance(x, dict) and x.get("close") is not None]
    highs = [_safe_float(x.get("high"), 0.0) for x in candles if isinstance(x, dict) and x.get("high") is not None]
    lows = [_safe_float(x.get("low"), 0.0) for x in candles if isinstance(x, dict) and x.get("low") is not None]
    vols = [_safe_float(x.get("volume"), 0.0) for x in candles if isinstance(x, dict) and x.get("volume") is not None]
    macro = dict(market_data.get("_macro") or signal.get("_macro") or {})

    score = _safe_float(signal.get("score"), 0.0)
    entry = _safe_float(signal.get("entry"), 0.0)
    stop = _safe_float(signal.get("stop_loss") or signal.get("stop"), 0.0)
    target = signal.get("take_profit") or signal.get("tp") or 0.0
    if isinstance(target, (list, tuple)):
        target = target[0] if target else 0.0
    if isinstance(target, dict):
        target = next(iter(target.values()), 0.0)
    target = _safe_float(target, 0.0)
    rr = _safe_float(signal.get("rr_ratio") or signal.get("rr_estimate") or signal.get("rr"), 1.0)
    strength = _safe_float(signal.get("strength") or signal.get("confidence"), 0.0)
    if strength > 1.0:
        strength /= 100.0

    vel3 = _safe_float(signal.get("price_velocity_3"), _pct_change(closes, 3))
    vel5 = _safe_float(signal.get("price_velocity_5"), _pct_change(closes, 5))
    vel10 = _safe_float(signal.get("price_velocity_10"), _pct_change(closes, 10))
    atr14 = _atr(highs, lows, closes, 14)
    atr50 = _atr(highs, lows, closes, 50)
    atr_rel = _safe_float(signal.get("atr_rel"), (atr14 / closes[-1]) if closes and closes[-1] > 0 else 0.0)
    atr_regime = _safe_float(signal.get("atr_regime"), (atr14 / atr50) if atr50 > 0 else 0.0)
    rel_vol = 0.0
    if len(vols) >= 21:
        baseline = sum(vols[-21:-1]) / 20.0
        rel_vol = (vols[-1] / baseline) if baseline > 0 else 0.0
    rel_vol = _safe_float(signal.get("relative_volume"), rel_vol)

    price_range = abs(target - entry) / (entry + 1e-6) if entry > 0 else 0.0
    risk_amount = abs(entry - stop) / (entry + 1e-6) if entry > 0 else 0.0
    direction = str(signal.get("direction") or "long").lower()
    strategy = str(signal.get("strategy_name") or signal.get("strategy") or "unknown").lower()
    regime = str(signal.get("regime") or "neutral").lower()
    asset = str(signal.get("asset") or signal.get("symbol") or "").upper()

    def mv(name, default=0.0):
        return _safe_float(signal.get(name), _safe_float(macro.get(name), default))

    return {
        "score_normalized": score / 100.0,
        "risk_reward_ratio": rr,
        "price_range": price_range,
        "risk_amount": risk_amount,
        "spread_ratio": risk_amount / (price_range + 1e-6),
        "strength_normalized": strength,
        "direction_enc": float(direction_to_int(direction)),
        "regime_enc": float(regime_model_to_int(regime)),
        "strategy_enc": float(strategy_model_to_int(strategy)),
        "high_score": 1.0 if score >= 75 else 0.0,
        "medium_score": 1.0 if 60 <= score < 75 else 0.0,
        "is_long": 1.0 if direction == "long" else 0.0,
        "asset_class_enc": _safe_float(signal.get("asset_class_enc"), _asset_class_to_int(asset)),
        "price_velocity_3": vel3,
        "price_velocity_5": vel5,
        "price_velocity_10": vel10,
        "price_acceleration_3_10": _safe_float(signal.get("price_acceleration_3_10"), vel3 - vel10),
        "velocity_abs_3": abs(vel3),
        "velocity_abs_10": abs(vel10),
        "atr_rel": atr_rel,
        "atr_regime_clamped": max(0.0, min(5.0, atr_regime)),
        "relative_volume_clamped": max(0.0, min(10.0, rel_vol)),
        "mtf_4h_trend": _safe_float(signal.get("mtf_4h_trend"), _mtf_trend(market_data, "4h")),
        "mtf_1d_trend": _safe_float(signal.get("mtf_1d_trend"), _mtf_trend(market_data, "1d")),
        "funding_rate": mv("funding_rate"),
        "open_interest_change": mv("open_interest_change"),
        "dxy_trend": mv("dxy_trend"),
        "vix_trend": mv("vix_trend"),
        "us10y_trend": mv("us10y_trend"),
        "yield_spread": mv("yield_spread"),
        "minutes_since_high_impact_news": mv("minutes_since_high_impact_news"),
        "minutes_until_high_impact_news": mv("minutes_until_high_impact_news"),
        "news_event_impact_score": mv("news_event_impact_score"),
        "spx_trend": mv("spx_trend"),
        "btc_corr": mv("btc_corr"),
    }


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


def _asset_class_to_int(asset: str) -> int:
    a = (asset or "").upper().strip()
    if a.endswith(("USDT", "USDC", "BUSD")) or len(a) > 6 and a.endswith("USD"):
        return 0
    if len(a.replace("/", "").replace("-", "")) == 6:
        return 1
    if any(k in a for k in ("XAU", "XAG", "XPT", "XPD", "WTI", "BRENT", "OIL", "GOLD", "SILVER", "COPPER")):
        return 2
    return 3

def extract_features(signal, market_data):
    tf = signal.get("timeframe")
    tf_data = (market_data or {}).get(tf) or {}
    ind = (tf_data or {}).get("indicators") or {}
    bb = (ind or {}).get("bollinger") or {}
    macro = (market_data or {}).get("_macro") or {}

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
    confluence_total = _safe_float(signal.get("confluence_total"))
    if confluence_total is None:
        confluence_total = _safe_float(os.getenv("CONFLUENCE_TOTAL"))
    if confluence_total is None:
        drivers = signal.get("confluence_drivers") or signal.get("drivers") or []
        if isinstance(drivers, (list, tuple)) and drivers:
            confluence_total = float(len(drivers))
    confluence_norm = (confluence_score / confluence_total) if confluence_total and confluence_total > 0 else 0.0

    features = {
        "rsi": float(signal.get("rsi") if signal.get("rsi") is not None else (ind.get("rsi") or 0)),
        "atr": float(signal.get("atr") if signal.get("atr") is not None else (ind.get("atr") or 0)),
        "trend_strength": float(signal.get("trend_strength") if signal.get("trend_strength") is not None else (ind.get("adx") or 0)),
        "volatility": float(signal.get("volatility") if signal.get("volatility") is not None else (bb.get("width") or ind.get("bollinger_width") or 0)),
        "rr": float(signal.get("rr") if signal.get("rr") is not None else (signal.get("rr_ratio") or 0)),
        "timeframe": timeframe_to_int(tf),
        "strategy_id": strategy_to_int(signal.get("strategy") or signal.get("strategy_name") or ""),
        "regime": regime_to_int(signal.get("regime", "")),
        "news_sentiment": float(market_data.get("news_sentiment", 0.0)),
        "asset_class_enc": float(signal.get("asset_class_enc") if signal.get("asset_class_enc") is not None else _asset_class_to_int(str(signal.get("asset") or ""))),
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
        "dxy_trend": float(signal.get("dxy_trend") if signal.get("dxy_trend") is not None else macro.get("dxy_trend") or 0.0),
        "vix_trend": float(signal.get("vix_trend") if signal.get("vix_trend") is not None else macro.get("vix_trend") or 0.0),
        "us10y_trend": float(signal.get("us10y_trend") if signal.get("us10y_trend") is not None else macro.get("us10y_trend") or 0.0),
        "yield_spread": float(signal.get("yield_spread") if signal.get("yield_spread") is not None else macro.get("yield_spread") or 0.0),
        "minutes_since_high_impact_news": float(signal.get("minutes_since_high_impact_news") if signal.get("minutes_since_high_impact_news") is not None else macro.get("minutes_since_high_impact_news") or 0.0),
        "minutes_until_high_impact_news": float(signal.get("minutes_until_high_impact_news") if signal.get("minutes_until_high_impact_news") is not None else macro.get("minutes_until_high_impact_news") or 0.0),
        "news_event_impact_score": float(signal.get("news_event_impact_score") if signal.get("news_event_impact_score") is not None else macro.get("news_event_impact_score") or 0.0),
        "exchange_net_flow": float(signal.get("exchange_net_flow") if signal.get("exchange_net_flow") is not None else macro.get("exchange_net_flow") or 0.0),
        "exchange_inflow": float(signal.get("exchange_inflow") if signal.get("exchange_inflow") is not None else macro.get("exchange_inflow") or 0.0),
        "exchange_outflow": float(signal.get("exchange_outflow") if signal.get("exchange_outflow") is not None else macro.get("exchange_outflow") or 0.0),
        "liquidation_heatmap_score": float(signal.get("liquidation_heatmap_score") if signal.get("liquidation_heatmap_score") is not None else macro.get("liquidation_heatmap_score") or 0.0),
        "liquidation_heatmap_density": float(signal.get("liquidation_heatmap_density") if signal.get("liquidation_heatmap_density") is not None else macro.get("liquidation_heatmap_density") or 0.0),
        "onchain_source_flag": float(signal.get("onchain_source_flag") if signal.get("onchain_source_flag") is not None else (1.0 if macro.get("onchain_source") not in (None, "", "none") else 0.0)),
        "spx_trend": float(signal.get("spx_trend") if signal.get("spx_trend") is not None else macro.get("spx_trend") or 0.0),
        "btc_corr": float(signal.get("btc_corr") if signal.get("btc_corr") is not None else macro.get("btc_corr") or 0.0),
    }
    # Canonical model fields override any legacy aliases above so every inference
    # path uses the same v3 semantics and categorical encoding as training.
    features.update(build_model_feature_values(signal, market_data))
    return features
