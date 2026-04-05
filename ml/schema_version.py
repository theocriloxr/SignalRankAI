from __future__ import annotations

from typing import Any


CURRENT_SCHEMA_VERSION = 1
MODEL_FORMAT_VERSION = 1

FEATURE_COLUMNS_V1 = [
    "rr_estimate",
    "score",
    "strength",
    "regime_score",
    "trend_ema",
    "rsi",
    "volume_ratio",
    "macd_trend",
    "adx_value",
    "news_sentiment",
    "nearest_support_dist",
    "nearest_resistance_dist",
]


def get_current_schema_version() -> int:
    return CURRENT_SCHEMA_VERSION


def get_feature_columns() -> list[str]:
    return list(FEATURE_COLUMNS_V1)


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
    model_data["schema_version"] = int(model_data.get("schema_version") or CURRENT_SCHEMA_VERSION)
    model_data["model_format_version"] = int(model_data.get("model_format_version") or MODEL_FORMAT_VERSION)
    model_data["feature_cols"] = normalize_feature_columns(model_data.get("feature_cols") or [])
    if not model_data.get("model_bytes_b64"):
        legacy = model_data.get("model_b64")
        if legacy:
            model_data["model_bytes_b64"] = legacy
    return model_data


def migrate_feature_payload(
    features: dict[str, Any] | None,
    target_feature_cols: list[str],
) -> dict[str, float]:
    src = features or {}
    out: dict[str, float] = {}
    for col in target_feature_cols:
        try:
            out[col] = float(src.get(col, 0.0))
        except Exception:
            out[col] = 0.0
    return out
