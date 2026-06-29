import json
import os

from engine.signal_metrics import (
    resolve_confidence_ratio,
    resolve_confluence_percent,
    resolve_ml_probability,
)


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


def _env_float(name: str, default: float) -> float:
    try:
        return float((os.getenv(name) or str(default)).strip())
    except Exception:
        return float(default)


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return bool(default)
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _extract_target_price(signal: dict) -> float | None:
    """Extract the first valid numeric target price from various formats."""
    for key in ("take_profit", "tp", "targets", "tp_levels"):
        val = signal.get(key)
        if val is None:
            continue
        
        # 1. Handle string representations (JSON lists/dicts or comma-separated strings)
        if isinstance(val, str):
            val_clean = val.strip()
            if val_clean.startswith(("[", "{")):
                try:
                    val = json.loads(val_clean)
                except Exception:
                    pass
            elif "," in val_clean:
                val = [v.strip() for v in val_clean.split(",") if v.strip()]

        # 2. Handle dictionary formats (e.g., {"tp1": 100} or {"1": 1.15})
        if isinstance(val, dict):
            for sub_key in ("tp1", "1", "target1", "first"):
                if sub_key in val:
                    try:
                        return float(val[sub_key])
                    except (ValueError, TypeError):
                        pass
            # Fallback: take the first convertible value in the dict
            for k, v in val.items():
                try:
                    return float(v)
                except (ValueError, TypeError):
                    continue

        # 3. Handle list, tuple, or set formats
        if isinstance(val, (list, tuple, set)):
            for item in val:
                try:
                    return float(item)
                except (ValueError, TypeError):
                    continue

        # 4. Handle direct numeric values or plain numeric strings
        try:
            return float(val)
        except (ValueError, TypeError):
            continue

    return None


def trend_alignment_score(signal: dict) -> float | None:
    """Score higher-timeframe trend alignment from 0.0 to 1.0."""
    trend_ema = signal.get("trend_ema")
    trend_sma = signal.get("trend_sma")
    htf_bias = signal.get("htf_bias") or signal.get("htf_alignment")
    direction = _direction_sign(signal.get("direction", 0))

    if trend_ema is not None and trend_sma is not None:
        try:
            te = float(trend_ema)
            ts = float(trend_sma)
            if direction > 0:
                return 1.0 if (te > 0 and ts > 0) else (0.5 if te > 0 else 0.0)
            if direction < 0:
                return 1.0 if (te < 0 and ts < 0) else (0.5 if te < 0 else 0.0)
        except Exception:
            pass

    if htf_bias is not None:
        try:
            return min(max(float(htf_bias), 0.0), 1.0)
        except Exception:
            pass
    return None


def volume_confirmation_score(signal: dict) -> float | None:
    """Score volume expansion from 0.0 to 1.0."""
    volume_ratio = signal.get("volume_ratio") or signal.get("vol_ratio")
    if volume_ratio is None:
        return None
    try:
        ratio = float(volume_ratio)
        min_ratio = _env_float("VOLUME_RATIO_MIN", 1.2)
        ideal_ratio = _env_float("VOLUME_RATIO_IDEAL", 2.0)
        if ratio <= 0.8:
            return 0.0
        if ratio <= 1.0:
            return 0.3
        if ratio < min_ratio:
            return 0.5
        raw = (ratio - min_ratio) / max(0.1, ideal_ratio - min_ratio)
        return min(1.0, 0.7 + raw * 0.3)
    except Exception:
        return None


def liquidity_pool_score(signal: dict) -> float | None:
    """Normalize liquidity score fields to 0.0-1.0."""
    value = signal.get("liquidity_score") or signal.get("liquidity")
    if value is None:
        return None
    try:
        score = float(value)
        return min(max(score / 100.0 if score > 1 else score, 0.0), 1.0)
    except Exception:
        return None


