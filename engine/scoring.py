def _direction_sign(direction_val) -> float:
    """Normalize direction to numeric sign (+1 long, -1 short, 0 neutral)."""
    try:
        if isinstance(direction_val, str):
            d = direction_val.strip().lower()
            if d in {"long", "buy", "+", "bull"}:
                return 1.0
            if d in {"short", "sell", "-", "bear"}:
                return -1.0
        return float(direction_val)
    except Exception:
        return 0.0


def score_signal(signal):
    """Score a signal based on multiple factors with confluence validation.
    
    Requirements for confluence:
    1. Trend alignment (EMA/SMA golden cross or aligned)
    2. Momentum confirmation (RSI + MACD alignment)
    3. Volume confirmation (spike or average volume)
    4. Support/Resistance respect
    5. Market regime fit (trending/ranging)
    
    Returns 0-100 score.
    """
    # CONFLUENCE REQUIREMENT: Multiple signals must align
    confluence_score = calculate_confluence(signal)
    if confluence_score < 50:  # Need at least 50% confluence
        return 0.0
    
    # Target: 0..100 score
    confidence = float(signal.get("confidence", 0) or 0)
    confidence = min(max(confidence, 0.0), 1.0)
    
    # ULTRA-STRICT QUALITY GATE: Only trade-worthy setups
    if confidence < 0.50:
        return 0.0

    entry = signal.get("entry")
    stop = signal.get("stop") or signal.get("stop_loss")
    target = signal.get("targets", entry)
    rr = abs(target - entry) / abs(entry - stop) if entry and stop and abs(entry - stop) > 0 else 0

    rr_component = rr_score(rr)
    vol_component = volatility_quality_score(signal)
    
    # Base score: weighted components
    score = (confidence * 30.0) + (rr_component * 30.0) + (vol_component * 20.0) + (confluence_score * 0.2)
    
    # Hard rejection for poor R/R (2.0:1 minimum)
    if rr < 2.0:
        return 0.0
    
    # REGIME ALIGNMENT BONUS
    regime_fit = signal.get("regime_fit") or signal.get("htf_alignment") or 0.5
    try:
        regime_fit = float(regime_fit)
        regime_fit = min(max(regime_fit, 0.0), 1.0)
        regime_bonus = 1.0 + (regime_fit * 0.2)
        score = score * regime_bonus
    except Exception:
        pass
    
    # ML PROBABILITY BOOST
    ml_prob = signal.get("ml_probability")
    if ml_prob is not None:
        try:
            ml_val = float(ml_prob)
            ml_val = min(max(ml_val, 0.0), 1.0)
            ml_boost = 0.8 + (ml_val * 0.4)
            score = score * ml_boost
        except Exception:
            pass
    
    # EXCEPTIONAL R/R REWARD
    if rr >= 2.5:
        score = score * 1.20
    elif rr >= 2.0:
        score = score * 1.15
    
    return round(min(score, 100.0), 2)


def calculate_signal_score(signal, risk_profile=None, regime=None):
    """Compatibility wrapper (signal, risk_profile, regime) -> numeric score."""
    return score_signal(signal)


