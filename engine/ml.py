from __future__ import annotations

import gc
import os
import logging
import json
import base64
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, cast

import numpy as np

try:
    import xgboost as xgb
except Exception:  # pragma: no cover - xgboost might not be present in minimal envs
    xgb = None

from ml.model_registry import load_model_with_metadata


_MODEL_CACHE: dict[str, Any] = {
    "loaded": False,
    "feature_cols": [],
    "booster": None,
    "path": None,
    "error": None,
    "version": "",
    "trained_at": "",
}
logger = logging.getLogger(__name__)
_SHADOW_CACHE: dict[str, Any] = {"loaded": False, "booster": None, "feature_cols": [], "name": "xgb_candidate", "version": None}
_STRATEGY_WEIGHT_CACHE: dict[str, Any] = {"loaded": False, "weights": {}, "updated_at": None}


def _asset_class_to_int(asset: str) -> float:
    a = str(asset or "").upper().strip()
    if a.endswith(("USDT", "USDC", "BUSD")) or (a.endswith("USD") and len(a) > 6):
        return 0.0
    clean = a.replace("/", "").replace("-", "")
    if len(clean) == 6:
        return 1.0
    if any(k in a for k in ("XAU", "XAG", "XPT", "XPD", "WTI", "BRENT", "OIL", "GOLD", "SILVER", "COPPER")):
        return 2.0
    return 3.0


def _num(value: Any, default: float = 0.0) -> float:
    try:
        return float(default if value is None else value)
    except Exception:
        return float(default)


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
    assert xgb is not None

    path = _model_path()
    if not path.exists():
        _MODEL_CACHE["error"] = f"model_missing:{path}"
        return

    try:
        booster, feature_cols, metadata, err = load_model_with_metadata(path, xgb)
        if err:
            _MODEL_CACHE["error"] = err
            return
        # Memory-optimised config for Railway 500 MB tier
            booster_any: Any = booster
            booster_any.set_param("nthread", str(int(os.getenv("XGB_NTHREAD", "2"))))
        gc.collect()  # free any cyclic garbage from model initialisation

        _MODEL_CACHE["feature_cols"] = feature_cols
        _MODEL_CACHE["booster"] = booster
        _MODEL_CACHE["version"] = str(metadata.get("version") or "")
        _MODEL_CACHE["trained_at"] = str(metadata.get("trained_at") or "")
    except Exception as exc:  # pragma: no cover - defensive
        _MODEL_CACHE["error"] = f"model_load_failed:{type(exc).__name__}"


def _load_shadow_model() -> None:
    if _SHADOW_CACHE.get("loaded"):
        return
    _SHADOW_CACHE.update({"loaded": True, "booster": None, "feature_cols": []})
    shadow_path = os.getenv("ML_CANDIDATE_MODEL_PATH", str(Path(__file__).parent.parent / "ml" / "model_candidate.json"))
    if xgb is None:
        return
    assert xgb is not None
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
        booster.set_param("nthread", str(int(os.getenv("XGB_NTHREAD", "2"))))
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
        macro = dict(signal.get("_macro") or {})
        strength = float(signal.get("strength") or 0.0)
        partial_tp_progress = _num(signal.get("partial_tp_progress"), 0.0)
        price_velocity_3 = _num(signal.get("price_velocity_3"), 0.0)
        price_velocity_5 = _num(signal.get("price_velocity_5"), 0.0)
        price_velocity_10 = _num(signal.get("price_velocity_10"), 0.0)
        price_acceleration_3_10 = _num(signal.get("price_acceleration_3_10"), price_velocity_3 - price_velocity_10)
        atr_rel = _num(signal.get("atr_rel"), 0.0)
        atr_regime = _num(signal.get("atr_regime"), 0.0)
        relative_volume = _num(signal.get("relative_volume"), 0.0)
        mtf_4h_trend = _num(signal.get("mtf_4h_trend"), 0.0)
        mtf_1d_trend = _num(signal.get("mtf_1d_trend"), 0.0)
        funding_rate = _num(signal.get("funding_rate"), 0.0)
        open_interest_change = _num(signal.get("open_interest_change"), 0.0)
        dxy_trend = _num(signal.get("dxy_trend"), 0.0)
        spx_trend = _num(signal.get("spx_trend"), 0.0)
        btc_corr = _num(signal.get("btc_corr"), 0.0)

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
            "asset_class_enc": _num(signal.get("asset_class_enc"), _asset_class_to_int(asset)),
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
            "dxy_trend": _num(signal.get("dxy_trend"), _num(macro.get("dxy_trend"), dxy_trend)),
            "vix_trend": _num(signal.get("vix_trend"), _num(macro.get("vix_trend"), 0.0)),
            "us10y_trend": _num(signal.get("us10y_trend"), _num(macro.get("us10y_trend"), 0.0)),
            "yield_spread": _num(signal.get("yield_spread"), _num(macro.get("yield_spread"), 0.0)),
            "minutes_since_high_impact_news": _num(signal.get("minutes_since_high_impact_news"), _num(macro.get("minutes_since_high_impact_news"), 0.0)),
            "minutes_until_high_impact_news": _num(signal.get("minutes_until_high_impact_news"), _num(macro.get("minutes_until_high_impact_news"), 0.0)),
            "news_event_impact_score": _num(signal.get("news_event_impact_score"), _num(macro.get("news_event_impact_score"), 0.0)),
            "exchange_net_flow": _num(signal.get("exchange_net_flow"), _num(macro.get("exchange_net_flow"), 0.0)),
            "exchange_inflow": _num(signal.get("exchange_inflow"), _num(macro.get("exchange_inflow"), 0.0)),
            "exchange_outflow": _num(signal.get("exchange_outflow"), _num(macro.get("exchange_outflow"), 0.0)),
            "liquidation_heatmap_score": _num(signal.get("liquidation_heatmap_score"), _num(macro.get("liquidation_heatmap_score"), 0.0)),
            "liquidation_heatmap_density": _num(signal.get("liquidation_heatmap_density"), _num(macro.get("liquidation_heatmap_density"), 0.0)),
            "onchain_source_flag": _num(signal.get("onchain_source_flag"), 1.0 if macro.get("onchain_source") not in (None, "", "none") else 0.0),
            "spx_trend": _num(signal.get("spx_trend"), _num(macro.get("spx_trend"), spx_trend)),
            "btc_corr": _num(signal.get("btc_corr"), _num(macro.get("btc_corr"), btc_corr)),
        }

        missing = [col for col in feature_cols if col not in values]
        if missing:
            preview = ",".join(missing[:8])
            suffix = f" (+{len(missing)-8} more)" if len(missing) > 8 else ""
            logger.warning("[ml] schema mismatch: missing features=%s%s", preview, suffix)
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
        assert xgb is not None
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
                        assert xgb is not None
                        dm_shadow = xgb.DMatrix(x_shadow, feature_names=sh_cols)
                        sh_preds = sh_booster.predict(dm_shadow)
                        if sh_preds is not None and len(sh_preds) > 0:
                            _persist_shadow_prediction(signal, float(sh_preds[0]), schema_ok=schema_ok)
            except Exception as shadow_exc:
                logger.debug("[ml-shadow] scoring skipped: %s", shadow_exc)
        return prob
    except Exception:  # pragma: no cover - defensive
        return None


