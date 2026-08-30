"""Versioned ML feature contracts.

Version 3 mirrors the production signal-quality training pipeline. Legacy
retraining remains isolated on its smaller version-1 feature set so missing
advanced features cannot silently become a new production model.
"""
from __future__ import annotations

import math
import os
from typing import Any

CURRENT_SCHEMA_VERSION = 3
MODEL_FORMAT_VERSION = 3
FEATURE_SCHEMA_VERSION = "feature-schema-v3"
LABEL_SCHEMA_VERSION = "label-schema-v1"

LEGACY_RETRAIN_FEATURE_COLUMNS = [
    "rr_estimate", "score", "strength", "regime_score", "trend_ema", "rsi",
    "volume_ratio", "macd_trend", "adx_value", "news_sentiment",
    "nearest_support_dist", "nearest_resistance_dist", "asset_class_enc",
    "dxy_trend", "vix_trend", "us10y_trend", "yield_spread",
    "minutes_since_high_impact_news", "minutes_until_high_impact_news",
    "news_event_impact_score",
]

FEATURE_COLUMNS_V3 = [
    "score_normalized", "risk_reward_ratio", "price_range", "risk_amount",
    "spread_ratio", "strength_normalized", "direction_enc", "regime_enc",
    "strategy_enc", "high_score", "medium_score", "is_long", "asset_class_enc",
    "price_velocity_3", "price_velocity_5", "price_velocity_10",
    "price_acceleration_3_10", "velocity_abs_3", "velocity_abs_10",
    "atr_rel", "atr_regime_clamped", "relative_volume_clamped",
    "mtf_4h_trend", "mtf_1d_trend", "funding_rate", "open_interest_change",
    "dxy_trend", "vix_trend", "us10y_trend", "yield_spread",
    "minutes_since_high_impact_news", "minutes_until_high_impact_news",
    "news_event_impact_score", "spx_trend", "btc_corr",
]

CRITICAL_FEATURES_V3 = frozenset({
    "score_normalized", "risk_reward_ratio", "price_range", "risk_amount",
    "direction_enc", "regime_enc", "strategy_enc", "asset_class_enc",
})


def get_current_schema_version() -> int:
    return CURRENT_SCHEMA_VERSION


def get_feature_columns() -> list[str]:
    return list(FEATURE_COLUMNS_V3)


def get_legacy_retrain_feature_columns() -> list[str]:
    return list(LEGACY_RETRAIN_FEATURE_COLUMNS)


def normalize_feature_columns(cols: Any) -> list[str]:
    if not isinstance(cols, list):
        return []
    out: list[str] = []
    seen: set[str] = set()
    for raw in cols:
        col = str(raw or "").strip()
        if not col or col in seen:
            continue
        seen.add(col)
        out.append(col)
    return out


def normalize_model_payload(payload: dict[str, Any]) -> dict[str, Any]:
    model_data = dict(payload or {})
    model_data["schema_version"] = int(model_data.get("schema_version") or 1)
    model_data["model_format_version"] = int(model_data.get("model_format_version") or 1)
    model_data["feature_cols"] = normalize_feature_columns(model_data.get("feature_cols") or [])
    if not model_data.get("model_bytes_b64"):
        legacy = model_data.get("model_b64")
        if legacy:
            model_data["model_bytes_b64"] = legacy
    return model_data


def migrate_feature_payload(
    features: dict[str, Any] | None,
    target_feature_cols: list[str],
    *,
    strict: bool = False,
    critical_features: set[str] | frozenset[str] | None = None,
) -> dict[str, float]:
    """Normalize a point-in-time feature payload to a model's declared order.

    ``strict=False`` preserves legacy model compatibility. Production inference
    enables strict mode with ``ML_STRICT_FEATURE_SCHEMA=1`` and rejects missing
    critical features instead of silently interpreting absence as market zero.
    """
    src = features or {}
    required = set(critical_features or ())
    missing: list[str] = []
    invalid: list[str] = []
    out: dict[str, float] = {}
    for col in target_feature_cols:
        if col not in src or src.get(col) is None:
            if strict and (not required or col in required):
                missing.append(col)
            out[col] = 0.0
            continue
        try:
            value = float(src[col])
            if not math.isfinite(value):
                raise ValueError("non_finite")
            out[col] = value
        except Exception:
            if strict and (not required or col in required):
                invalid.append(col)
            out[col] = 0.0
    if missing or invalid:
        parts = []
        if missing:
            parts.append("missing=" + ",".join(sorted(missing)))
        if invalid:
            parts.append("invalid=" + ",".join(sorted(invalid)))
        raise ValueError("feature_schema_mismatch:" + ";".join(parts))
    return out


def strict_feature_schema_enabled() -> bool:
    raw = str(os.getenv("ML_STRICT_FEATURE_SCHEMA", "1") or "1").strip().lower()
    return raw in {"1", "true", "yes", "on"}
