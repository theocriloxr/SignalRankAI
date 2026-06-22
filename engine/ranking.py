"""
Enhanced Signal Ranking with Weighted Composite Confidence

Implements the Perfect Trading Bot's dynamic confidence system:
- Trend Confidence: Based on ADX and market structure
- Liquidity Confidence: Based on volume and liquidity metrics  
- Volume Confidence: Based on volume expansion
- ML Confidence: Based on ML model probability
- Regime Confidence: Based on regime detection stability

Final confidence = Weighted Composite Score
"""

import os
from typing import Any, Dict, List, Optional, Tuple

from engine.ml import score_signal, get_live_strategy_weight


def _env_float(name: str, default: float) -> float:
    try:
        return float((os.getenv(name) or str(default)).strip())
    except Exception:
        return float(default)


# Confidence component weights (must sum to 1.0)
CONFIDENCE_WEIGHTS = {
    "trend": _env_float("TREND_CONFIDENCE_WEIGHT", 0.25),
    "liquidity": _env_float("LIQUIDITY_CONFIDENCE_WEIGHT", 0.20),
    "volume": _env_float("VOLUME_CONFIDENCE_WEIGHT", 0.20),
    "ml": _env_float("ML_CONFIDENCE_WEIGHT", 0.25),
    "regime": _env_float("REGIME_CONFIDENCE_WEIGHT", 0.10),
}


def _resolve_indicator(indicators: Dict, key: str, default: float = 0.0) -> float:
    """Safely resolve indicator value from indicators dict."""
    if not isinstance(indicators, dict):
        return default
    try:
        val = indicators.get(key)
        if val is None:
            return default
        return float(val)
    except (TypeError, ValueError):
        return default


def _calculate_trend_confidence(indicators: Dict, direction: str) -> float:
    """
    Calculate Trend Confidence (0-100)
    
    Factors:
    - ADX: Higher = stronger trend (25+ = strong)
    - Plus DI vs Minus DI: Directional strength
    - Market structure: Break of structure detection
    
    Returns: 0-100 confidence score
    """
    adx = _resolve_indicator(indicators, "adx", 0)
    plus_di = _resolve_indicator(indicators, "plus_di", 0)
    minus_di = _resolve_indicator(indicators, "minus_di", 0)
    
    # ADX scoring (0-50 points)
    if adx >= 40:
        adx_score = 50
    elif adx >= 30:
        adx_score = 40
    elif adx >= 25:
        adx_score = 30
    elif adx >= 20:
        adx_score = 20
    elif adx >= 15:
        adx_score = 10
    else:
        adx_score = 0
    
    # Directional DI scoring (0-30 points)
    dir_diff = abs(plus_di - minus_di)
    if dir_diff >= 20:
        di_score = 30
    elif dir_diff >= 15:
        di_score = 25
    elif dir_diff >= 10:
        di_score = 20
    elif dir_diff >= 5:
        di_score = 10
    else:
        di_score = 0
    
    # DI alignment with direction (0-20 points)
    dir_lower = direction.lower()
    if dir_lower == "long" and plus_di > minus_di:
        alignment_score = 20
    elif dir_lower == "short" and minus_di > plus_di:
        alignment_score = 20
    elif dir_lower == "long" and plus_di > 0:
        alignment_score = 10
    elif dir_lower == "short" and minus_di > 0:
        alignment_score = 10
    else:
        alignment_score = 0
    
    return min(100, adx_score + di_score + alignment_score)


def _calculate_liquidity_confidence(indicators: Dict) -> float:
    """
    Calculate Liquidity Confidence (0-100)
    
    Factors:
    - Volume relative to average
    - Order book imbalance (if available)
    - Spread tightness
    
    Returns: 0-100 confidence score
    """
    volume = _resolve_indicator(indicators, "volume", 0)
    volume_ma = _resolve_indicator(indicators, "volume_ma", 0)
    spread = _resolve_indicator(indicators, "spread", 999)
    
    # Volume vs MA scoring (0-60 points)
    if volume_ma > 0:
        vol_ratio = volume / volume_ma
        if vol_ratio >= 2.0:
            vol_score = 60
        elif vol_ratio >= 1.5:
            vol_score = 50
        elif vol_ratio >= 1.2:
            vol_score = 40
        elif vol_ratio >= 1.0:
            vol_score = 30
        elif vol_ratio >= 0.8:
            vol_score = 20
        else:
            vol_score = 10
    else:
        vol_score = 30  # Default neutral
    
    # Spread scoring (0-40 points) - lower is better
    if spread <= 0.01:
        spread_score = 40
    elif spread <= 0.05:
        spread_score = 30
    elif spread <= 0.1:
        spread_score = 20
    elif spread <= 0.5:
        spread_score = 10
    else:
        spread_score = 0
    
    return min(100, vol_score + spread_score)


