"""Asset-class specialist models (owner request, 10 Nov 2026).

"Keep the gates, but update the ML: different strategies work for different
assets in different asset classes; train based on all of this."

One global model ranks every candidate. A specialist is an extra model trained
only on one asset class (crypto, FX, metals/energy, stocks/indices), on the same
feature contract. Strategy, regime, direction and timeframe-sensitive features
are inputs, so each specialist learns which strategies work in *its* class.

Gates are unchanged and applied per specialist: the class's rows get their own
chronological fit / calibration / untouched-validation split
(``ml.train_model.train_model``) and the specialist must clear the same
promotion quality gate (``_promotion_quality_gate``), including the
train/validation overfit gap, on its own validation window. Classes without a
passing specialist keep the global model. Specialists ride inside the model
artifact (``"specialists"``), so a challenger with specialists goes through the
same forward proof and owner promotion as any challenger.

At scoring time ``Router.route`` picks the specialist for the candidate's
``asset_class_enc``; its own certified threshold and calibration apply.
"""
from __future__ import annotations

import base64
import logging
import os
from typing import Any, Optional

logger = logging.getLogger(__name__)

CLASS_NAMES = {0: "crypto", 1: "fx", 2: "metals_energy", 3: "stocks_indices"}


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)) or default)
    except ValueError:
        return default


def enabled() -> bool:
    return str(os.getenv("ML_SPECIALISTS_ENABLED", "1")).strip().lower() in {"1", "true", "yes", "on"}


def class_key(value: Any) -> Optional[str]:
    try:
        return str(int(round(float(value))))
    except (TypeError, ValueError):
        return None


def train_specialists(X, y, feature_cols, sample_weights=None, timestamps=None, fit_only_mask=None, *,
                      deployed_runtime: bool = False) -> dict[str, dict[str, Any]]:
    """Train one model per asset class with enough rows; return every result with its gate verdict."""
    import numpy as np

    from ml.train_model import _promotion_quality_gate, train_model

    results: dict[str, dict[str, Any]] = {}
    if not enabled() or "asset_class_enc" not in getattr(X, "columns", []):
        return results
    min_rows = max(200, _env_int("ML_SPECIALIST_MIN_ROWS", 600))
    classes = X["asset_class_enc"].round().astype(int)
    own = np.ones(len(X), dtype=bool) if fit_only_mask is None else ~np.asarray(fit_only_mask, dtype=bool)
    for value in sorted(set(classes.tolist())):
        key = class_key(value)
        mask = (classes == value).to_numpy()
        own_rows = int((mask & own).sum())
        name = CLASS_NAMES.get(int(value), f"class_{value}")
        if own_rows < min_rows:
            results[key] = {"name": name, "rows": own_rows, "passed": False, "reason": "too_few_rows"}
            continue
        idx = np.flatnonzero(mask)
        y_sub = y.iloc[idx]
        if len(set(y_sub.tolist())) < 2:
            results[key] = {"name": name, "rows": own_rows, "passed": False, "reason": "one_outcome_class"}
            continue
        try:
            model, cols, cal_x, cal_y, metrics = train_model(
                X.iloc[idx], y_sub, list(feature_cols),
                None if sample_weights is None else sample_weights.iloc[idx],
                None if timestamps is None else (timestamps.iloc[idx] if hasattr(timestamps, "iloc") else
                                                 np.asarray(timestamps)[idx]),
                None if fit_only_mask is None else np.asarray(fit_only_mask, dtype=bool)[idx],
            )
        except Exception as exc:  # a class too small to split must not fail the whole run
            results[key] = {"name": name, "rows": own_rows, "passed": False, "reason": f"train_failed:{type(exc).__name__}"}
            continue
        passed, _min_acc, _min_auc = _promotion_quality_gate(metrics, deployed_runtime=deployed_runtime)
        calibration_ok = bool((metrics.get("calibration") or {}).get("validated", True))
        results[key] = {
            "name": name, "rows": own_rows, "passed": bool(passed and calibration_ok),
            "reason": "passed" if passed and calibration_ok else ("calibration" if passed else "quality_gate"),
            "model": model, "feature_cols": list(cols), "calibration_x": list(cal_x or []),
            "calibration_y": list(cal_y or []), "metrics": metrics,
        }
        logger.info("[ml_specialist] class=%s rows=%s passed=%s auc=%s gap=%s expected_r=%s", name, own_rows,
                    results[key]["passed"], round(float(metrics.get("auc") or 0), 4), metrics.get("overfit_gap"),
                    metrics.get("expected_r"))
    return results


