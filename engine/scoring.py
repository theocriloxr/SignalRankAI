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


import os

from engine.signal_metrics import (
    resolve_confidence_ratio,
    resolve_confluence_percent,
    resolve_ml_probability,
)


def _env_float(name: str, default: float) -> float:
    try:
        return float((os.getenv(name) or str(default)).strip())
    except Exception:
        return float(default)


def score_signal(signal):
    """Score a signal based on multiple factors with confluence validation.
    
    Requirements for confluence:
    1. Trend alignment (EMA/SMA golden cross or aligned)
    2. Momentum confirmation (RSI + MACD alignment)
    3. Volume confirmation (spike or average volume)
    4. Support/Resistance respect
    5. Market regime fit (trending/ranging)
    
    Returns 0-100 score. Also populates signal with detailed score breakdowns.
    """
    # CONFLUENCE REQUIREMENT: Multiple signals must align
    # LOWERED from 25.0 to 15.0 to allow more signals through (fixes "Zero Signal")
    confluence_min = _env_float("CONFLUENCE_MIN", 15.0)
    confluence_score = resolve_confluence_percent(signal)
    if confluence_score is None:
        confluence_score = calculate_confluence(signal)
    if confluence_score is not None and confluence_score < confluence_min:
        # Log detailed rejection
        signal['score_rejection_reason'] = f'confluence {confluence_score:.1f}% < {confluence_min:.1f}%'
        return 0.0
    
    # Target: 0..100 score
    confidence = resolve_confidence_ratio(signal)
    if confidence is None:
        confidence = resolve_ml_probability(signal)
    
    # LOWERED from 0.35 to 0.25 to allow more signals through (fixes "Zero Signal")
    confidence_min = _env_float("CONFIDENCE_MIN", 0.25)
    if confidence is not None and confidence < confidence_min:
        signal['score_rejection_reason'] = f'confidence {confidence:.2f} < {confidence_min:.2f}'
        return 0.0

    entry = signal.get("entry")
    stop = signal.get("stop") or signal.get("stop_loss")
    target = signal.get("targets", entry)
    rr = abs(target - entry) / abs(entry - stop) if entry and stop and abs(entry - stop) > 0 else 0

    rr_component = rr_score(rr)
    vol_component = volatility_quality_score(signal)
    
    # Base score: weighted components
    weight_conf = _env_float("SCORE_WEIGHT_CONFIDENCE", 0.3)
    weight_rr = _env_float("SCORE_WEIGHT_RR", 0.3)
    weight_vol = _env_float("SCORE_WEIGHT_VOL", 0.2)
    weight_confli = _env_float("SCORE_WEIGHT_CONFLUENCE", 0.2)

    components: dict[str, tuple[float, float]] = {
        "rr": (rr_component, weight_rr),
        "vol": (vol_component, weight_vol),
    }
    if confidence is not None:
        components["confidence"] = (confidence, weight_conf)
    if confluence_score is not None:
        components["confluence"] = (min(max(confluence_score / 100.0, 0.0), 1.0), weight_confli)

    total_weight = sum(weight for _, weight in components.values()) if components else 0.0
    if total_weight <= 0:
        signal['score_rejection_reason'] = 'no_scoring_components'
        return 0.0
    score_raw = 100.0 * sum(val * (weight / total_weight) for val, weight in components.values())
    
    # LOWERED from 1.5 to 1.0 to allow more signals through (fixes "Zero Signal")
    min_rr = _env_float("MIN_RR", 1.0)
    # Hard rejection for poor R/R
    if rr < min_rr:
        signal['score_rejection_reason'] = f'RR {rr:.2f} < {min_rr:.2f}'
        return 0.0
    
    # === FIX PHASE 1: Log raw scores before any normalization/bonuses ===
    # Store pre-normalized score components for transparency
    signal['score_components'] = {
        'rr': round(rr_component * 100, 2),  # RR component contribution
        'volatility': round(vol_component * 100, 2),  # Vol component contribution
    }
    if confidence is not None:
        signal['score_components']['confidence'] = round(confidence * 100, 2)
    if confluence_score is not None:
        signal['score_components']['confluence'] = round(confluence_score, 2)
    
    # === Log raw total before bonuses ===
    signal['score_raw'] = round(score_raw, 2)
    signal['score_pre_threshold'] = round(score_raw, 2)
    
    # === FIX PHASE 1: Track individual bonuses for transparency ===
    bonuses_applied = []
    
    # REGIME ALIGNMENT BONUS (additive, not multiplicative to preserve normalization)
    regime_fit = signal.get("regime_fit") or signal.get("htf_alignment")
    regime_bonus = 1.0
    try:
        if regime_fit is not None:
            regime_fit = float(regime_fit)
            regime_fit = min(max(regime_fit, 0.0), 1.0)
            bonus_base = _env_float("REGIME_SCORE_BONUS_BASE", 1.0)
            bonus_scale = _env_float("REGIME_SCORE_BONUS_SCALE", 0.2)
            regime_bonus = bonus_base + (regime_fit * bonus_scale)
            # Apply as additive bonus instead of multiplicative to preserve normalization
            regime_bonus_pct = (regime_bonus - 1.0) * 100
            score_raw = score_raw + (score_raw * regime_bonus_pct / 100)
            bonuses_applied.append(f'regime:+{regime_bonus_pct:.1f}%')
    except Exception:
        pass
    
    signal['score_after_regime'] = round(score_raw, 2)
    
    # ML PROBABILITY BOOST (additive to preserve normalization)
    ml_val = resolve_ml_probability(signal)
    ml_boost = 1.0
    if ml_val is not None:
        try:
            ml_val = min(max(float(ml_val), 0.0), 1.0)
            ml_boost_min = _env_float("ML_SCORE_BOOST_MIN", 0.8)
            ml_boost_range = _env_float("ML_SCORE_BOOST_RANGE", 0.4)
            ml_boost = ml_boost_min + (ml_val * ml_boost_range)
            # Apply as additive bonus instead of multiplicative
            ml_boost_pct = (ml_boost - 1.0) * 100
            score_raw = score_raw + (score_raw * ml_boost_pct / 100)
            bonuses_applied.append(f'ml:+{ml_boost_pct:.1f}%')
        except Exception:
            pass
    
    signal['score_after_ml'] = round(score_raw, 2)
    
    # EXCEPTIONAL R/R REWARD (additive to preserve normalization)
    if rr >= 2.5:
        score_raw = score_raw + (score_raw * 0.20)  # +20%
        bonuses_applied.append('rr_exceptional:+20%')
    elif rr >= 2.0:
        score_raw = score_raw + (score_raw * 0.15)  # +15%
        bonuses_applied.append('rr_good:+15%')
    
    # Store all bonus info for transparency
    signal['bonuses_applied'] = bonuses_applied
    
    # Final score - ensure it stays in 0-100 range (normalize if over)
    score_final = round(min(score_raw, 100.0), 2)
    signal['score_post_threshold'] = score_final
    
    # Return the final normalized score (0-100)
    return score_final