def _calculate_volume_confidence(indicators: Dict) -> float:
    """
    Calculate Volume Confidence (0-100)
    
    Factors:
    - Volume expansion vs recent average
    - Volume trend direction
    - candle size vs volume relationship
    
    Returns: 0-100 confidence score
    """
    volume = _resolve_indicator(indicators, "volume", 0)
    volume_ma = _resolve_indicator(indicators, "volume_ma", 0)
    volume_std = _resolve_indicator(indicators, "volume_std", 0)
    close = _resolve_indicator(indicators, "close", 0)
    open_price = _resolve_indicator(indicators, "open", close)
    
    # Volume expansion scoring (0-60 points)
    if volume_ma > 0 and volume_std > 0:
        z_score = (volume - volume_ma) / volume_std
        if z_score >= 2.0:
            exp_score = 60
        elif z_score >= 1.5:
            exp_score = 50
        elif z_score >= 1.0:
            exp_score = 40
        elif z_score >= 0.5:
            exp_score = 30
        elif z_score >= 0:
            exp_score = 20
        else:
            exp_score = 10
    else:
        vol_ratio = volume / volume_ma if volume_ma > 0 else 1.0
        if vol_ratio >= 1.5:
            exp_score = 50
        elif vol_ratio >= 1.2:
            exp_score = 40
        elif vol_ratio >= 1.0:
            exp_score = 30
        elif vol_ratio >= 0.8:
            exp_score = 20
        else:
            exp_score = 10
    
    # Candle direction vs volume (0-40 points for expansion)
    try:
        candle_change = abs(close - open_price) / open_price if open_price > 0 else 0
        if volume > 0 and volume_ma > 0:
            if candle_change > 0 and volume > volume_ma:
                dir_score = 40
            elif candle_change > 0:
                dir_score = 30
            else:
                dir_score = 20
        else:
            dir_score = 20
    except:
        dir_score = 20
    
    return min(100, exp_score + dir_score)


def _calculate_ml_confidence(ml_prob: Optional[float]) -> float:
    """
    Calculate ML Confidence (0-100)
    
    Direct mapping from ML probability
    """
    if ml_prob is None:
        return 50.0  # Neutral when no ML score
    return min(100.0, max(0.0, ml_prob * 100.0))


def _calculate_regime_confidence(regime_info: Optional[Dict]) -> float:
    """
    Calculate Regime Confidence (0-100)
    
    Factors:
    - Regime detection confidence
    - Regime stability over 24h
    - Multi-timeframe agreement
    """
    if not regime_info:
        return 50.0  # Neutral
    
    # Base confidence from detection (0-60)
    base_conf = float(regime_info.get("confidence", 0.5)) * 60
    
    # Stability score (0-25)
    stability = float(regime_info.get("stability", 0.5)) * 25
    
    # Multi-timeframe agreement (0-15)
    votes = regime_info.get("regime_votes", {})
    tf_count = len(votes)
    if tf_count >= 3:
        tf_score = 15
    elif tf_count == 2:
        tf_score = 10
    else:
        tf_score = 5
    
    return min(100.0, base_conf + stability + tf_score)


def _calculate_weighted_composite(
    trend: float,
    liquidity: float,
    volume: float,
    ml: float,
    regime: float,
) -> float:
    """
    Calculate Weighted Composite Score (0-100)
    
    Combines all confidence components using configured weights
    """
    weights = CONFIDENCE_WEIGHTS
    composite = (
        (trend * weights.get("trend", 0.25)) +
        (liquidity * weights.get("liquidity", 0.20)) +
        (volume * weights.get("volume", 0.20)) +
        (ml * weights.get("ml", 0.25)) +
        (regime * weights.get("regime", 0.10))
    )
    return min(100.0, max(0.0, composite))


def _extract_indicators(signal):
    """Extract indicators from signal for confidence calculation."""
    indicators = signal.get("indicators")
    if indicators and isinstance(indicators, dict):
        return indicators
    
    # Try nested structure
    for key in ("market_data", "data", "ohlcv"):
        nested = signal.get(key)
        if nested and isinstance(nested, dict):
            indicators = nested.get("indicators")
            if indicators and isinstance(indicators, dict):
                return indicators
    
    return {}


def _extract_regime_info(signal: Dict) -> Optional[Dict]:
    """Extract regime info from signal."""
    regime = signal.get("regime")
    if regime and isinstance(regime, dict):
        return regime
    return signal.get("regime_info")


def calculate_confidence_components(signal: Dict) -> Dict[str, float]:
    """
    Calculate all confidence components for a signal.
    
    Returns dict with:
    - trend_confidence: 0-100
    - liquidity_confidence: 0-100
    - volume_confidence: 0-100
    - ml_confidence: 0-100
    - regime_confidence: 0-100
    - composite_score: 0-100 Weighted Composite Score
    """
    direction = str(signal.get("direction", "long")).lower()
    
