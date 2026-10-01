#!/usr/bin/env python3
"""Live certification of the actual SignalRankAI market-data path by asset class.

This script is intentionally networked and fail-closed. It exercises the same
canonical provider waterfall used by the engine, records the provider actually
selected, validates normalized OHLCV, and requires fresh candles. It never
falls back to synthetic data or yfinance in staging/production.
"""
from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
import time
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from data.fetcher import async_get_candles, _get_last_provider_used
from data.provider_catalog import validate_candles

CLASS_SAMPLES: dict[str, tuple[str, str]] = {
    "crypto_spot": ("BTCUSDT", "5m"),
    "forex": ("EURUSD", "5m"),
    "equity": ("AAPL", "5m"),
    "index": ("NAS100", "5m"),
    "commodity_spot": ("XAUUSD", "5m"),
}
TF_SECONDS = {"1m": 60, "5m": 300, "15m": 900, "1h": 3600, "4h": 14400, "1d": 86400}


def _environment() -> str:
    return str(
        os.getenv("SIGNALRANK_ENVIRONMENT_OVERRIDE")
        or os.getenv("RAILWAY_ENVIRONMENT_NAME")
        or os.getenv("RAILWAY_ENVIRONMENT")
        or os.getenv("APP_ENV")
        or os.getenv("ENVIRONMENT")
        or ""
    ).strip().lower()


def _latest_age(validation: dict[str, Any]) -> float | None:
    raw = validation.get("last_timestamp")
    if raw is None:
        return None
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None
    while value > 10_000_000_000:
        value /= 1000.0
    return max(0.0, time.time() - value)


async def _certify(asset_class: str, symbol: str, timeframe: str, timeout: float) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        rows = await asyncio.wait_for(
            async_get_candles(symbol, timeframe),
            timeout=timeout,
        )
    except asyncio.TimeoutError:
        return {
            "asset_class": asset_class,
            "symbol": symbol,
            "timeframe": timeframe,
            "status": "FAILED",
            "reason": "provider_waterfall_timeout",
            "execution_eligible": False,
        }
    except Exception as exc:
        return {
            "asset_class": asset_class,
            "symbol": symbol,
            "timeframe": timeframe,
            "status": "FAILED",
            "reason": f"provider_waterfall_error:{type(exc).__name__}",
            "execution_eligible": False,
        }

    provider = str(_get_last_provider_used(symbol, timeframe) or "unknown")
    validation = validate_candles(rows or [], minimum=20)
    age = _latest_age(validation)
    freshness_limit = max(180.0, float(TF_SECONDS.get(timeframe, 3600)) * 2.5)
    source_lower = provider.lower()
    analysis_only = any(token in source_lower for token in ("yahoo", "yfinance"))
    fresh = age is not None and age <= freshness_limit
    valid = bool(validation.get("valid"))
    eligible = bool(valid and fresh and not analysis_only and provider != "unknown")

    reasons: list[str] = []
    if not valid:
        reasons.extend(str(v) for v in validation.get("errors") or [])
    if age is None:
        reasons.append("missing_freshness_timestamp")
    elif not fresh:
        reasons.append(f"stale:{age:.0f}s>{freshness_limit:.0f}s")
    if analysis_only:
        reasons.append("analysis_only_provider")
    if provider == "unknown":
        reasons.append("provider_identity_unknown")

    return {
        "asset_class": asset_class,
        "symbol": symbol,
        "timeframe": timeframe,
        "provider": provider,
        "status": "PASS" if eligible else "FAILED",
        "execution_eligible": eligible,
        "candle_count": len(rows or []),
        "age_seconds": round(age, 3) if age is not None else None,
        "freshness_limit_seconds": freshness_limit,
        "latency_ms": round((time.perf_counter() - started) * 1000.0, 3),
        "validation": validation,
        "reasons": reasons,
    }


async def _run(args: argparse.Namespace) -> int:
    env = _environment()
    if env not in {"staging", "production", "prod"} and not args.allow_non_release_environment:
        raise RuntimeError(f"market_class_certification_requires_staging_or_production got={env or 'unknown'}")

    required = [
        item.strip().lower()
        for item in str(args.asset_classes or "").split(",")
        if item.strip()
    ]
    unknown = [item for item in required if item not in CLASS_SAMPLES]
    if unknown:
        raise RuntimeError("unknown_asset_classes:" + ",".join(sorted(unknown)))

    results = []
    for asset_class in required:
        symbol, timeframe = CLASS_SAMPLES[asset_class]
        results.append(await _certify(asset_class, symbol, timeframe, args.timeout))

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "environment": env,
        "required_asset_classes": required,
        "results": results,
        "all_required_classes_execution_eligible": all(
            bool(row.get("execution_eligible")) for row in results
        ),
        "synthetic_data_used": False,
        "yfinance_execution_truth_allowed": False,
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    print("MARKET_CLASS_CERTIFICATION " + json.dumps(report, sort_keys=True))
    return 0 if report["all_required_classes_execution_eligible"] else 4


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--asset-classes",
        default="crypto_spot,forex,equity,index,commodity_spot",
    )
    parser.add_argument("--timeout", type=float, default=20.0)
    parser.add_argument(
        "--output",
        default="artifacts/provider-certification/market_class_certification.json",
    )
    parser.add_argument("--allow-non-release-environment", action="store_true")
    return asyncio.run(_run(parser.parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
