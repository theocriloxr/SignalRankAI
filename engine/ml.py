from __future__ import annotations

import base64
import gc
import json
import os
import logging
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
logger = logging.getLogger(__name__)
_SHADOW_CACHE: dict[str, Any] = {"loaded": False, "booster": None, "feature_cols": [], "name": "xgb_candidate", "version": None}


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


def _load_shadow_model() -> None:
    if _SHADOW_CACHE.get("loaded"):
        return
    _SHADOW_CACHE.update({"loaded": True, "booster": None, "feature_cols": []})
    shadow_path = os.getenv("ML_CANDIDATE_MODEL_PATH", str(Path(__file__).parent.parent / "ml" / "model_candidate.json"))
    if xgb is None:
        return
    p = Path(shadow_path)
    if not p.exists():
        return
    try:
        payload = json.loads(p.read_text(encoding="utf-8"))
        feature_cols: List[str] = list(payload.get("feature_cols") or [])
        model_bytes_b64 = payload.get("model_bytes_b64")
        if not model_bytes_b64 or not feature_cols:
            return
        raw_bytes = base64.b64decode(model_bytes_b64)
        booster = xgb.Booster()
        booster.set_param("nthread", int(os.getenv("XGB_NTHREAD", "2")))
        booster.load_model(bytearray(raw_bytes))
        _SHADOW_CACHE["booster"] = booster
        _SHADOW_CACHE["feature_cols"] = feature_cols
        _SHADOW_CACHE["version"] = str(payload.get("version") or "unknown")
    except Exception as exc:
        logger.warning("[ml-shadow] failed to load candidate model: %s", exc)


def _persist_shadow_prediction(signal: Dict[str, Any], prob: float, schema_ok: bool) -> None:
    try:
        from utils.async_runner import run_sync
        from db.session import get_session
        from db.models import MLShadowPrediction

        async def _save():
            async with get_session() as session:
                row = MLShadowPrediction(
                    signal_id=str(signal.get("signal_id") or "") or None,
                    model_name=str(_SHADOW_CACHE.get("name") or "xgb_candidate"),
                    model_version=str(_SHADOW_CACHE.get("version") or "unknown"),
                    probability=float(prob),
                    is_shadow=True,
                    feature_schema_ok=bool(schema_ok),
                    meta={"asset": signal.get("asset"), "timeframe": signal.get("timeframe")},
                )
                session.add(row)
                await session.commit()

        run_sync(_save())
    except Exception as exc:
        logger.debug("[ml-shadow] persist failed: %s", exc)


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
        partial_tp_progress = float(signal.get("partial_tp_progress") or 0.0)
        price_velocity_3 = float(signal.get("price_velocity_3") or 0.0)
        price_velocity_5 = float(signal.get("price_velocity_5") or 0.0)
        price_velocity_10 = float(signal.get("price_velocity_10") or 0.0)
        price_acceleration_3_10 = float(signal.get("price_acceleration_3_10") or (price_velocity_3 - price_velocity_10))
        atr_rel = float(signal.get("atr_rel") or 0.0)
        atr_regime = float(signal.get("atr_regime") or 0.0)
        relative_volume = float(signal.get("relative_volume") or 0.0)
        mtf_4h_trend = float(signal.get("mtf_4h_trend") or 0.0)
        mtf_1d_trend = float(signal.get("mtf_1d_trend") or 0.0)
        funding_rate = float(signal.get("funding_rate") or 0.0)
        open_interest_change = float(signal.get("open_interest_change") or 0.0)
        dxy_trend = float(signal.get("dxy_trend") or 0.0)
        spx_trend = float(signal.get("spx_trend") or 0.0)
        btc_corr = float(signal.get("btc_corr") or 0.0)

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
            "partial_tp_progress_norm": max(0.0, min(1.0, partial_tp_progress / 3.0)),
            "price_velocity_3": price_velocity_3,
            "price_velocity_5": price_velocity_5,
            "price_velocity_10": price_velocity_10,
            "price_acceleration_3_10": price_acceleration_3_10,
            "velocity_abs_3": abs(price_velocity_3),
            "velocity_abs_10": abs(price_velocity_10),
            "atr_rel": atr_rel,
            "atr_regime_clamped": max(0.0, min(5.0, atr_regime)),
            "relative_volume_clamped": max(0.0, min(10.0, relative_volume)),
            "mtf_4h_trend": mtf_4h_trend,
            "mtf_1d_trend": mtf_1d_trend,
            "funding_rate": funding_rate,
            "open_interest_change": open_interest_change,
            "dxy_trend": dxy_trend,
            "spx_trend": spx_trend,
            "btc_corr": btc_corr,
        }

        missing = [col for col in feature_cols if col not in values]
        if missing:
            logger.warning("[ml] schema mismatch: missing features=%s", ",".join(missing[:8]))
            if str(os.getenv("ML_STRICT_SCHEMA", "0")).strip().lower() in {"1", "true", "yes", "on"}:
                return None
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
        # Shadow mode: evaluate candidate model silently and persist.
        if str(os.getenv("ML_SHADOW_MODE", "1")).strip().lower() in {"1", "true", "yes", "on"}:
            try:
                _load_shadow_model()
                sh_booster = _SHADOW_CACHE.get("booster")
                sh_cols: List[str] = _SHADOW_CACHE.get("feature_cols") or []
                if sh_booster is not None and sh_cols:
                    x_shadow = _feature_vector(signal, sh_cols)
                    schema_ok = x_shadow is not None
                    if x_shadow is not None:
                        dm_shadow = xgb.DMatrix(x_shadow, feature_names=sh_cols)
                        sh_preds = sh_booster.predict(dm_shadow)
                        if sh_preds is not None and len(sh_preds) > 0:
                            _persist_shadow_prediction(signal, float(sh_preds[0]), schema_ok=schema_ok)
            except Exception as shadow_exc:
                logger.debug("[ml-shadow] scoring skipped: %s", shadow_exc)
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
