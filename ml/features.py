def timeframe_to_int(tf):
    mapping = {"5m": 1, "15m": 2, "1h": 3, "4h": 4, "1d": 5}
    return mapping.get(tf, 0)

def strategy_to_int(name):
    mapping = {"ATR Breakout": 1, "EMA Trend": 2, "Structure Bull": 3, "RSI Momentum": 4}
    return mapping.get(name, 0)

def regime_to_int(regime):
    mapping = {"TRENDING": 1, "RANGING": 2, "VOLATILE": 3}
    return mapping.get(regime, 0)

def extract_features(signal, market_data):
    tf = signal.get("timeframe")
    tf_data = (market_data or {}).get(tf) or {}
    ind = (tf_data or {}).get("indicators") or {}
    bb = (ind or {}).get("bollinger") or {}

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
    }
