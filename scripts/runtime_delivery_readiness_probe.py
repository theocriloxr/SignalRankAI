#!/usr/bin/env python3
"""Read-only final-delivery readiness probe across SignalRank asset classes.

The probe separates two questions that must not be conflated:
1. Can SignalRank obtain a source-timestamped live quote for each market now?
2. Would a recent stored signal pass the exact final-send freshness/risk boundary?

It never reserves deliveries, writes signal state, or sends Telegram messages.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select

from data.get_live_price import get_live_price_result
from data.provider_types import LivePriceFailure, LivePriceQuote
from db.models import Signal
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


async def _quote_probe(symbol: str, timeout_seconds: float) -> dict[str, Any]:
    try:
        result = await asyncio.wait_for(
            get_live_price_result(
                symbol,
                timeout=min(8.0, timeout_seconds),
                require_delivery_freshness=True,
            ),
            timeout=timeout_seconds,
        )
        if isinstance(result, LivePriceQuote):
            return {
                "ok": True,
                "provider": str(result.provider or ""),
                "provider_symbol": str(result.provider_symbol or ""),
                "quote_kind": str(result.quote_kind or ""),
                "source_age_seconds": result.source_age_seconds(),
                "market_status": str(result.market_status or ""),
                "confidence": float(result.confidence),
                "untrusted_reason": str(result.untrusted_reason or ""),
            }
        if isinstance(result, LivePriceFailure):
            return {
                "ok": False,
                "provider": str(result.provider or ""),
                "reason": str(result.reason or "quote_failure"),
                "asset_class": str(result.asset_class or ""),
                "breaker_state": str(result.breaker_state or ""),
            }
        return {"ok": False, "reason": "unexpected_quote_result"}
    except asyncio.TimeoutError:
        return {"ok": False, "reason": "quote_probe_timeout"}
    except Exception as exc:
        return {"ok": False, "reason": f"quote_probe_error:{type(exc).__name__}"}


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
    lookback_days = max(1, min(int(os.getenv("DELIVERY_READINESS_LOOKBACK_DAYS", "7") or 7), 30))
    start = datetime.utcnow() - timedelta(days=lookback_days)

    async with get_session(
        priority="background",
        label="runtime_delivery_readiness_probe",
        timeout_seconds=30.0,
    ) as session:
        result = await session.execute(
            select(Signal)
            .where(Signal.created_at >= start)
            .order_by(Signal.created_at.desc())
            .limit(1000)
        )
        rows = list(result.scalars().all())

    buckets: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        payload = _payload(row)
        cls = _asset_class(payload)
        if cls in ASSET_CLASSES and len(buckets[cls]) < per_class:
            buckets[cls].append(payload)

    report: dict[str, Any] = {
        "read_only": True,
        "samples_per_class": per_class,
        "lookback_days": lookback_days,
        "rows_found": len(rows),
        "asset_classes": {},
    }
    for cls in ASSET_CLASSES:
        samples = []
        reasons: Counter[str] = Counter()
        quote_reasons: Counter[str] = Counter()
        passes = 0
        quote_passes = 0
        seen_quote_assets: set[str] = set()
        for payload in buckets.get(cls, []):
            symbol = str(payload.get("asset") or payload.get("symbol") or "").strip()
            quote_result = (
                await _quote_probe(symbol, timeout_seconds)
                if symbol and symbol not in seen_quote_assets
                else {"ok": False, "reason": "duplicate_asset_skipped"}
            )
            if symbol:
                seen_quote_assets.add(symbol)
            quote_passes += int(bool(quote_result.get("ok")))
            quote_reasons[str(quote_result.get("reason") or "quote_ok")] += 1

            result = await _evaluate(payload, timeout_seconds)
            result["asset"] = symbol[:32]
            result["timeframe"] = str(payload.get("timeframe") or "")[:16]
            result["status"] = str(payload.get("status") or "")[:16]
            created_at = payload.get("created_at")
            result["created_at"] = created_at.isoformat() if hasattr(created_at, "isoformat") else str(created_at or "")
            result["expired"] = bool(payload.get("expired"))
            result["archived"] = bool(payload.get("archived"))
            result["quote_probe"] = quote_result
            samples.append(result)
            reasons[result["reason"]] += 1
            passes += int(bool(result.get("ok")))

        report["asset_classes"][cls] = {
            "sampled": len(samples),
            "quote_passed": quote_passes,
            "quote_blocked": len(samples) - quote_passes,
            "quote_reasons": dict(quote_reasons),
            "delivery_passed": passes,
            "delivery_blocked": len(samples) - passes,
            "delivery_reasons": dict(reasons),
            "samples": samples,
        }

    print("[delivery_readiness_probe] " + json.dumps(report, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main_async()))
