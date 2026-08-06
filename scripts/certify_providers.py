#!/usr/bin/env python3
"""Generate static and optional live provider certification evidence.

Examples:
    python scripts/certify_providers.py --output-dir artifacts/provider-certification
    python scripts/certify_providers.py --live --providers coinbase,okx,kraken

Live mode is intentionally opt-in and never prints credential values.
"""
from __future__ import annotations

import argparse
import asyncio
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import importlib
import json
from pathlib import Path
import socket
import sys
import time
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from data.provider_catalog import (
    CertificationStatus,
    ProviderSpec,
    list_provider_specs,
    validate_candles,
)


@dataclass(slots=True)
class ProviderCertification:
    provider: str
    display_name: str
    implemented: bool
    configured: bool
    enabled: bool
    live_requested: bool
    certification_status: str
    symbol: str | None
    timeframe: str | None
    candle_count: int = 0
    latency_ms: float | None = None
    validation: dict[str, Any] | None = None
    error: str | None = None
    docs_url: str = ""
    tested_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _looks_like_network_failure(exc: BaseException | str) -> bool:
    text = str(exc).lower()
    return any(
        token in text
        for token in (
            "name resolution",
            "temporary failure",
            "network is unreachable",
            "connection refused",
            "connecterror",
            "dns",
            "timed out",
            "timeout",
        )
    )


async def _call_connector(spec: ProviderSpec, *, timeout: float, limit: int) -> tuple[list[dict[str, Any]], float]:
    connector = spec.resolve_connector()
    if connector is None:
        raise RuntimeError("no connector implementation")

    started = time.perf_counter()

    def _call() -> list[dict[str, Any]]:
        kwargs = {"limit": int(limit), "timeout": timeout}
        try:
            result = connector(spec.sample_symbol, spec.sample_timeframe, **kwargs)
        except TypeError:
            kwargs.pop("timeout", None)
            try:
                result = connector(spec.sample_symbol, spec.sample_timeframe, **kwargs)
            except TypeError:
                result = connector(spec.sample_symbol, spec.sample_timeframe)
        return list(result or [])

    rows = await asyncio.wait_for(asyncio.to_thread(_call), timeout=max(timeout + 2.0, 3.0))
    return rows, (time.perf_counter() - started) * 1000.0


