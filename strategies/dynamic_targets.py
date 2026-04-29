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
    entry: float,
    atr: float,
    direction: str,
    regime: str,
    volatility_regime: str,
    structure_strength: float = 1.0,
    ml_boost: float = 1.0
) -> DynamicTargets:
    """
    Calculate adaptive TP ladder with BASE_RR=2.0 minimum.
    
    Scaling factors:
    - Strong trend/structure: RR up to 4.0
    - High vol: tighten TP (more conservative)
    - ML expectancy boost: extend targets
    """
    # Base R:R minimum 2.0
    base_rr = max(2.0, 1.5 + structure_strength * ml_boost)
    
    # Vol regime adjustment
    vol_mult = 0.8 if volatility_regime == "high" else 1.2 if volatility_regime == "low" else 1.0
    
    # Regime boost
    regime_mult = 1.3 if regime == "trending" else 0.9 if regime == "ranging" else 1.0
    
    final_rr = base_rr * vol_mult * regime_mult
    final_rr = min(final_rr, 5.0)  # Cap for sanity
    
    risk_distance = 2.0 * atr  # Standard 2x ATR SL
    
    if direction.lower() == "long":
        sl = entry - risk_distance
        tp1 = entry + (risk_distance * 1.0)
        tp2 = entry + (risk_distance * final_rr * 0.6)
        tp3 = entry + (risk_distance * final_rr)
    else:  # short
        sl = entry + risk_distance
        tp1 = entry - (risk_distance * 1.0)
        tp2 = entry - (risk_distance * final_rr * 0.6)
        tp3 = entry - (risk_distance * final_rr)
    
    targets = DynamicTargets(
        tp_levels=[tp1, tp2, tp3],
        sl=sl,
        base_rr=base_rr,
        final_rr=final_rr,
        vol_adjusted=True
    )
    
    logger.debug(f"Dynamic targets: base_rr={base_rr:.1f}, final={final_rr:.1f}, vol={volatility_regime}, regime={regime}")
    return targets

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
    
    targets = calculate_dynamic_targets(
        entry=signal["entry"],
        atr=signal.get("atr", 0.01),
        direction=signal.get("direction", "long"),
        regime=signal.get("regime", "neutral"),
        volatility_regime=signal.get("vol_regime", "medium"),
        structure_strength=signal.get("structure_strength", 1.0),
        ml_boost=signal.get("ml_boost", 1.0)
    )
    
    signal["dynamic_tp"] = targets.tp_levels
    signal["dynamic_sl"] = targets.sl
    signal["dynamic_rr"] = targets.final_rr
    
    return signal

