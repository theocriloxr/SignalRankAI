import logging
import time
from datetime import datetime, timezone
from typing import Dict, Tuple, Optional

logger = logging.getLogger(__name__)

# ============================================================================
# PHASE 2: Regime Strategy Preference Mapping
# Maps market regimes to preferred strategies with confidence weighting
# ============================================================================
REGIME_STRATEGY_PREFERENCE = {
    "TRENDING": {
        # Strategies that excel in trending markets (2+ strategies = high_confidence)
        "high_confidence": ["supertrend", "rsi", "trend_follow", "adx_breakout"],
        # Strategies that underperform in trending markets
        "low_confidence": ["fibonacci_confluence", "support_resistance", "mean_reversion"],
        # Weight multiplier for trending regime strategies
        "weight_boost": 1.2,
    },
    "RANGING": {
        # Strategies that excel in ranging/consolidation markets
        "high_confidence": ["fibonacci_confluence", "support_resistance", "mean_reversion"],
        # Strategies that underperform in ranging markets
        "low_confidence": ["supertrend", "trend_follow", "adx_breakout"],
        # Weight multiplier for ranging regime strategies
        "weight_boost": 0.8,
    },
    "VOLATILE": {
        # Strategies for high volatility environments
        "high_confidence": ["implied_move", "volatility", "breakout"],
        # Strategies that suffer in high volatility
        "low_confidence": ["fibonacci_confluence", "mean_reversion"],
        # Weight multiplier for volatile regime strategies
        "weight_boost": 1.0,
    },
}


def _get_regime_from_indicators(indicators: Dict) -> Tuple[str, float]:
    """
    Detect regime from single timeframe indicators.
    
    Returns: (regime_name, confidence_0_to_1)
    - Confidence 1.0 = very high conviction
    - Confidence 0.5 = moderate conviction
    - Confidence 0.0 = no clear regime (default to TRENDING)
    """
    if not isinstance(indicators, dict):
        return "TRENDING", 0.0
    
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
    
    # Regime detection with confidence scoring
    # Strong trending: ADX > 20 + ATR > 1% = TRENDING with 0.9 confidence
    if adx > 20 and atr_pct > 1.0:
        return "TRENDING", 0.9
    
    # Moderate trending: ADX > 15 + ATR > 0.5% = TRENDING with 0.7 confidence
    if adx > 15 and atr_pct > 0.5:
        return "TRENDING", 0.7
    
    # Weak trending: ADX > 10 = TRENDING with 0.5 confidence
    if adx > 10:
        return "TRENDING", 0.5
    
    # Low volatility + low ADX = RANGING with 0.8 confidence
    if bb_width < 0.05 and adx < 20:
        return "RANGING", 0.8
    
    # Moderate range + low ADX = RANGING with 0.6 confidence
    if bb_width < 0.10 and adx < 15:
        return "RANGING", 0.6
    
    # High volatility (ATR > 3%) = VOLATILE with 0.9 confidence
    if atr_pct > 3.0:
        return "VOLATILE", 0.9
    
    # Moderate volatility (ATR 1.5-3%) + low ADX = VOLATILE with 0.7 confidence
    if atr_pct > 1.5 and adx < 15:
        return "VOLATILE", 0.7
    
    # Default: uncertain regime, prefer TRENDING to allow signals through
    return "TRENDING", 0.3


