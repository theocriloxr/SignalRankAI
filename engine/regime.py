def detect_market_regime(market_data):
    if not isinstance(market_data, dict):
        raise ValueError("market_data must be a dict")
    ht_tf = market_data.get('4h', {})
    indicators = ht_tf.get('indicators', {})
    adx = indicators.get('adx', 0)
    atr = indicators.get('atr', 0)
    bb_width = indicators.get('bollinger', {}).get('width', 0)
    # Placeholder logic
    if adx > 25 and atr:  # atr increasing logic not implemented
        return "TRENDING"
    if bb_width < 0.05 and adx < 20:
        return "RANGING"
    if atr > 2:  # 'very high' placeholder
        return "VOLATILE"
    return "NEUTRAL"
