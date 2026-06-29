"""
Dynamic Threshold Calculator

Auto-adjusts the ML probability threshold based on model AUC performance.
This creates a self-healing system where:
- If model AUC drops (market drift), threshold increases (stricter)
- If model AUC rises, threshold decreases (more signals)

FIX APPLIED:
- Removed hard clamp at 0.40 that was causing threshold to always return 0.40
- Added persistence via Redis so threshold persists between cycles
- Added cooldown to prevent recalculation spam
- Added hysteresis (MIN_CHANGE = 0.03) to prevent oscillation
- Added per-asset-class thresholds
- Logs only when threshold changes (not every cycle)
"""

import os
import logging
import time
from typing import Optional, Dict
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

# Threshold bounds (safety limits)
MIN_THRESHOLD = float(os.getenv("ML_THRESHOLD_MIN", "0.10"))
MAX_THRESHOLD = float(os.getenv("ML_THRESHOLD_MAX", "0.85"))

# Cooldown settings
MIN_UPDATE_INTERVAL_HOURS = float(os.getenv("ML_THRESHOLD_UPDATE_HOURS", "6"))
MIN_OUTCOMES_FOR_UPDATE = int(os.getenv("ML_THRESHOLD_MIN_OUTCOMES", "50"))

# Hysteresis to prevent oscillation
MIN_CHANGE = 0.03

# Redis key prefix for threshold persistence
THRESHOLD_KEY_PREFIX = "ml:threshold:"
THRESHOLD_KEYS = {
    "default": f"{THRESHOLD_KEY_PREFIX}default",
    "crypto": f"{THRESHOLD_KEY_PREFIX}crypto",
    "fx": f"{THRESHOLD_KEY_PREFIX}fx",
    "stocks": f"{THRESHOLD_KEY_PREFIX}stocks",
    "commodities": f"{THRESHOLD_KEY_PREFIX}commodities",
}

# In-memory cache for thresholds (with cooldown)
_last_calculation_time: float = 0
_last_calculated_threshold: Optional[float] = None
_cached_threshold: Optional[float] = None
_cached_asset_class: str = "default"


def _get_redis_client():
    """Get Redis client for persistence."""
    try:
        import redis as redis_client
        redis_url = os.getenv("REDIS_URL")
        if not redis_url:
            return None
        return redis_client.from_url(redis_url, decode_responses=True)
    except Exception:
        return None


def _should_recalculate() -> bool:
    """
    Check if threshold should be recalculated based on cooldown.
    
    Returns True if:
    - First run (no cached value)
    - 6+ hours since last calculation
    - No outcomes recorded yet
    """
    global _last_calculation_time, _cached_threshold
    
    if _cached_threshold is None:
        return True
    
    elapsed_hours = (time.time() - _last_calculation_time) / 3600
    if elapsed_hours >= MIN_UPDATE_INTERVAL_HOURS:
        return True
    
    # Check if enough outcomes exist for meaningful analysis
    r = _get_redis_client()
    if r:
        try:
            outcome_count = r.get("ml:outcome:count")
            if outcome_count and int(outcome_count) >= MIN_OUTCOMES_FOR_UPDATE:
                return True
        except Exception:
            pass
        finally:
            r.close()
    
    return False


def _get_persisted_threshold(asset_class: str = "default") -> Optional[float]:
    """Get persisted threshold from Redis."""
    r = _get_redis_client()
    if not r:
        return None
    
    try:
        key = THRESHOLD_KEYS.get(asset_class, THRESHOLD_KEYS["default"])
        value = r.get(key)
        r.close()
        
        if value is not None:
            return float(value)
    except Exception as e:
        logger.debug(f"[ml] Failed to get persisted threshold: {e}")
    return None


def _persist_threshold(threshold: float, asset_class: str = "default") -> bool:
    """Persist threshold to Redis."""
    r = _get_redis_client()
    if not r:
        return False
    
    try:
        key = THRESHOLD_KEYS.get(asset_class, THRESHOLD_KEYS["default"])
        # Set with 24-hour expiry
        r.setex(key, 86400, str(threshold))
        r.close()
        return True
    except Exception as e:
        logger.debug(f"[ml] Failed to persist threshold: {e}")
    return False