def scored_signals_with_ml(signals: Iterable[Dict[str, Any]], threshold: float | None = None) -> list[Dict[str, Any]]:
    """Attach ML probability to each signal and mark pass/fail by threshold.

    Fail-open: if ML is unavailable, signals are returned with ml_pass=True.
    If threshold is None, ML results are advisory only (ml_pass=True).
    """
    scored: list[Dict[str, Any]] = []
    for sig in signals or []:
        prob = score_signal(sig)
        out = dict(sig)
        if prob is None:
            out["ml_probability"] = None
            out["ml_pass"] = True
        else:
            out["ml_probability"] = float(prob)
            if threshold is None:
                out["ml_pass"] = True
            else:
                out["ml_pass"] = float(prob) >= float(threshold)
        scored.append(out)
    return scored


# Backward-compatible helpers (used by other modules)
def get_strategy_weights() -> Dict[str, float]:
    raw = (os.getenv("STRATEGY_WEIGHTS_JSON") or os.getenv("STRATEGY_WEIGHTS") or "").strip()
    if not raw:
        return {}
    try:
        payload = json.loads(raw)
        weights: Dict[str, float] = {}
        if isinstance(payload, dict):
            for key, value in payload.items():
                try:
                    weights[str(key)] = float(value)
                except Exception:
                    continue
        return weights
    except Exception:
        weights = {}
        for item in raw.split(","):
            if ":" not in item:
                continue
            name, val = item.split(":", 1)
            try:
                weights[name.strip()] = float(val)
            except Exception:
                continue
        return weights


def get_regime_strategies() -> Dict[str, list[str]]:
    raw = (os.getenv("REGIME_STRATEGIES_JSON") or os.getenv("REGIME_STRATEGIES") or "").strip()
    if not raw:
        return {}
    try:
        payload = json.loads(raw)
        mapping: Dict[str, list[str]] = {}
        if isinstance(payload, dict):
            for key, value in payload.items():
                try:
                    mapping[str(key)] = [str(item).strip() for item in (value or []) if str(item).strip()]
                except Exception:
                    continue
        return mapping
    except Exception:
        mapping: Dict[str, list[str]] = {}
        for item in raw.split(";"):
            if ":" not in item:
                continue
            regime, strategies = item.split(":", 1)
            mapping[str(regime).strip()] = [s.strip() for s in strategies.split(",") if s.strip()]
        return mapping