def calculate_signal_score(signal, risk_profile=None, regime=None):
    """Compatibility wrapper (signal, risk_profile, regime) -> numeric score."""
    return score_signal(signal)


def calculate_confluence(signal: dict) -> float | None:
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
    total_checks = 0
    
    # 1. Trend alignment
    trend_ema = signal.get("trend_ema")
    trend_sma = signal.get("trend_sma")
    direction = _direction_sign(signal.get("direction", 0))

    if trend_ema is not None and trend_sma is not None:
        total_checks += 1
        if (direction > 0 and trend_ema > 0 and trend_sma > 0) or \
           (direction < 0 and trend_ema < 0 and trend_sma < 0):
            confirmations += 1
    
    # 2. Momentum confirmation
    rsi = signal.get("rsi")
    macd_trend = signal.get("macd_trend")

    if rsi is not None and macd_trend is not None:
        total_checks += 1
        if direction > 0:
            # For longs: RSI > 50 (upward momentum) and MACD positive
            if rsi > 50 and macd_trend > 0:
                confirmations += 1
        elif direction < 0:
            # For shorts: RSI < 50 (downward momentum) and MACD negative
            if rsi < 50 and macd_trend < 0:
                confirmations += 1
    
    # 3. Volume confirmation
    volume_ratio = signal.get("volume_ratio")
    if volume_ratio is not None:
        total_checks += 1
        if volume_ratio > _env_float("VOLUME_RATIO_MIN", 1.2):  # Above average volume
            confirmations += 1
    
    # 4. Support/Resistance respect
    nearest_support = signal.get("nearest_support")
    nearest_resistance = signal.get("nearest_resistance")
    current_price = signal.get("close_price")

    if current_price is not None and (nearest_support is not None or nearest_resistance is not None):
        total_checks += 1
        if nearest_support is not None and direction > 0 and current_price > nearest_support:
            confirmations += 1  # Price is above support
        elif nearest_resistance is not None and direction < 0 and current_price < nearest_resistance:
            confirmations += 1  # Price is below resistance
    
    # 5. Market regime alignment
    regime = signal.get("regime")
    adx_strength = signal.get("adx_trend")

    if regime in ("trending", "ranging") and adx_strength in ("weak", "moderate", "strong"):
        total_checks += 1
        if regime == "trending" and adx_strength in ("moderate", "strong"):
            confirmations += 1
        elif regime == "ranging" and adx_strength == "weak":
            confirmations += 1
    
    # Calculate percentage
    if total_checks <= 0:
        return None
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
    
    # LOWERED from 1.5 to 1.0 to allow more signals through (fixes "Zero Signal")
    min_rr = _env_float("MIN_RR", 1.0)
    # Hard floor: reject RR below configured minimum
    if rr < min_rr:
        return 0.0
    
    # Scale: 2.0 is 50%, 3.0 is 100%
    base = max(min_rr, 1.0)
    scale = max(0.5, 3.0 - base)
    return float(min(max((rr - base) / scale, 0.0), 1.0))