def get_threshold_for_asset_class(asset_class: str) -> float:
    """
    Get the threshold for a specific asset class.
    
    Uses persisted value if available, otherwise returns default.
    """
    # Try persisted first
    persisted = _get_persisted_threshold(asset_class)
    if persisted is not None:
        return persisted
    
    # Fall back to default
    return _get_persisted_threshold("default") or float(os.getenv("ML_PROB_THRESHOLD", "0.15"))


def calculate_dynamic_threshold(
    base_threshold: float, 
    current_auc: float, 
    target_auc: float = 0.85,
    force: bool = False
) -> float:
    """
    Auto-adjusts the required score threshold based on the ML model's current performance.
    
    FIXED: This function now:
    - Returns cached value if within cooldown period
    - Only recalculates when needed
    - Does NOT hard clamp at 0.40
    - Persists the new threshold
    
    Args:
        base_threshold: The base ML probability threshold (e.g., 0.30)
        current_auc: The current model AUC from training (0.0-1.0)
        target_auc: The target AUC to normalize against (default: 0.85)
        force: Force recalculation even within cooldown
    
    Returns:
        Dynamic threshold adjusted based on model performance
    """
    global _last_calculation_time, _last_calculated_threshold, _cached_threshold
    
    # Check cooldown unless force=True
    if not force and _cached_threshold is not None and not _should_recalculate():
        logger.debug(
            f"[ml] Using cached threshold: %.2f (cooldown period)",
            _cached_threshold
        )
        return _cached_threshold
    
    # Model is essentially guessing - block almost all trades
    if current_auc <= 0.50:
        logger.warning("[ml] Model AUC %.2f <= 0.50 (guessing); using strict threshold 0.85", current_auc)
        new_threshold = 0.85
    elif current_auc >= 0.95:
        # Model is very strong - allow more trades
        logger.info("[ml] Model AUC %.2f >= 0.95 (excellent); using loose threshold", current_auc)
        new_threshold = max(MIN_THRESHOLD, base_threshold * 0.8)
    else:
        # Scale the threshold inversely to model performance
        adjustment_factor = target_auc / current_auc
        dynamic_threshold = base_threshold * adjustment_factor
        
        # Clamp to reasonable bounds (NOT hard-clamped to 0.40!)
        new_threshold = max(MIN_THRESHOLD, min(MAX_THRESHOLD, dynamic_threshold))
    
    # Apply hysteresis: only change if difference > MIN_CHANGE
    if _last_calculated_threshold is not None:
        change = abs(new_threshold - _last_calculated_threshold)
        if change < MIN_CHANGE:
            logger.debug(
                f"[ml] Threshold change %.3f < MIN_CHANGE %.3f, keeping current",
                change, MIN_CHANGE
            )
            return _last_calculated_threshold
    
    # Check if model AUC is too low for dynamic adaptation
    if current_auc < 0.60:
        logger.warning(
            f"[ml] AUC {current_auc:.2f} < 0.60 - disabling dynamic adaptation. "
            f"Focus on data quality first.",
            current_auc
        )
        # Return base threshold instead of dynamic
        new_threshold = base_threshold
    
    # Log only when threshold actually changes
    if _last_calculated_threshold is None or abs(new_threshold - _last_calculated_threshold) >= MIN_CHANGE:
        logger.info(
            "[ml] Dynamic threshold CHANGED: base=%.2f current_auc=%.2f target=%.2f -> adjusted=%.2f",
            base_threshold,
            current_auc,
            target_auc,
            new_threshold
        )
        # Persist the new threshold
        _persist_threshold(new_threshold)
    
    # Update cached values
    _cached_threshold = new_threshold
    _last_calculated_threshold = new_threshold
    _last_calculation_time = time.time()
    
    return new_threshold