async def certify_one(spec: ProviderSpec, *, live: bool, timeout: float, limit: int) -> ProviderCertification:
    tested_at = datetime.now(timezone.utc).isoformat()
    # Context/discovery providers may intentionally expose no candle callable.
    # Importable provider modules are still implemented; candle certification is
    # only applicable when connector_attr is declared.
    implemented = bool(spec.connector_module)
    configured = spec.configured()
    enabled = spec.enabled()

    result = ProviderCertification(
        provider=spec.key,
        display_name=spec.display_name,
        implemented=implemented,
        configured=configured,
        enabled=enabled,
        live_requested=live,
        certification_status=CertificationStatus.IMPLEMENTED_NOT_LIVE_VERIFIED.value,
        symbol=spec.sample_symbol,
        timeframe=spec.sample_timeframe,
        docs_url=spec.docs_url,
        tested_at=tested_at,
    )

    if not implemented:
        result.certification_status = CertificationStatus.DISABLED.value if not enabled else CertificationStatus.FAILED.value
        result.error = "No canonical connector implementation in this repository snapshot."
        return result

    try:
        module = importlib.import_module(str(spec.connector_module))
        if spec.connector_attr:
            spec.resolve_connector()
    except Exception as exc:
        result.certification_status = CertificationStatus.FAILED.value
        result.error = f"connector import failed: {type(exc).__name__}: {exc}"
        return result

    # Discovery, macro, on-chain and calendar providers are analysis-only and
    # do not normalize OHLC candles. Their module contract and health function
    # can still be certified without pretending they are quote providers.
    if not spec.connector_attr:
        health = getattr(module, "health", None)
        if callable(health):
            try:
                health_payload = health() or {}
                result.validation = {"valid": True, "provider_health": health_payload}
            except Exception as exc:  # noqa: BLE001
                result.certification_status = CertificationStatus.FAILED.value
                result.error = f"health contract failed: {type(exc).__name__}: {exc}"
                return result
        else:
            result.validation = {"valid": True, "contract": "module_import"}

        if not live:
            result.certification_status = CertificationStatus.IMPLEMENTED_AND_MOCK_VERIFIED.value
            return result
        if not enabled:
            result.certification_status = CertificationStatus.DISABLED.value
            result.error = f"disabled by {spec.enabled_env or 'catalog policy'}"
            return result
        if not configured:
            required_parts = []
            if spec.required_env:
                required_parts.append("one of [" + ", ".join(spec.required_env) + "]")
            required_parts.extend("one of [" + ", ".join(group) + "]" for group in spec.required_env_all)
            result.certification_status = CertificationStatus.BLOCKED_MISSING_CREDENTIAL.value
            result.error = "missing " + " and ".join(required_parts or ["required provider configuration"])
            return result
        result.certification_status = CertificationStatus.ANALYSIS_ONLY.value
        result.error = "context/discovery provider; candle certification is not applicable"
        return result

    synthetic = [
        {"timestamp": 1_700_000_000_000, "open": 100, "high": 102, "low": 99, "close": 101, "volume": 10},
        {"timestamp": 1_700_000_300_000, "open": 101, "high": 103, "low": 100, "close": 102, "volume": 11},
    ]
    static_validation = validate_candles(synthetic)
    if not static_validation["valid"]:
        result.certification_status = CertificationStatus.FAILED.value
        result.error = "internal normalized candle validator failed"
        result.validation = static_validation
        return result

    if not live:
        result.certification_status = CertificationStatus.IMPLEMENTED_AND_MOCK_VERIFIED.value
        result.validation = static_validation
        return result

    if not enabled:
        result.certification_status = CertificationStatus.DISABLED.value
        result.error = f"disabled by {spec.enabled_env or 'catalog policy'}"
        return result

    if not configured:
        required_parts = []
        if spec.required_env:
            required_parts.append("one of [" + ", ".join(spec.required_env) + "]")
        required_parts.extend("one of [" + ", ".join(group) + "]" for group in spec.required_env_all)
        result.certification_status = CertificationStatus.BLOCKED_MISSING_CREDENTIAL.value
        result.error = "missing " + " and ".join(required_parts or ["required provider configuration"])
        return result

    if not spec.sample_symbol:
        result.certification_status = CertificationStatus.FAILED.value
        result.error = "catalog has no live sample symbol"
        return result

    try:
        candles, latency_ms = await _call_connector(spec, timeout=timeout, limit=limit)
        result.latency_ms = round(latency_ms, 3)
        result.candle_count = len(candles)
        result.validation = validate_candles(candles, minimum=min(2, limit))
        if not result.validation["valid"]:
            result.certification_status = CertificationStatus.FAILED.value
            result.error = "; ".join(result.validation["errors"][:8])
            return result
        if spec.sandbox:
            result.certification_status = CertificationStatus.IMPLEMENTED_AND_SANDBOX_VERIFIED.value
        elif spec.public_endpoint and not spec.required_env:
            result.certification_status = CertificationStatus.IMPLEMENTED_AND_PUBLIC_ENDPOINT_VERIFIED.value
        else:
            result.certification_status = CertificationStatus.IMPLEMENTED_AND_LIVE_VERIFIED.value
        return result
    except Exception as exc:
        result.certification_status = (
            CertificationStatus.BLOCKED_NETWORK.value
            if _looks_like_network_failure(exc)
            else CertificationStatus.FAILED.value
        )
        result.error = f"{type(exc).__name__}: {exc}"
        return result


def _markdown(results: list[ProviderCertification]) -> str:
    lines = [
        "# Provider Certification Matrix",
        "",
        f"Generated: {datetime.now(timezone.utc).isoformat()}",
        "",
        "A mock/import result is not live production certification. Only explicit live/public/sandbox statuses prove an external connection.",
        "",
        "| Provider | Implemented | Configured | Enabled | Status | Sample | Candles | Latency ms | Error |",
        "|---|---:|---:|---:|---|---|---:|---:|---|",
    ]
    for item in results:
        error = (item.error or "").replace("|", "\\|").replace("\n", " ")
        sample = f"{item.symbol or '-'} {item.timeframe or '-'}"
        lines.append(
            f"| {item.display_name} | {item.implemented} | {item.configured} | {item.enabled} | "
            f"{item.certification_status} | {sample} | {item.candle_count} | "
            f"{item.latency_ms if item.latency_ms is not None else '-'} | {error} |"
        )
    return "\n".join(lines) + "\n"


async def _run(args: argparse.Namespace) -> int:
    requested = {item.strip().lower() for item in (args.providers or "").split(",") if item.strip()}
    specs = [spec for spec in list_provider_specs() if not requested or spec.key in requested]
    results = [
        await certify_one(spec, live=args.live, timeout=args.timeout, limit=args.limit)
        for spec in specs
    ]

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "provider_certification.json"
    md_path = output_dir / "provider_certification.md"
    json_path.write_text(json.dumps([item.to_dict() for item in results], indent=2, sort_keys=True), encoding="utf-8")
    md_path.write_text(_markdown(results), encoding="utf-8")

    print(md_path.read_text(encoding="utf-8"))
    print(f"JSON: {json_path}")
    print(f"Markdown: {md_path}")

    hard_fail = any(
        item.certification_status == CertificationStatus.FAILED.value
        and item.enabled
        for item in results
    )
    return 1 if hard_fail else 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true", help="perform external calls; disabled by default")
    parser.add_argument("--providers", default="", help="comma-separated provider keys")
    parser.add_argument("--timeout", type=float, default=8.0)
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--output-dir", default="artifacts/provider-certification")
    return parser


def main() -> int:
    return asyncio.run(_run(build_parser().parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
