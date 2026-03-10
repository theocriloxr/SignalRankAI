from __future__ import annotations

import base64
import gc
import json
import os
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

import numpy as np

try:
    import xgboost as xgb
except Exception:  # pragma: no cover - xgboost might not be present in minimal envs
    xgb = None


_MODEL_CACHE: dict[str, Any] = {
    "loaded": False,
    "feature_cols": [],
    "booster": None,
    "path": None,
    "error": None,
}


def _model_path() -> Path:
    raw = os.getenv("ML_MODEL_PATH")
    if raw:
        return Path(raw)
    return Path(__file__).parent.parent / "ml" / "model.json"


def _load_model() -> None:
    if _MODEL_CACHE["loaded"]:
        return
    _MODEL_CACHE.update({"loaded": True, "feature_cols": [], "booster": None, "path": str(_model_path()), "error": None})

    if xgb is None:
        _MODEL_CACHE["error"] = "xgboost_not_installed"
        return

    path = _model_path()
    if not path.exists():
        _MODEL_CACHE["error"] = f"model_missing:{path}"
        return

    try:
        with open(path, "r", encoding="utf-8") as f:
            payload = json.load(f)
        feature_cols: List[str] = list(payload.get("feature_cols") or [])
        model_bytes_b64 = payload.get("model_bytes_b64")
        if not model_bytes_b64 or not feature_cols:
            _MODEL_CACHE["error"] = "model_payload_invalid"
            return

        raw_bytes = base64.b64decode(model_bytes_b64)
        booster = xgb.Booster()
        # Memory-optimised config for Railway 500 MB tier
        booster.set_param("nthread", int(os.getenv("XGB_NTHREAD", "2")))
        booster.load_model(bytearray(raw_bytes))
        del raw_bytes  # release raw bytes immediately
        gc.collect()  # free any cyclic garbage from model initialisation

        _MODEL_CACHE["feature_cols"] = feature_cols
        _MODEL_CACHE["booster"] = booster
    except Exception as exc:  # pragma: no cover - defensive
        _MODEL_CACHE["error"] = f"model_load_failed:{type(exc).__name__}"


def _feature_vector(signal: Dict[str, Any], feature_cols: Iterable[str]) -> Optional[np.ndarray]:
    try:
        s_score = float(signal.get("score") or 0.0)
        rr = float(signal.get("rr_ratio") or signal.get("rr_estimate") or 1.0)
        entry = float(signal.get("entry") or 0.0)
        sl = float(signal.get("stop_loss") or 0.0)
        tp = float(signal.get("take_profit") or 0.0)
        direction = str(signal.get("direction") or "long").lower()
        regime = str(signal.get("regime") or "neutral").lower()
        strategy = str(signal.get("strategy_name") or "unknown").lower()
        asset = str(signal.get("asset") or "unknown").upper()
        timeframe = str(signal.get("timeframe") or "1d").lower()
        strength = float(signal.get("strength") or 0.0)

        price_range = abs(tp - entry) / (entry + 1e-6)
        risk_amount = abs(entry - sl) / (entry + 1e-6)
        spread_ratio = risk_amount / (price_range + 1e-6)
        strength_norm = strength / 100.0 if strength > 1 else strength
        high_score = 1.0 if s_score >= 75 else 0.0
        medium_score = 1.0 if 60 <= s_score < 75 else 0.0
        is_long = 1.0 if direction == "long" else 0.0

        # Simple hash encodings for categorical features to stay deterministic without fitted encoders.
        def _hash_bucket(val: str, buckets: int = 64) -> float:
            return float(abs(hash(val)) % buckets)

        values = {
            "score_normalized": s_score / 100.0,
            "risk_reward_ratio": rr,
            "price_range": price_range,
            "risk_amount": risk_amount,
            "spread_ratio": spread_ratio,
            "strength_normalized": strength_norm,
            "direction_enc": _hash_bucket(direction),
            "regime_enc": _hash_bucket(regime),
            "strategy_enc": _hash_bucket(strategy),
            "asset_enc": _hash_bucket(asset),
            "timeframe_enc": _hash_bucket(timeframe),
            "high_score": high_score,
            "medium_score": medium_score,
            "is_long": is_long,
        }

        vec = [float(values.get(col, 0.0)) for col in feature_cols]
        return np.asarray([vec], dtype=np.float32)
    except Exception:
        return None


def score_signal(signal: Dict[str, Any]) -> Optional[float]:
    """Return ML probability (0-1) for a signal or None if unavailable."""

    _load_model()
    booster = _MODEL_CACHE.get("booster")
    feature_cols: List[str] = _MODEL_CACHE.get("feature_cols") or []
    if booster is None or not feature_cols:
        return None

    x = _feature_vector(signal, feature_cols)
    if x is None:
        return None

    try:
        dm = xgb.DMatrix(x, feature_names=feature_cols)
        preds = booster.predict(dm)
        del dm  # release DMatrix immediately
        gc.collect()  # free cyclic garbage after inference
        if preds is None or len(preds) == 0:
            return None
        prob = float(preds[0])
        if prob < 0 or prob > 1:
            return None
        return prob
    except Exception:  # pragma: no cover - defensive
        return None


# Backward-compatible helpers (used by other modules)
def get_strategy_weights():
    return {}


def get_regime_strategies():
    return {}


def weekly_job():
    return


def adjust_weight_based_on_performance(perf: Optional[Dict[str, Any]]) -> Optional[float]:
    """Adjust strategy weight based on recent performance.

    Minimal backward-compatible helper: return None when no performance
    data is provided. Real implementation will use CV and smoothing.
    """
    if perf is None:
        return None
    # No-op by design for now
    return None


def disable_strategies_with_drawdown() -> list:
    """Disable strategies when drawdown thresholds exceeded (currently no-op).

    Returns an empty list for now; real implementation will inspect
    portfolio/strategy metrics and return strategy names to disable.
    """
    return None
