def detect_market_regime(market_data):
    """Detect market regime with relaxed thresholds to prevent signal starvation.
    
    FIX: Lowered ADX threshold from 25 to 15 to allow more trending markets through.
    FIX: Added handling for missing/NaN indicators.
    FIX: Changed default from NEUTRAL to TRENDING when uncertain.
    """
    if not isinstance(market_data, dict):
        raise ValueError("market_data must be a dict")
    
    # Try 4h first, fallback to 1h or any available timeframe
    ht_tf = market_data.get('4h', {}) or market_data.get('1h', {}) or {}
    indicators = ht_tf.get('indicators', {}) if isinstance(ht_tf, dict) else {}
    
    # Handle missing or None indicators gracefully
    if not indicators:
        # Try any available timeframe
        for tf_name, tf_data in market_data.items():
            if isinstance(tf_data, dict) and tf_data.get('indicators'):
                indicators = tf_data['indicators']
                break
    
    # Get indicator values with safe defaults
    try:
        adx = float(indicators.get('adx', 0) or 0)
    except (TypeError, ValueError):
        adx = 0
    
    try:
        atr = float(indicators.get('atr', 0) or 0)
    except (TypeError, ValueError):
        atr = 0
        
    bb_data = indicators.get('bollinger', {})
    bb_width = 0
    try:
        bb_width = float(bb_data.get('width', 0) or 0) if bb_data else 0
    except (TypeError, ValueError):
        bb_width = 0
    
    # Get close price for relative ATR calculation
    close_price = 0
    try:
        close_price = float(indicators.get('close_price', 0) or 0)
    except (TypeError, ValueError):
        close_price = 0
    
    # Calculate ATR as percentage of price (normalize across assets)
    atr_pct = (atr / close_price * 100) if close_price > 0 else 0
    
    # Basic regime logic - LOWERED THRESHOLDS to prevent signal starvation
    # ADX > 15 (lowered from 25) to detect more trending markets
    if adx > 15 and atr_pct > 0.5:
        return "TRENDING"
    
    # Low volatility ranging
    if bb_width < 0.05 and adx < 20:
        return "RANGING"
    
    # High volatility - use percentage-based threshold
    if atr_pct > 3.0:  # 'very high' threshold (3% move)
        return "VOLATILE"
    
    # Default to TRENDING instead of NEUTRAL to allow strategies to run
    # This is the key fix - previously returned NEUTRAL which blocked all signals
    return "TRENDING"