def calculate_confluence(signal: dict) -> float:
    """Calculate confluence score (0-100) based on multiple signal confirmations.
    
    Checks:
    1. Trend alignment (EMA/SMA golden cross)
    2. Momentum confirmation (RSI + MACD)
    3. Volume confirmation (above average)
    4. Support/Resistance respect
    5. Market regime alignment
    
    All factors weighted equally. Score = % of confirmations met.
    """
    confirmations = 0
    total_checks = 5
    
    # 1. Trend alignment
    trend_ema = signal.get("trend_ema", 0)
    trend_sma = signal.get("trend_sma", 0)
    direction = _direction_sign(signal.get("direction", 0))

    if (direction > 0 and trend_ema > 0 and trend_sma > 0) or \
       (direction < 0 and trend_ema < 0 and trend_sma < 0):
        confirmations += 1
    
    # 2. Momentum confirmation
    rsi = signal.get("rsi", 50)
    macd_trend = signal.get("macd_trend", 0)

    if direction > 0:
        # For longs: RSI > 50 (upward momentum) and MACD positive
        if rsi > 50 and macd_trend > 0:
            confirmations += 1
    elif direction < 0:
        # For shorts: RSI < 50 (downward momentum) and MACD negative
        if rsi < 50 and macd_trend < 0:
            confirmations += 1
    
    # 3. Volume confirmation
    volume_ratio = signal.get("volume_ratio", 1.0)
    if volume_ratio > 1.5:  # Above average volume
        confirmations += 1
    
    # 4. Support/Resistance respect
    nearest_support = signal.get("nearest_support", 0)
    nearest_resistance = signal.get("nearest_resistance", 0)
    current_price = signal.get("close_price", 0)
    
    if direction > 0 and current_price > nearest_support:
        confirmations += 1  # Price is above support
    elif direction < 0 and current_price < nearest_resistance:
        confirmations += 1  # Price is below resistance
    
    # 5. Market regime alignment
    regime = signal.get("regime", "unknown")
    adx_strength = signal.get("adx_trend", "weak")
    
    if regime == "trending" and adx_strength in ("moderate", "strong"):
        confirmations += 1
    elif regime == "ranging" and adx_strength == "weak":
        confirmations += 1
    
    # Calculate percentage
    confluence_pct = (confirmations / total_checks) * 100
    return confluence_pct


# --- Helper scoring components (lightweight defaults) ---
def strategy_agreement_score(signal):
    return float(signal.get("agreement", 0.5) or 0.5)


def rr_score(rr):
    """Score risk/reward ratio. Higher RR is better (optimal: 2.5:1 to 3:1).
    
    ULTRA-STRICT for win rate recovery:
    - <2.0:1 = 0.0 (reject - need minimum 2:1 edge)
    - 2.0:1 = 0.50 (minimum acceptable)
    - 2.5:1 = 0.75 (good quality setup)
    - 3.0:1 = 1.00 (excellent - ideal setup)
    - >3.0:1 = 1.0 (capped)
    
    Rationale: 16% win rate requires MASSIVE R/R advantage to be profitable
    """
    try:
        rr = float(rr)
    except Exception:
        rr = 0.0
    
    # Hard floor: reject RR < 2.0 (need 2:1 minimum)
    if rr < 2.0:
        return 0.0
    
    # Scale: 2.0 is 50%, 3.0 is 100%
    return float(min(max((rr - 2.0) / 1.0, 0.0), 1.0))


def htf_alignment_score(signal):
    return float(signal.get("htf_alignment", 0.5) or 0.5)


def regime_fit_score(signal, regime=None):
    return float(signal.get("regime_fit", 0.5) or 0.5)


def volatility_quality_score(signal):
    """Score volatility quality (lower volatility = better conditions = higher score).
    
    ULTRA-STRICT for win rate recovery:
    - vol <= 0.08 (8%): score 1.0 (ideal low-volatility)
    - vol = 0.10 (10%): score 0.50 (marginal)
    - vol >= 0.12 (12%): score 0.0 (reject - too volatile for reliable execution)
    
    Rationale: High volatility = poor fills, slippage, stop hunting
    With 16% win rate, we need PERFECT conditions to turn it around
    """
    vol = signal.get("volatility", 0.0)
    try:
        vol = float(vol)
    except Exception:
        vol = 0.0
    
    if vol <= 0.08:
        return 1.0  # Perfect
    elif vol >= 0.12:
        return 0.0  # Hard reject: too volatile
    else:
        # Linear scale: 0.08→0.12 maps to 1.0→0.0
        return float((0.12 - vol) / (0.12 - 0.08))


def historical_winrate_score(signal):
    return float(signal.get("historical_winrate", 0.5) or 0.5)


def liquidity_score(signal):
    return float(signal.get("liquidity", 0.5) or 0.5)