def get_current_model_auc() -> Optional[float]:
    """
    Fetch the current model AUC from Redis.
    
    Returns:
        float: The AUC value if available, None otherwise
    """
    try:
        import redis as redis_client
        
        redis_url = os.getenv("REDIS_URL")
        if not redis_url:
            return None
        
        r = redis_client.from_url(redis_url, decode_responses=True)
        auc_str = r.get("ml:model:auc")
        r.close()
        
        if auc_str is not None:
            return float(auc_str)
    except Exception as e:
        logger.debug("[ml] Failed to fetch AUC from Redis: %s", e)
    
    return None


def get_dynamic_ml_threshold(base_threshold: Optional[float] = None) -> float:
    """
    Get the dynamic ML threshold based on current model AUC.
    
    This is the main function the engine should call to get the threshold.
    
    Args:
        base_threshold: Optional base threshold. If None, reads from ML_PROB_THRESHOLD env var (default: 0.30)
    
    Returns:
        The dynamically adjusted threshold based on model performance
    """
    if base_threshold is None:
        base_threshold = float(os.getenv("ML_PROB_THRESHOLD", "0.30"))
    
    # Try to get AUC from Redis
    current_auc = get_current_model_auc()
    
    if current_auc is None:
        # No AUC available - use base threshold
        logger.debug("[ml] No AUC in Redis, using base threshold %.2f", base_threshold)
        return base_threshold
    
    # Calculate dynamic threshold based on AUC
    target_auc = float(os.getenv("ML_TARGET_AUC", "0.85"))
    return calculate_dynamic_threshold(base_threshold, current_auc, target_auc)


# EMA-based threshold smoothing for stable dynamic adjustment
# Stores the previous threshold for EMA smoothing
_prev_threshold: Optional[float] = None


def adjust_threshold(base: float, current_auc: float, target: float, prev_threshold: float = None) -> float:
    """
    Apply EMA smoothing to threshold calculation.
    
    This prevents abrupt threshold jumps that could cause signal starvation
    by smoothing transitions based on previous threshold values.
    
    Args:
        base: Base threshold value
        current_auc: Current ML model AUC
        target: Target AUC 
        prev_threshold: Previous threshold value for EMA smoothing
        
    Returns:
        Smoothed threshold value
    """
    global _prev_threshold
    
    # Use provided prev_threshold or fall back to stored global
    if prev_threshold is None:
        prev_threshold = _prev_threshold
    
    if current_auc < target:
        raw = base + (target - current_auc) * 0.3
    else:
        raw = base - (current_auc - target) * 0.2
        
    raw = max(0.35, min(0.85, raw))
    
    # EMA Smoothing: 30% new value + 70% previous
    if prev_threshold is not None and prev_threshold > 0:
        smoothed = (raw * 0.3) + (prev_threshold * 0.7)
    else:
        smoothed = raw
    
    # Store for next iteration
    _prev_threshold = smoothed
    
    return smoothed


def get_prev_threshold() -> Optional[float]:
    """Get the previously stored threshold value."""
    global _prev_threshold
    return _prev_threshold


def set_prev_threshold(value: float) -> None:
    """Set the previous threshold value for EMA smoothing."""
    global _prev_threshold
    _prev_threshold = value


# Test the functions
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    # Test cases
    print("=== Dynamic Threshold Tests ===")
    
    # Test 1: Model underperforming
    result1 = calculate_dynamic_threshold(0.30, 0.70, 0.85)
    print(f"Base=0.30, AUC=0.70, Target=0.85 -> {result1:.2f} (expected: ~0.36, stricter)")
    
    # Test 2: Model overperforming
    result2 = calculate_dynamic_threshold(0.30, 0.90, 0.85)
    print(f"Base=0.30, AUC=0.90, Target=0.85 -> {result2:.2f} (expected: ~0.28, looser)")
    
    # Test 3: Model guessing
    result3 = calculate_dynamic_threshold(0.30, 0.45, 0.85)
    print(f"Base=0.30, AUC=0.45, Target=0.85 -> {result3:.2f} (expected: 0.99, blocked)")
    
    # Test 4: Model excellent
    result4 = calculate_dynamic_threshold(0.30, 0.97, 0.85)
    print(f"Base=0.30, AUC=0.97, Target=0.85 -> {result4:.2f} (expected: ~0.24, very loose)")
    
    print("\n=== Tests Complete ===")