# Extract data sources
    indicators = _extract_indicators(signal)
    regime_info = _extract_regime_info(signal)
    ml_prob = signal.get("ml_probability") or signal.get("ml_prob")
    if ml_prob is not None:
        try:
            ml_prob = float(ml_prob)
        except:
            ml_prob = None
    
    # Calculate each component
    trend_conf = _calculate_trend_confidence(indicators, direction)
    liquidity_conf = _calculate_liquidity_confidence(indicators)
    volume_conf = _calculate_volume_confidence(indicators)
    ml_conf = _calculate_ml_confidence(ml_prob)
    regime_conf = _calculate_regime_confidence(regime_info)
    
    # Calculate composite
    composite = _calculate_weighted_composite(
        trend_conf,
        liquidity_conf,
        volume_conf,
        ml_conf,
        regime_conf,
    )
    
    return {
        "trend_confidence": trend_conf,
        "liquidity_confidence": liquidity_conf,
        "volume_confidence": volume_conf,
        "ml_confidence": ml_conf,
        "regime_confidence": regime_conf,
        "composite_score": composite,
    }


def rank_signals(signals):
    """
    Accepts a list of signals and returns a dict with keys 'vip', 'premium', 'free'.
    
    Enhanced with Weighted Composite Confidence:
    - Uses composite_score as primary ranking metric
    - Falls back to score_final if composite not available
    - Includes all confidence components in signal metadata
    """
    vip_threshold = _env_float("VIP_SCORE_THRESHOLD", 75)
    premium_threshold = _env_float("PREMIUM_SCORE_THRESHOLD", 60)
    
    premium = []
    vip = []
    free = []
    
    for signal in signals:
        # Get base components
        base_score = float(signal.get('score', 0) or 0)
        ml_prob = score_signal(signal)
        ml_score = (ml_prob or 0.0) * 100.0
        strategy_name = str(signal.get("strategy_name") or signal.get("strategy") or signal.get("name") or "").strip()
        live_weight = get_live_strategy_weight(strategy_name, default=1.0) if strategy_name else 1.0
        weighted_base = base_score * live_weight
        score_final = (0.6 * weighted_base) + (0.4 * ml_score) if ml_prob is not None else weighted_base
        
        # Calculate confidence components
        try:
            conf_components = calculate_confidence_components(signal)
        except Exception:
            conf_components = {
                "composite_score": score_final,
                "trend_confidence": 50.0,
                "liquidity_confidence": 50.0,
                "volume_confidence": 50.0,
                "ml_confidence": ml_score if ml_prob else 50.0,
                "regime_confidence": 50.0,
            }
        
        # Use composite score as primary ranking metric
        # If composite is significantly different from score_final, prefer composite
        composite = conf_components.get("composite_score", score_final)
        
        # Blend composite with score_final for final ranking (70% composite, 30% original)
        ranking_score = (0.7 * composite) + (0.3 * score_final)
        
        # Persist all scores for downstream consumers
        signal['score_final'] = ranking_score
        signal['score_ml'] = ml_score if ml_prob is not None else None
        signal['score_composite'] = composite
        signal['score_base'] = base_score
        signal['strategy_weight'] = live_weight
        
        # Persist confidence components
        signal['trend_confidence'] = conf_components.get("trend_confidence", 50.0)
        signal['liquidity_confidence'] = conf_components.get("liquidity_confidence", 50.0)
        signal['volume_confidence'] = conf_components.get("volume_confidence", 50.0)
        signal['ml_confidence'] = conf_components.get("ml_confidence", 50.0)
        signal['regime_confidence'] = conf_components.get("regime_confidence", 50.0)
        signal['composite_score'] = composite
        
        # Tier allocation using composite score
        if ranking_score >= vip_threshold:
            vip.append(signal)
        elif ranking_score >= premium_threshold:
            premium.append(signal)
        else:
            free.append(signal)
    
    # Sort by ranking score (descending)
    vip.sort(key=lambda x: x.get('score_final', x.get('score', 0)), reverse=True)
    premium.sort(key=lambda x: x.get('score_final', x.get('score', 0)), reverse=True)
    free.sort(key=lambda x: x.get('score_final', x.get('score', 0)), reverse=True)
    
    return {'vip': vip, 'premium': premium, 'free': free}


# Backwards compatibility
def _env_int(name: str, default: int = 0) -> int:
    try:
        return int((os.getenv(name) or str(default)).strip())
    except Exception:
        return default


__all__ = [
    "rank_signals",
    "calculate_confidence_components",
    "CONFIDENCE_WEIGHTS",
]
