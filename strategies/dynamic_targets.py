"""Dynamic Take Profit Targets - Adaptive R:R based on ATR, structure, volatility regime.

BASE_RR=2.0 minimum, scales up for strong setups.
"""

import logging
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass

from core.tier_constants import EXPECTANCY_MIN

logger = logging.getLogger(__name__)

@dataclass
class DynamicTargets:
    tp_levels: List[float]
    sl: float
    base_rr: float
    final_rr: float
    vol_adjusted: bool

def calculate_dynamic_targets(
    direction: str,
    entry_price: float,
    candles=None,
    indicators=None,
    regime: str = "neutral",
    signal_quality: float = 0.5
) -> dict:
    """
    Calculate adaptive TP ladder with BASE_RR=2.0 minimum.
    
    Called by strategy classes with this exact signature:
    - direction: 'LONG' or 'SHORT'
    - entry_price: float - entry price
    - candles: list of candle dicts (for ATR calculation)
    - indicators: dict of indicator values (for ATR)
    - regime: market regime string
    - signal_quality: confidence 0-1
    
    Returns dict with keys:
    - stop_loss, take_profit, tp_levels, rr_ratio
    """
    # Extract ATR from indicators or calculate from candles
    atr = 0.0
    if indicators and isinstance(indicators, dict):
        atr = float(indicators.get('atr') or indicators.get('atr14') or 0)
    
    # Fallback: calculate ATR from candles if not in indicators
    if atr <= 0 and candles and isinstance(candles, list) and len(candles) >= 14:
        try:
            closes = [c.get('close', 0) for c in candles if c.get('close')]
            highs = [c.get('high', 0) for c in candles if c.get('high')]
            lows = [c.get('low', 0) for c in candles if c.get('low')]
            
            if len(closes) >= 14 and len(highs) >= 14 and len(lows) >= 14:
                trs = []
                for i in range(1, len(closes)):
                    h = highs[i]
                    l = lows[i]
                    pc = closes[i-1]
                    tr = max(h - l, abs(h - pc), abs(l - pc))
                    trs.append(tr)
                if trs:
                    atr = sum(trs[-14:]) / 14
        except Exception:
            pass
    
    # Default ATR if still zero - use 1% of price as rough estimate
    if atr <= 0:
        atr = entry_price * 0.01
    
    # Base R:R minimum 2.0, scaled by signal quality
    base_rr = max(2.0, 1.5 + signal_quality)
    
    # Vol regime adjustment (extract from indicators if available)
    vol_regime = "medium"
    if indicators and isinstance(indicators, dict):
        vol_regime = indicators.get('vol_regime') or indicators.get('volatility_regime') or "medium"
    
    vol_mult = 0.8 if vol_regime == "high" else 1.2 if vol_regime == "low" else 1.0
    
    # Regime boost
    regime_lower = str(regime).lower()
    regime_mult = 1.3 if regime_lower == "trending" else 0.9 if regime_lower == "ranging" else 1.0
    
    final_rr = base_rr * vol_mult * regime_mult
    final_rr = min(final_rr, 5.0)  # Cap for sanity
    
    risk_distance = 2.0 * atr  # Standard 2x ATR SL
    
    direction_lower = str(direction).lower()
    if direction_lower == "long":
        sl = entry_price - risk_distance
        tp1 = entry_price + (risk_distance * 1.0)
        tp2 = entry_price + (risk_distance * final_rr * 0.6)
        tp3 = entry_price + (risk_distance * final_rr)
    else:  # short
        sl = entry_price + risk_distance
        tp1 = entry_price - (risk_distance * 1.0)
        tp2 = entry_price - (risk_distance * final_rr * 0.6)
        tp3 = entry_price - (risk_distance * final_rr)
    
    # Return dict with expected keys (for backwards compatibility)
    result = {
        'stop_loss': sl,
        'take_profit': tp3,
        'tp_levels': [tp1, tp2, tp3],
        'rr_ratio': final_rr,
        'base_rr': base_rr,
        'final_rr': final_rr,
        'atr': atr,
    }
    
    logger.debug(f"Dynamic targets: base_rr={base_rr:.1f}, final={final_rr:.1f}, vol={vol_regime}, regime={regime}")
    return result

def get_tp_ladders_for_tier(targets: DynamicTargets, tier: str) -> List[float]:
    """Tier-specific TP ladder (from core/tier_constants)."""
    from core.tier_constants import TIER_SIGNAL_DEPTH
    
    depth = TIER_SIGNAL_DEPTH.get(tier, {"max_tp_level": 2})
    max_tp = depth.get("max_tp_level", 2)
    
    return targets.tp_levels[:max_tp]

# Integration hook
def enhance_signal_targets(signal: Dict) -> Dict:
    """Hook for engine pipeline."""
    if "atr" not in signal or "entry" not in signal:
        return signal
    
    # Use new signature
    targets = calculate_dynamic_targets(
        direction=signal.get("direction", "long"),
        entry_price=signal.get("entry", 0),
        candles=signal.get("candles"),
        indicators=signal,
        regime=signal.get("regime", "neutral"),
        signal_quality=signal.get("confidence", 0.5)
    )
    
    signal["dynamic_tp"] = targets.get('tp_levels', [])
    signal["dynamic_sl"] = targets.get('stop_loss')
    signal["dynamic_rr"] = targets.get('final_rr')
    
    return signal

