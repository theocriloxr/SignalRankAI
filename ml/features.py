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
    return {
        "rsi": signal.get("rsi", market_data.get("rsi", 0)),
        "atr": signal.get("atr", market_data.get("atr", 0)),
        "trend_strength": signal.get("trend_strength", market_data.get("trend_strength", 0)),
        "volatility": signal.get("volatility", market_data.get("volatility", 0)),
        "rr": signal.get("rr", 0),
        "timeframe": timeframe_to_int(signal.get("timeframe")),
        "strategy_id": strategy_to_int(signal.get("strategy", "")),
        "regime": regime_to_int(signal.get("regime", ""))
    }
