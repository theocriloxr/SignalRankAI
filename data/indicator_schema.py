from __future__ import annotations

from typing import Any, MutableMapping


CANONICAL_INDICATOR_ALIASES: dict[str, tuple[str, ...]] = {
    "ema_fast": ("ema_20", "ema_12"),
    "ema_slow": ("ema_50", "ema_26"),
    "ema_trend": ("ema_200", "trend_ema"),
    "sma_fast": ("sma_20",),
    "sma_slow": ("sma_50",),
    "sma_trend": ("sma_200",),
    "atr": ("atr_14",),
    "rsi": ("rsi_14",),
    "macd_signal": ("macd_signal_line",),
}


def normalize_indicator_schema(indicators: MutableMapping[str, Any] | None) -> MutableMapping[str, Any]:
    """Fill canonical indicator names expected by strategies without deleting source keys."""
    if not isinstance(indicators, MutableMapping):
        return indicators if indicators is not None else {}

    for canonical, aliases in CANONICAL_INDICATOR_ALIASES.items():
        if indicators.get(canonical) not in (None, ""):
            continue
        for alias in aliases:
            if indicators.get(alias) not in (None, ""):
                indicators[canonical] = indicators.get(alias)
                break

    macd_payload = indicators.get("macd")
    if isinstance(macd_payload, dict):
        if indicators.get("macd_line") in (None, "") and macd_payload.get("macd") not in (None, ""):
            indicators["macd_line"] = macd_payload.get("macd")
        if indicators.get("macd_signal") in (None, "") and macd_payload.get("signal") not in (None, ""):
            indicators["macd_signal"] = macd_payload.get("signal")
        if indicators.get("macd_hist") in (None, "") and macd_payload.get("hist") not in (None, ""):
            indicators["macd_hist"] = macd_payload.get("hist")

    return indicators


def missing_indicators(indicators: MutableMapping[str, Any] | None, required: tuple[str, ...]) -> list[str]:
    normalized = normalize_indicator_schema(indicators)
    if not isinstance(normalized, MutableMapping):
        return list(required)
    return [key for key in required if normalized.get(key) in (None, "")]
