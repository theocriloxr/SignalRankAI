#!/usr/bin/env python3
"""Read-only final-delivery readiness probe across SignalRank asset classes.

This diagnostic never reserves deliveries, writes signal state, or sends Telegram
messages. It evaluates a small sample with the same final-send quote/freshness/
risk boundary used immediately before Telegram transmission.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path
from collections import Counter, defaultdict
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from db.pg_features import list_active_signals
from db.session import get_session
from engine.delivery_freshness import validate_delivery_freshness
from services.asset_mapper import classify_asset


ASSET_CLASSES = ("crypto", "fx", "commodity", "index", "stock")


def _payload(row: Any) -> dict[str, Any]:
    if hasattr(row, "__table__"):
        return {column.key: getattr(row, column.key, None) for column in row.__table__.columns}
    return {k: v for k, v in dict(getattr(row, "__dict__", {}) or {}).items() if not k.startswith("_")}


def _asset_class(payload: dict[str, Any]) -> str:
    raw = str(payload.get("asset_class") or "").strip().lower()
    aliases = {"forex": "fx", "equity": "stock", "equities": "stock", "indices": "index"}
    raw = aliases.get(raw, raw)
    if raw in ASSET_CLASSES:
        return raw
    symbol = str(payload.get("asset") or payload.get("symbol") or "").strip()
    classified = str(classify_asset(symbol) or "").strip().lower()
    classified = aliases.get(classified, classified)
    return classified if classified in ASSET_CLASSES else "unknown"


async def _evaluate(payload: dict[str, Any], timeout_seconds: float) -> dict[str, Any]:
    try:
        result = await asyncio.wait_for(
            validate_delivery_freshness(
                payload,
                final_send=True,
                delivery_tier="owner",
            ),
            timeout=timeout_seconds,
        )
        return {
            "ok": bool(result.ok),
            "reason": str(result.reason or "unknown"),
            "state": str(result.state or ""),
            "provider": str(result.quote_provider or ""),
            "quote_kind": str(result.quote_kind or ""),
            "source_age_seconds": result.quote_source_age_seconds,
            "entry_drift_pct": result.entry_drift_pct,
            "queue_age_seconds": result.queue_age_seconds,
            "rules": list(result.rule_results or ()),
        }
    except asyncio.TimeoutError:
        return {"ok": False, "reason": "probe_timeout", "state": "PROBE_TIMEOUT"}
    except Exception as exc:
        return {
            "ok": False,
            "reason": f"probe_error:{type(exc).__name__}",
            "state": "PROBE_ERROR",
        }


async def main_async() -> int:
    per_class = max(1, min(int(os.getenv("DELIVERY_READINESS_SAMPLES_PER_CLASS", "2") or 2), 5))
    timeout_seconds = max(3.0, min(float(os.getenv("DELIVERY_READINESS_PROBE_TIMEOUT_SECONDS", "12") or 12), 30.0))
    async with get_session(
        priority="background",
        label="runtime_delivery_readiness_probe",
        timeout_seconds=30.0,
    ) as session:
        rows = await list_active_signals(session, max_age_days=2, limit=300)

    buckets: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        payload = _payload(row)
        cls = _asset_class(payload)
        if cls in ASSET_CLASSES and len(buckets[cls]) < per_class:
            buckets[cls].append(payload)

    report: dict[str, Any] = {"read_only": True, "samples_per_class": per_class, "asset_classes": {}}
    for cls in ASSET_CLASSES:
        samples = []
        reasons: Counter[str] = Counter()
        passes = 0
        for payload in buckets.get(cls, []):
            result = await _evaluate(payload, timeout_seconds)
            result["asset"] = str(payload.get("asset") or payload.get("symbol") or "")[:32]
            result["timeframe"] = str(payload.get("timeframe") or "")[:16]
            samples.append(result)
            reasons[result["reason"]] += 1
            passes += int(bool(result.get("ok")))
        report["asset_classes"][cls] = {
            "sampled": len(samples),
            "passed": passes,
            "blocked": len(samples) - passes,
            "reasons": dict(reasons),
            "samples": samples,
        }

    print("[delivery_readiness_probe] " + json.dumps(report, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main_async()))
