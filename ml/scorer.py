"""Simple ML scorer wrapper that exposes `score_signal` used by engine.

This module attempts to use the XGBoost-based `MLFilter` from `ml.inference` when
ML is enabled and available; otherwise falls back to a lightweight heuristic.
"""
from typing import Dict, Any

try:
    from ml.inference import MLFilter
except Exception:
    MLFilter = None


_ml = MLFilter() if MLFilter is not None else None


def score_signal(probe: Dict[str, Any]) -> float | None:
    """Return a probability in [0.0, 1.0] or None if no ML result.

    `probe` is expected to contain features such as `entry`, `stop_loss`, and
    any other engineered features produced by the strategy/market_state.
    """
    try:
        features = probe or {}
        if _ml is not None and getattr(_ml, "active", False):
            threshold_raw = features.get("threshold")
            threshold = float(threshold_raw) if threshold_raw is not None else None
            approved, prob = _ml.ml_filter(features, threshold=threshold)
            return float(prob) if prob is not None else None

        # Fallback heuristic: higher score when entry farther from stop loss
        entry = float(features.get("entry") or 0.0)
        stop = float(features.get("stop_loss") or entry)
        if entry == 0.0 or stop == entry:
            return None
        diff = abs(entry - stop)
        # Normalize to a 0-1 scale with a soft cap
        prob = min(1.0, diff / max(abs(entry), 1.0) * 10.0)
        return float(prob)
    except Exception:
        return None