def summary(results: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Counts and gate numbers per class (no model bytes), for logs and /ml_status."""
    out = {}
    for key, r in results.items():
        m = r.get("metrics") or {}
        out[r.get("name", key)] = {
            "rows": r.get("rows"), "passed": r.get("passed"), "reason": r.get("reason"),
            "auc": None if not m else round(float(m.get("auc") or 0), 4),
            "overfit_gap": None if m.get("overfit_gap") is None else round(float(m["overfit_gap"]), 4),
            "expected_r": m.get("expected_r"), "balanced_accuracy": m.get("balanced_accuracy"),
        }
    return out


def payload(results: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Artifact form of the *passing* specialists."""
    out: dict[str, dict[str, Any]] = {}
    for key, r in results.items():
        if not r.get("passed") or r.get("model") is None:
            continue
        raw = r["model"].get_booster().save_raw("ubj")
        out[key] = {
            "name": r["name"], "rows": r["rows"], "feature_cols": r["feature_cols"],
            "model_bytes_b64": base64.b64encode(bytes(raw)).decode("ascii"),
            "calibration_x": r["calibration_x"], "calibration_y": r["calibration_y"],
            "classification_threshold": (r.get("metrics") or {}).get("classification_threshold"),
            "metrics": {k: v for k, v in (r.get("metrics") or {}).items() if not isinstance(v, (dict, list))},
        }
    return out


class Router:
    """Loads specialists from an artifact payload and scores a candidate with the right one."""

    def __init__(self, specialists: Optional[dict[str, Any]]) -> None:
        self.models: dict[str, dict[str, Any]] = {}
        if not specialists or not enabled():
            return
        try:
            import xgboost as xgb
        except Exception:  # pragma: no cover - xgboost is a hard dependency in deployed images
            return
        for key, spec in dict(specialists).items():
            try:
                booster = xgb.Booster()
                booster.load_model(bytearray(base64.b64decode(spec["model_bytes_b64"])))
                threshold = spec.get("classification_threshold")
                self.models[str(key)] = {
                    "booster": booster, "feature_cols": list(spec.get("feature_cols") or []),
                    "calibration_x": list(spec.get("calibration_x") or []),
                    "calibration_y": list(spec.get("calibration_y") or []),
                    "threshold": None if threshold is None else max(0.05, min(0.95, float(threshold))),
                    "name": spec.get("name") or key,
                }
            except Exception as exc:
                logger.warning("[ml_specialist] load failed class=%s error=%s", key, type(exc).__name__)

    def route(self, features: dict[str, Any]) -> Optional[dict[str, Any]]:
        if not self.models:
            return None
        key = class_key((features or {}).get("asset_class_enc"))
        return self.models.get(key) if key is not None else None

    @staticmethod
    def predict(spec: dict[str, Any], features: dict[str, Any]) -> tuple[float, float]:
        """(raw probability, calibrated probability)."""
        import numpy as np
        import xgboost as xgb

        cols = spec["feature_cols"]
        vector = np.array([[float((features or {}).get(c, 0.0) or 0.0) for c in cols]], dtype=np.float32)
        raw = float(spec["booster"].predict(xgb.DMatrix(vector, feature_names=cols))[0])
        xs, ys = spec["calibration_x"], spec["calibration_y"]
        calibrated = float(np.interp(raw, xs, ys, left=ys[0], right=ys[-1])) if len(xs) >= 2 and len(xs) == len(ys) else raw
        return raw, calibrated
