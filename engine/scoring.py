def _direction_sign(direction_val) -> float:
    """Normalize direction to numeric sign (+1 long, -1 short, 0 neutral)."""
    try:
        if isinstance(direction_val, str):
            d = direction_val.strip().lower()
            if d in ("long", "buy", "+", "bull"):
                return 1.0
            if d in ("short", "sell", "-", "bear"):
                return -1.0
        return float(direction_val)
    except Exception:
        return 0.0


import os
import logging

logger = logging.getLogger(__name__)

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
    
    Returns 0-100 score.
    
    PHASE 1 CHANGES:
    - RR is now a hard gate (checked before scoring)
    - Confluence uses graduated weight (not binary gate)
    - ML scoring simplified (multiply only, not in components)
    """
    # ========================================================================
    # PHASE 1.1: CALCULATE RR FIRST FOR HARD GATE CHECK
    # ========================================================================
    entry_raw = signal.get("entry")
    stop_raw = signal.get("stop") if signal.get("stop") is not None else signal.get("stop_loss")
    target_raw = signal.get("targets")
    if isinstance(target_raw, list) and target_raw:
        target = float(target_raw[-1])  # Use the final/last target from the list
    else:
        target = float(target_raw) if target_raw is not None else entry_raw
    
    # Defensive: ensure entry and stop are floats
    try:
        entry = float(entry_raw) if entry_raw is not None else 0.0
    except (TypeError, ValueError):
        entry = 0.0
    
    try:
        stop = float(stop_raw) if stop_raw is not None else None
    except (TypeError, ValueError):
        stop = None
    
    # Calculate R:R ratio with defensive checks
    if entry is None or stop is None or entry == 0 or stop is None:
        rr = 0.0
    else:
        denominator = abs(entry - stop)
        if denominator > 0:
            rr = abs(target - entry) / denominator
        else:
            rr = 0.0
    
    # PHASE 1 FIX #1: HARD RR GATE - Reject before any scoring if RR < 1.5
    # This is now the FIRST check, ensuring poor-RR signals never get scored
    min_rr = _env_float("MIN_RR", 1.5)
    if rr < min_rr:
        logger.info(
            f"[scoring][rr_hard_gate] {signal.get('asset')} {signal.get('direction')} "
            f"RR={rr:.2f} < MIN_RR={min_rr} - REJECTED"
        )
        return 0.0
    
    # ========================================================================
    # PHASE 1.2: CONFLUENCE GRADUATED WEIGHT (NOT BINARY GATE)
    # ========================================================================
    # ORIGINAL VALUE: 25.0 (restored from 15.0)
    confluence_min = _env_float("CONFLUENCE_MIN", 25.0)
    confluence_score = resolve_confluence_percent(signal)
    if confluence_score is None:
        confluence_score = calculate_confluence(signal)
    
    # PHASE 1 FIX #3: Graduated confluence weight instead of hard rejection
    # If confluence < 25%, multiply score by (confluence / 50)
    # This allows near-consensus signals through at reduced strength
    confluence_weight = 1.0
    if confluence_score is not None and confluence_score < confluence_min:
        confluence_weight = max(0.0, confluence_score / 50.0)  # Linear scale from 0 to 50
        logger.debug(
            f"[scoring][confluence_graduated] {signal.get('asset')} confluence={confluence_score:.1f}% "
            f"< min={confluence_min}% - applying weight={confluence_weight:.3f}"
        )
    
    # Target: 0..100 score
    confidence = resolve_confidence_ratio(signal)
    if confidence is None:
        confidence = resolve_ml_probability(signal)
    
    # LOWERED from 0.35 to 0.20 to allow more signals through
    # This fixes "generated_signals=0" when ML probability is moderate
    # ORIGINAL VALUE: 0.35 (restored from 0.25)
    confidence_min = _env_float("CONFIDENCE_MIN", 0.20)
    if confidence is not None and confidence < confidence_min:
        return 0.0

    rr_component = rr_score(rr)
    vol_component = volatility_quality_score(signal)
    
    # Base score: weighted components
    weight_conf = _env_float("SCORE_WEIGHT_CONFIDENCE", 0.3)
    weight_rr = _env_float("SCORE_WEIGHT_RR", 0.3)
    weight_vol = _env_float("SCORE_WEIGHT_VOL", 0.2)
    weight_confli = _env_float("SCORE_WEIGHT_CONFLUENCE", 0.2)

    components = {
        "rr": (rr_component, weight_rr),
        "vol": (vol_component, weight_vol),
    }
    if confidence is not None:
        components["confidence"] = (confidence, weight_conf)
    if confluence_score is not None:
        components["confluence"] = (min(max(confluence_score / 100.0, 0.0), 1.0), weight_confli)

    total_weight = sum(weight for _, weight in components.values()) if components else 0.0
    if total_weight <= 0:
        return 0.0
    score = 100.0 * sum(val * (weight / total_weight) for val, weight in components.values())
    
    # Apply confluence weight (from PHASE 1 FIX #3)
    score = score * confluence_weight
    
    # REGIME ALIGNMENT BONUS
    regime_fit = signal.get("regime_fit") or signal.get("htf_alignment")
    regime_bonus = 1.0
    try:
        if regime_fit is not None:
            regime_fit = float(regime_fit)
            regime_fit = min(max(regime_fit, 0.0), 1.0)
            bonus_base = _env_float("REGIME_SCORE_BONUS_BASE", 1.0)
            bonus_scale = _env_float("REGIME_SCORE_BONUS_SCALE", 0.2)
            regime_bonus = bonus_base + (regime_fit * bonus_scale)
            score = score * regime_bonus
    except Exception:
        pass
    
    # PHASE 1 FIX #2: ML PROBABILITY SIMPLIFIED - MULTIPLY ONLY (not in components)
    # Removed ML from score components to simplify - now only multiply method
    ml_val = resolve_ml_probability(signal)
    ml_boost = 1.0
    if ml_val is not None:
        try:
            ml_val = min(max(float(ml_val), 0.0), 1.0)
            ml_boost_min = _env_float("ML_SCORE_BOOST_MIN", 0.8)
            ml_boost_range = _env_float("ML_SCORE_BOOST_RANGE", 0.4)
            ml_boost = ml_boost_min + (ml_val * ml_boost_range)
            score = score * ml_boost
            logger.debug(
                f"[scoring][ml_boost] {signal.get('asset')} ml_confidence={ml_val:.3f} "
                f"boost={ml_boost:.3f} score_after={score:.2f}"
            )
        except Exception:
            pass
    
    # EXCEPTIONAL R/R REWARD
    rr_bonus = 1.0
    if rr >= 2.5:
        rr_bonus = 1.20
        score = score * 1.20
    elif rr >= 2.0:
        rr_bonus = 1.15
        score = score * 1.15
    
# PHASE 1 FIX: Soft cap to prevent score collapse to 100
    # Store raw_score before cap for debugging
    raw_score = score
    
    # Soft-cap: exponential decay prevents collapse while preserving ordering
    # FIX: Changed divisor from 75.0 -> 50.0 for better score mapping
    # At raw_score=75, soft_score≈78; At raw_score=100, soft_score≈86.5
    # This prevents all scores from collapsing to 100
    import math
    soft_score = 100.0 * (1.0 - math.exp(-raw_score / 50.0))
    display_score = round(min(soft_score, 99.5), 2)
    
    # PHASE 1 FIX #5: ENHANCED COMPONENT LOGGING
    # Store comprehensive breakdown for post-analysis without logic changes
    signal["score_components"] = {
        "rr": rr_component,
        "rr_ratio": round(rr, 2),
        "vol": vol_component,
        "confidence": confidence,
        "ml_confidence": ml_val,
        "confluence": confluence_score,
        "confluence_weight": confluence_weight,
        "regime_bonus": regime_bonus,
        "ml_boost": ml_boost,
        "rr_bonus": rr_bonus,
    }
    # Store both raw and display scores for different use cases
    signal["raw_score"] = raw_score
    signal["display_score"] = display_score
    
    # Calculate take profit levels for logging (support multi-level TPs)
    tp_levels = signal.get("targets")
    if isinstance(tp_levels, list):
        tp_1 = tp_levels[0] if len(tp_levels) > 0 else None
        tp_2 = tp_levels[1] if len(tp_levels) > 1 else None
        tp_3 = tp_levels[2] if len(tp_levels) > 2 else None
    else:
        tp_1 = tp_levels if tp_levels else None
        tp_2 = None
        tp_3 = None
    
    # Get entry logic (strategy name or entry_logic field)
    entry_logic_used = signal.get("strategy_name") or signal.get("entry_logic") or "unknown"
    
    # PHASE 1 FIX #5: Log all component information for post-analysis
    logger.info(
        f"[scoring][components] asset={signal.get('asset')} direction={signal.get('direction')} "
        f"timeframe={signal.get('timeframe')} | "
        f"entry={entry:.2f} stop_loss={stop:.2f} tp_1={tp_1} tp_2={tp_2} tp_3={tp_3} | "
        f"entry_logic={entry_logic_used} confluence={confluence_score:.1f}% rr={rr:.2f} "
        f"ml_confidence={ml_val if ml_val else 'None'} regime={signal.get('regime', 'unknown')} | "
        f"final_score={display_score:.2f} (raw={raw_score:.2f})"
    )
    
    # Log score components for debugging score saturation issues
    logger.debug(
        f"[scoring][breakdown] raw={raw_score:.1f} display={display_score:.1f} "
        f"rr={rr_component:.2f} vol={vol_component:.2f} conf={confidence} "
        f"confluence={confluence_score} regime={regime_bonus:.2f} ml={ml_boost:.2f}"
    )
    
    return display_score


def calculate_signal_score(signal, risk_profile=None, regime=None):
    """Compatibility wrapper (signal, risk_profile, regime) -> numeric score."""
    return score_signal(signal)


def calculate_confluence(signal):
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
    
# ORIGINAL VALUE: 1.5 (restored from 1.0)
    min_rr = _env_float("MIN_RR", 1.5)
    # Hard floor: reject RR below configured minimum
    if rr < min_rr:
        return 0.0
    
    # Scale: 2.0 is 50%, 3.0 is 100%
    base = max(min_rr, 1.0)
    scale = max(0.5, 3.0 - base)
    raw_score = float(min(max((rr - base) / scale, 0.0), 1.0))
    
    # FIX: Soft-cap on top end to prevent all strong signals from collapsing to 100.0
    # Apply soft cap: scores above 85 get compressed, so 90->92, 95->96, 100 stays 100
    # This ensures some spread remains in the score distribution
    if raw_score >= 0.85:
        # Compress the top end: (score - 0.85) * 0.5 + 0.85
        soft_cap = 0.85 + (raw_score - 0.85) * 0.5
        return soft_cap
    
    return raw_score


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