def htf_alignment_score(signal):
    return float(signal.get("htf_alignment", 0.5) or 0.5)


def regime_fit_score(signal, regime=None):
    return float(signal.get("regime_fit", 0.5) or 0.5)


def volatility_quality_score(signal):
    """Score volatility quality (lower volatility = better conditions = higher score).
    
    LOWERED to allow more signals through (fixes "Zero Signal"):
    - vol <= 0.10 (10%): score 1.0 (ideal low-volatility)
    - vol = 0.15 (15%): score 0.50 (marginal)
    - vol >= 0.20 (20%): score 0.0 (reject - too volatile for reliable execution)
    """
    vol = signal.get("volatility", 0.0)
    try:
        vol = float(vol)
    except Exception:
        vol = 0.0
    
    # LOWERED from 0.16 to 0.20 to allow more signals through
    max_vol = _env_float("MAX_VOLATILITY", 0.20)
    # LOWERED from 0.10 to 0.12 to allow more signals through
    ideal_vol = _env_float("IDEAL_VOLATILITY", 0.12)
    if vol <= ideal_vol:
        return 1.0  # Perfect
    elif vol >= max_vol:
        return 0.0  # Hard reject: too volatile
    else:
        # Linear scale: ideal_vol→max_vol maps to 1.0→0.0
        return float((max_vol - vol) / max(1e-9, (max_vol - ideal_vol)))


def historical_winrate_score(signal):
    return float(signal.get("historical_winrate", 0.5) or 0.5)


def liquidity_score(signal):
    return float(signal.get("liquidity", 0.5) or 0.5)