def detect_market_regime(market_data: Dict) -> Dict:
    """
    Detect market regime using multi-timeframe confirmation and stability scoring.
    
    PHASE 2 ENHANCEMENT:
    - Gets regime votes from 1h, 4h, 1d timeframes
    - Calculates confidence based on vote agreement (2+/3 = higher confidence)
    - Tracks regime stability (penalizes frequent regime changes)
    - Returns structured regime info with strategy preferences
    
    Returns:
    {
        "regime": "TRENDING" | "RANGING" | "VOLATILE",
        "confidence": 0.0-1.0,  # 0.33 (1/3), 0.66 (2/3), 1.0 (3/3) votes
        "stability": 0.0-1.0,   # 1.0 stable, 0.3 unstable
        "regime_votes": {"1h": "TRENDING", "4h": "TRENDING", "1d": "RANGING"},
        "regime_tf_confidences": {"1h": 0.7, "4h": 0.9, "1d": 0.6},
        "changes_24h": 1,       # Number of regime changes in last 24h
        "strategy_preferences": { ... } # Subset of REGIME_STRATEGY_PREFERENCE
    }
    """
    import os
    
    if not isinstance(market_data, dict):
        raise ValueError("market_data must be a dict")
    
    # ========================================================================
    # STEP 1: Collect regime votes from available timeframes
    # ========================================================================
    timeframes_to_check = ['1h', '4h', '1d']
    regime_votes = {}  # timeframe -> regime
    regime_confidences = {}  # timeframe -> confidence (0.0-1.0)
    
    for tf in timeframes_to_check:
        tf_data = market_data.get(tf, {})
        if not isinstance(tf_data, dict):
            continue
        
        indicators = tf_data.get('indicators', {})
        if not indicators:
            continue
        
        regime, confidence = _get_regime_from_indicators(indicators)
        regime_votes[tf] = regime
        regime_confidences[tf] = confidence
    
    # Fallback: if no timeframes available, try any available one
    if not regime_votes:
        for tf_name, tf_data in market_data.items():
            if isinstance(tf_data, dict) and tf_data.get('indicators'):
                regime, confidence = _get_regime_from_indicators(tf_data['indicators'])
                regime_votes[tf_name] = regime
                regime_confidences[tf_name] = confidence
                break
    
    # Final fallback: uncertain regime
    if not regime_votes:
        return {
            "regime": "TRENDING",
            "confidence": 0.3,
            "stability": 0.5,
            "regime_votes": {},
            "regime_tf_confidences": {},
            "changes_24h": 0,
            "strategy_preferences": REGIME_STRATEGY_PREFERENCE.get("TRENDING", {}),
        }
    
    # ========================================================================
    # STEP 2: Vote aggregation - determine winning regime
    # ========================================================================
    # Count votes for each regime type
    from collections import Counter
    vote_counts = Counter(regime_votes.values())
    
    # Determine winning regime based on majority vote
    # 2+ votes out of 3 = HIGH_CONFIDENCE, otherwise use highest-confidence single vote
    winning_regime = vote_counts.most_common(1)[0][0]
    vote_agreement_count = vote_counts[winning_regime]
    
    # Calculate confidence based on vote agreement
    total_tf_votes = len(regime_votes)
    if total_tf_votes >= 3:
        # 3/3 = 1.0, 2/3 = 0.66, 1/3 = 0.33
        confidence = vote_agreement_count / total_tf_votes
    elif total_tf_votes == 2:
        # 2/2 = 1.0, 1/2 = 0.5
        confidence = vote_agreement_count / 2
    else:
        # Single vote - use its intrinsic confidence
        confidence = list(regime_confidences.values())[0] if regime_confidences else 0.5
    
    # ========================================================================
    # STEP 3: Regime stability scoring
    # ========================================================================
    # Track regime history in Redis to detect frequent changes
    # Key: "regime:asset:history" stores list of (timestamp, regime) tuples
    try:
        from utils.state import state
        
        # Try to get existing history
        asset = market_data.get('asset', 'UNKNOWN')
        history_key = f"regime:{asset}:history"
        history_str = state.get_sync(history_key)
        
        regime_history = []
        changes_24h = 0
        stability_score = 1.0
        
        if history_str:
            try:
                import json
                history_str = str(history_str)
                regime_history = json.loads(history_str) if history_str else []
            except Exception:
                regime_history = []
        
        # Filter to last 24 hours and count changes
        now = time.time()
        cutoff = now - (24 * 3600)
        
        recent_history = []
        for entry in regime_history:
            if isinstance(entry, (list, tuple)) and len(entry) >= 2:
                ts, regime = entry[0], entry[1]
                if float(ts) > cutoff:
                    recent_history.append((ts, regime))
        
        # Count regime changes in last 24h
        if recent_history:
            changes = 0
            prev_regime = recent_history[0][1]
            for ts, regime in recent_history[1:]:
                if regime != prev_regime:
                    changes += 1
                prev_regime = regime
            changes_24h = changes
            
            # Stability score: 1.0 (stable) to 0.3 (very unstable)
            # 0 changes = 1.0, 1 change = 0.8, 2+ changes = 0.5-0.3
            if changes_24h == 0:
                stability_score = 1.0
            elif changes_24h == 1:
                stability_score = 0.8
            elif changes_24h == 2:
                stability_score = 0.6
            else:
                stability_score = 0.4
        
        # Update history with current regime
        now_ts = time.time()
        new_entry = [now_ts, winning_regime]
        if not recent_history or recent_history[-1][1] != winning_regime:
            # New regime or regime change - add to history
            recent_history.append((now_ts, winning_regime))
        
        # Keep last 50 entries (fits Redis string size)
        recent_history = recent_history[-50:]
        
        # Store back to Redis
        try:
            import json
            history_str = json.dumps(recent_history)
            state.set_sync(history_key, history_str, ex=86400 * 2)  # 2-day TTL
        except Exception as e:
            logger.debug(f"[regime] Failed to store regime history: {e}")
    
    except Exception as e:
        logger.debug(f"[regime] Stability tracking disabled: {e}")
        changes_24h = 0
        stability_score = 1.0
    
    # ========================================================================
    # STEP 4: Return comprehensive regime information
    # ========================================================================
    result = {
        "regime": winning_regime,
        "confidence": float(confidence),
        "stability": float(stability_score),
        "regime_votes": regime_votes,
        "regime_tf_confidences": regime_confidences,
        "changes_24h": changes_24h,
        "strategy_preferences": REGIME_STRATEGY_PREFERENCE.get(winning_regime, {}),
    }
    
    logger.debug(
        f"[regime] Detected {winning_regime} (confidence={confidence:.2f}, "
        f"stability={stability_score:.2f}, votes={regime_votes})"
    )
    
    return result
