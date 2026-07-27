"""Read-only performance rollup facade.

The facade accepts rows from any storage adapter and keeps provenance visible;
it does not mix shadow/backtest/paper/manual/live categories.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Iterable, Mapping

from ml.evidence import compute_metrics


def summarize_rows(rows: Iterable[Mapping[str, Any]], *, provenance: str = "live") -> dict[str, Any]:
    normalized = [dict(row) for row in rows if str(row.get("provenance", provenance)).lower() == str(provenance).lower()]
    metrics = compute_metrics(normalized)
    return {
        "provenance": str(provenance).lower(),
        "methodology": "individual TP events with explicit cost/slippage fields",
        "sample_size": metrics.sample_size,
        "sufficient_sample": metrics.sample_size >= 100,
        "win_rate": metrics.win_rate,
        "confidence_interval": [metrics.confidence_low, metrics.confidence_high],
        "expectancy_r": metrics.expectancy_r,
        "profit_factor": metrics.profit_factor,
        "max_drawdown_r": metrics.max_drawdown_r,
        "tp1_rate": metrics.tp1_rate,
        "tp2_rate": metrics.tp2_rate,
        "tp3_rate": metrics.tp3_rate,
        "sl_rate": metrics.sl_rate,
        "missed_entry_rate": metrics.missed_entry_rate,
        "expired_rate": metrics.expired_rate,
        "cost_r": metrics.total_cost_r,
    }


def segment_summaries(rows: Iterable[Mapping[str, Any]], *, provenance: str = "live", fields: tuple[str, ...] = ("asset", "strategy", "timeframe", "provider")) -> dict[str, dict[str, Any]]:
    grouped: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in rows:
        if str(row.get("provenance", provenance)).lower() != str(provenance).lower():
            continue
        key = "|".join(str(row.get(field) or "unknown") for field in fields)
        grouped[key].append(row)
    return {key: summarize_rows(values, provenance=provenance) for key, values in grouped.items()}


__all__ = ["segment_summaries", "summarize_rows"]
