"""
Dynamic Threshold Wrapper for Engine

Wraps the ML dynamic threshold functions with fallback handling.
This creates a self-healing system where:
- If model AUC drops (market drift), threshold increases (stricter)
- If model AUC rises, threshold decreases (more signals)
"""

import os
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Try to import from ml.dynamic_threshold, with graceful fallback
try:
    from ml.dynamic_threshold import (
        calculate_dynamic_threshold as _ml_calculate_threshold,
        get_current_model_auc as _get_ml_auc,
        get_dynamic_ml_threshold as _get_dynamic_threshold,
    )
except ImportError as e:
    logger.warning(f"[engine] ml.dynamic_threshold not available: {e}")
    # Stub functions
    def _ml_calculate_threshold(*args, **kwargs):
        return 0.30
    def _get_ml_auc():
        return None
    def _get_dynamic_threshold(*args, **kwargs):
        return 0.30


def calculate_dynamic_threshold(
    base_threshold: Optional[float] = None,
    current_auc: Optional[float] = None,
    target_auc: float = 0.85
) -> float:
    """
    Calculate dynamic threshold based on ML model AUC.
    
    This is the main function the engine calls to get the threshold.
    
    If base_threshold is None, reads from ML_PROB_THRESHOLD env var (default: 0.30)
    If current_auc is None, fetches from Redis key "ml:model:auc"
    
    Args:
        base_threshold: Base ML probability threshold. If None, uses env var.
        current_auc: Current model AUC. If None, fetches from Redis.
        target_auc: Target AUC to normalize against (default: 0.85)
    
    Returns:
        Dynamically adjusted threshold based on model performance
    """
    # Get base threshold from env if not provided
    if base_threshold is None:
        base_threshold = float(os.getenv("ML_PROB_THRESHOLD", "0.30"))
    
    # Try to get AUC from Redis if not provided
    if current_auc is None:
        current_auc = _get_ml_auc()
    
    # If no AUC available, return base threshold
    if current_auc is None:
        logger.debug("[engine] No AUC available, using base threshold %.2f", base_threshold)
        return base_threshold
    
    # Calculate dynamic threshold
    try:
        return _ml_calculate_threshold(base_threshold, current_auc, target_auc)
    except Exception as e:
        logger.warning(f"[engine] Dynamic threshold calculation failed: {e}, using base")
        return base_threshold


def get_ml_model_auc() -> Optional[float]:
    """Get the current ML model AUC from Redis."""
    return _get_ml_auc()


# Default function matching the interface used in engine/core.py
def get_threshold() -> float:
    """Get the current ML probability threshold with dynamic AUC-based adjustment."""
    return calculate_dynamic_threshold()


# Convenience function for engine/core.py import
__all__ = [
    "calculate_dynamic_threshold",
    "get_ml_model_auc", 
    "get_threshold",
]