def ml_probability_score(signal: dict) -> float | None:
    """Normalize ML probability/confidence fields to 0.0-1.0."""
    for key in ("ml_probability", "ml_prob", "ml_confidence", "confidence"):
        value = signal.get(key)
        if value is None:
            continue
        try:
            prob = float(value)
            return min(max(prob if prob <= 1.0 else prob / 100.0, 0.0), 1.0)
        except Exception:
            continue
    return None


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
    confluence_min = _env_float("CONFLUENCE_MIN", 15.0)
    confluence_score = resolve_confluence_percent(signal)
    if confluence_score is None:
        confluence_score = calculate_confluence(signal)
    if confluence_score is not None and confluence_score < confluence_min:
        return 0.0
    
    # Target: 0..100 score
    confidence = resolve_confidence_ratio(signal)
    if confidence is None:
        confidence = resolve_ml_probability(signal)
    
    confidence_min = _env_float("CONFIDENCE_MIN", 0.25)
    if confidence is not None and confidence < confidence_min:
        return 0.0

    # Safely convert and normalize entry, stop, and target fields
    try:
        entry = float(signal.get("entry")) if signal.get("entry") is not None else None
        stop = float(signal.get("stop") or signal.get("stop_loss")) if (signal.get("stop") or signal.get("stop_loss")) is not None else None
        target_parsed = _extract_target_price(signal)
        target = float(target_parsed) if target_parsed is not None else entry
    except Exception:
        entry = None
        stop = None
        target = None

    if entry is not None and stop is not None and target is not None and abs(entry - stop) > 0:
        rr = abs(target - entry) / abs(entry - stop)
    else:
        rr = 0.0

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
        return 0.0
    score = 100.0 * sum(val * (weight / total_weight) for val, weight in components.values())
    
    min_rr = _env_float("MIN_RR", 1.0)
    # Hard rejection for poor R/R
    if rr < min_rr:
        print(f"[scoring_rejection] Asset: {signal.get('asset', 'Unknown')} | Reason: Poor R/R ({rr:.2f} < {min_rr:.2f}) | Entry: {entry}, Stop: {stop}, Target: {target}")
        return 0.0
    
    # REGIME ALIGNMENT BONUS
    regime_fit = signal.get("regime_fit") or signal.get("htf_alignment")
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
    
    # ML PROBABILITY BOOST
    ml_val = resolve_ml_probability(signal)
    if ml_val is not None:
        try:
            ml_val = min(max(float(ml_val), 0.0), 1.0)
            ml_boost_min = _env_float("ML_SCORE_BOOST_MIN", 0.8)
            ml_boost_range = _env_float("ML_SCORE_BOOST_RANGE", 0.4)
            ml_boost = ml_boost_min + (ml_val * ml_boost_range)
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


def calculate_confluence(signal: dict) -> float | None:
    """Calculate confluence score (0-100) based on multiple signal confirmations."""
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
            if rsi > 50 and macd_trend > 0:
                confirmations += 1
        elif direction < 0:
            if rsi < 50 and macd_trend < 0:
                confirmations += 1
    
    # 3. Volume confirmation
    volume_ratio = signal.get("volume_ratio")
    if volume_ratio is not None:
        total_checks += 1
        if volume_ratio > _env_float("VOLUME_RATIO_MIN", 1.2):
            confirmations += 1
    
    # 4. Support/Resistance respect
    nearest_support = signal.get("nearest_support")
    nearest_resistance = signal.get("nearest_resistance")
    current_price = signal.get("close_price")

    if current_price is not None and (nearest_support is not None or nearest_resistance is not None):
        total_checks += 1
        if nearest_support is not None and direction > 0 and current_price > nearest_support:
            confirmations += 1
        elif nearest_resistance is not None and direction < 0 and current_price < nearest_resistance:
            confirmations += 1
    
    # 5. Market regime alignment
    regime = signal.get("regime")
    adx_strength = signal.get("adx_trend")

    if regime in ("trending", "ranging") and adx_strength in ("weak", "moderate", "strong"):
        total_checks += 1
        if regime == "trending" and adx_strength in ("moderate", "strong"):
            confirmations += 1
        elif regime == "ranging" and adx_strength == "weak":
            confirmations += 1
    
    if total_checks <= 0:
        return None
    confluence_pct = (confirmations / total_checks) * 100
    return confluence_pct


def strategy_agreement_score(signal):
    return float(signal.get("agreement", 0.5) or 0.5)


def rr_score(rr):
    """Score risk/reward ratio. Higher RR is better (optimal: 2.5:1 to 3:1)."""
    try:
        rr = float(rr)
    except Exception:
        rr = 0.0
    
    min_rr = _env_float("MIN_RR", 1.0)
    if rr < min_rr:
        return 0.0
    
    base = max(min_rr, 1.0)
    scale = max(0.5, 3.0 - base)
    return float(min(max((rr - base) / scale, 0.0), 1.0))


def htf_alignment_score(signal):
    return float(signal.get("htf_alignment", 0.5) or 0.5)


def regime_fit_score(signal, regime=None):
    return float(signal.get("regime_fit", 0.5) or 0.5)


def volatility_quality_score(signal):
    """Score volatility quality (lower volatility = better conditions = higher score)."""
    vol = signal.get("volatility", 0.0)
    try:
        vol = float(vol)
    except Exception:
        vol = 0.0
    
    max_vol = _env_float("MAX_VOLATILITY", 0.20)
    ideal_vol = _env_float("IDEAL_VOLATILITY", 0.12)
    if vol <= ideal_vol:
        return 1.0
    elif vol >= max_vol:
        return 0.0
    else:
        return float((max_vol - vol) / max(1e-9, (max_vol - ideal_vol)))


def historical_winrate_score(signal):
    return float(signal.get("historical_winrate", 0.5) or 0.5)


def liquidity_score(signal):
    return float(signal.get("liquidity", 0.5) or 0.5)


def score_to_confidence_label(score: float) -> str:
    """Convert numeric signal score to a display label."""
    try:
        score = float(score)
    except Exception:
        score = 0.0
    if score >= 90:
        return "Very High"
    if score >= 80:
        return "High"
    if score >= 70:
        return "Above Average"
    if score >= 60:
        return "Moderate"
    if score >= 50:
        return "Below Average"
    return "Low"