def weekly_job() -> bool:
    """Run weekly ML retrain job if enabled."""
    if str(os.getenv("ML_WEEKLY_RETRAIN_ENABLED", "0")).strip().lower() not in {"1", "true", "yes", "on"}:
        return False
    try:
        from ml.retrain import retrain_model
        from utils.async_runner import run_sync  # type: ignore[import-untyped]
        return bool(run_sync(retrain_model(), timeout=1200.0))
    except Exception:
        return False


def adjust_weight_based_on_performance(perf: Optional[Dict[str, Any]]) -> Optional[float]:
    """Adjust strategy weight based on recent performance.

    Minimal backward-compatible helper: return None when no performance
    data is provided. Real implementation will use CV and smoothing.
    """
    if perf is None:
        return None
    # No-op by design for now
    return None


def disable_strategies_with_drawdown() -> list[str]:
    """Disable strategies when drawdown thresholds exceeded.

    Reads STRATEGY_DRAWDOWN_DISABLE_LIST (comma-separated) to allow ops-driven
    disables without code changes. Returns an empty list when nothing is set.
    """
    raw = (os.getenv("STRATEGY_DRAWDOWN_DISABLE_LIST") or "").strip()
    if not raw:
        return []
    return [s.strip() for s in raw.split(",") if s.strip()]


def _strategy_perf_key(name: str) -> str:
    return f"ml:strategy_perf:{str(name or '').strip().lower()}"


def _strategy_weight_key(name: str) -> str:
    return f"ml:strategy_weight:{str(name or '').strip().lower()}"


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value if value is not None else default)
    except Exception:
        return float(default)


def _weight_from_performance(perf: Dict[str, Any]) -> float:
    """Convert rolling performance into a normalized weight.

    The formula intentionally rewards a mix of win rate, expectancy, and
    signal frequency. This avoids overfitting to one lucky large winner.
    """

    if not perf:
        return 1.0
    win_rate = max(0.0, min(1.0, _safe_float(perf.get("win_rate"), 0.5)))
    expectancy = _safe_float(perf.get("expectancy"), 0.0)
    avg_rr = max(0.0, _safe_float(perf.get("avg_rr"), 1.0))
    trades = max(0.0, _safe_float(perf.get("trades"), 0.0))
    recent_trades = max(0.0, _safe_float(perf.get("recent_trades"), trades))
    if trades <= 0:
        return 1.0

    trade_confidence = min(1.0, recent_trades / 50.0)
    expectancy_term = 1.0 + max(-0.4, min(0.6, expectancy / 10.0))
    rr_term = 0.8 + min(0.4, avg_rr / 10.0)
    base = (0.45 * win_rate) + (0.25 * trade_confidence) + (0.15 * expectancy_term) + (0.15 * rr_term)
    return max(0.25, min(2.0, base * 1.25))


async def update_strategy_weight(strategy_name: str, perf: Optional[Dict[str, Any]]) -> float:
    """Persist a rolling strategy weight derived from live performance.

    The cache is stored in Postgres-backed runtime state when available, and is
    also mirrored in-process so the ranking layer can consume it cheaply.
    """

    weight = _weight_from_performance(perf or {})
    name = str(strategy_name or "").strip()
    if not name:
        return weight
    cache_key = name.lower()
    _STRATEGY_WEIGHT_CACHE.setdefault("weights", {})[cache_key] = {
        "weight": float(weight),
        "updated_at": datetime.utcnow().isoformat(),
        "name": name,
    }
    _STRATEGY_WEIGHT_CACHE["updated_at"] = datetime.utcnow().isoformat()

    try:
        from core.redis_state import state
        payload = {
            "strategy_name": name,
            "weight": float(weight),
            "perf": dict(perf or {}),
            "updated_at": datetime.utcnow().isoformat(),
        }
        state.set_sync(_strategy_weight_key(name), json.dumps(payload), ex=7 * 24 * 3600)
    except Exception:
        pass

    return float(weight)


def get_live_strategy_weight(strategy_name: str, default: float = 1.0) -> float:
    name = str(strategy_name or "").strip()
    if not name:
        return float(default)
    cache_key = name.lower()

    cached = _STRATEGY_WEIGHT_CACHE.get("weights", {}).get(cache_key)
    if isinstance(cached, dict):
        try:
            return float(cached.get("weight", default))
        except Exception:
            return float(default)

    try:
        from core.redis_state import state
        raw = state.get_sync(_strategy_weight_key(name))
        if raw:
            payload = json.loads(raw)
            if isinstance(payload, dict):
                weight = _safe_float(payload.get("weight"), default)
                _STRATEGY_WEIGHT_CACHE.setdefault("weights", {})[cache_key] = {
                    "weight": weight,
                    "updated_at": payload.get("updated_at"),
                    "name": name,
                }
                return weight
    except Exception:
        pass
    return float(default)


def get_strategy_weight_map() -> Dict[str, float]:
    weights = {}
    try:
        for name, payload in (_STRATEGY_WEIGHT_CACHE.get("weights") or {}).items():
            if isinstance(payload, dict):
                label = str(payload.get("name") or name)
                weights[label] = float(payload.get("weight", 1.0))
    except Exception:
        pass
    return weights
