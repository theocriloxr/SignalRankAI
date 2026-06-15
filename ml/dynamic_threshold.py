"""
Dynamic Threshold Calculator

Auto-adjusts the ML probability threshold based on model AUC performance.
This creates a self-healing system where:
- If model AUC drops (market drift), threshold increases (stricter)
- If model AUC rises, threshold decreases (more signals)
"""

import os
import logging
from typing import Optional

logger = logging.getLogger(__name__)


def calculate_dynamic_threshold(
    base_threshold: float, 
    current_auc: float, 
    target_auc: float = 0.85
) -> float:
    """
    Auto-adjusts the required score threshold based on the ML model's current performance.
    
    If the model is performing poorly (low AUC), it becomes stricter.
    If the model is performing well (high AUC), it loosens the threshold.
    
    Args:
        base_threshold: The base ML probability threshold (e.g., 0.30)
        current_auc: The current model AUC from training (0.0-1.0)
        target_auc: The target AUC to normalize against (default: 0.85)
    
    Returns:
        Dynamic threshold adjusted based on model performance
    
    Example:
        >>> calculate_dynamic_threshold(0.30, 0.70, 0.85)
        0.36  # Stricter because model is underperforming (0.70 < 0.85)
        >>> calculate_dynamic_threshold(0.30, 0.90, 0.85)
        0.28  # Looser because model is overperforming (0.90 > 0.85)
    """
    # Model is essentially guessing - block almost all trades
    if current_auc <= 0.50:
        logger.warning("[ml] Model AUC %.2f <= 0.50 (guessing); blocking with threshold 0.99", current_auc)
        return 0.99
    
    # Model is very strong - allow more trades
    if current_auc >= 0.95:
        logger.info("[ml] Model AUC %.2f >= 0.95 (excellent); loosening threshold", current_auc)
        return max(0.10, base_threshold * 0.8)
    
# Scale the threshold inversely to model performance
    # If current_auc < target_auc, ratio < 1.0, threshold increases (stricter)
    # If current_auc > target_auc, ratio > 1.0, threshold decreases (looser)
    adjustment_factor = target_auc / current_auc
    dynamic_threshold = base_threshold * adjustment_factor
    
    # Clamp to reasonable bounds
    min_threshold = max(0.10, base_threshold * 0.5)  # At least 50% of base
    max_threshold = min(0.70, base_threshold * 1.5)  # At most 150% of base
    
    final_threshold = max(min_threshold, min(max_threshold, dynamic_threshold))
    
    logger.info(
        "[ml] Dynamic threshold: base=%.2f current_auc=%.2f target=%.2f -> adjusted=%.2f",
        base_threshold,
        current_auc,
        target_auc,
        final_threshold
    )
    
    return final_threshold


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
