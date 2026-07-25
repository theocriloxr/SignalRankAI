"""Validate SignalRankAI environment profiles before deployment.

This validator never prints secret values. It detects duplicate keys, unsafe
fail-open flags, contradictory outcome ownership, and Railway pool/OHLC settings
that caused the observed staging failures.
"""
from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path

TRUE = {"1", "true", "yes", "on", "y"}


def parse_env(path: Path) -> tuple[dict[str, str], list[str]]:
    values: dict[str, str] = {}
    keys: list[str] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if not key:
            continue
        keys.append(key)
        values[key] = value.strip()
    return values, keys


def is_true(values: dict[str, str], key: str, default: bool = False) -> bool:
    if key not in values:
        return default
    return values[key].strip().lower() in TRUE


def as_int(values: dict[str, str], key: str, default: int) -> int:
    try:
        return int(values.get(key, str(default)))
    except ValueError:
        return default


def validate(path: Path) -> list[str]:
    values, keys = parse_env(path)
    errors: list[str] = []
    duplicates = sorted(key for key, count in Counter(keys).items() if count > 1)
    if duplicates:
        errors.append("duplicate keys: " + ", ".join(duplicates))

    for key in ("AUTO_TRADE_ENABLED", "COPY_TRADE_ENABLED", "REAL_PAYOUTS_ENABLED"):
        if is_true(values, key):
            errors.append(f"unsafe release flag enabled: {key}")

    for key in (
        "DELIVERY_FRESHNESS_TIMEOUT_FAIL_OPEN",
        "DELIVERY_FRESHNESS_ERROR_FAIL_OPEN",
        "DELIVERY_MISSING_PRICE_FAIL_OPEN",
    ):
        if is_true(values, key):
            errors.append(f"delivery safety must fail closed: {key}")

    public_testing = is_true(values, "PUBLIC_TESTING_MODE")
    pool_size = as_int(values, "DB_POOL_SIZE_RAILWAY", as_int(values, "DB_POOL_SIZE", 2))
    overflow = as_int(values, "DB_MAX_OVERFLOW_RAILWAY", as_int(values, "DB_MAX_OVERFLOW", 0))
    if public_testing and (pool_size > 2 or overflow > 0):
        errors.append(f"unsafe public-testing DB pool: pool_size={pool_size} max_overflow={overflow}")

    asset_concurrency = as_int(values, "MARKET_FETCH_ASSET_CONCURRENCY", 2)
    if public_testing and asset_concurrency > 4:
        errors.append(f"unsafe public-testing OHLC asset concurrency: {asset_concurrency}")

    if is_true(values, "WORKER_OUTCOME_TRACKER_ENABLED", True) and is_true(
        values, "ENGINE_OUTCOME_TRACKER_ENABLED", False
    ):
        errors.append("duplicate realtime outcome owners enabled")

    if values.get("OUTCOME_TRACK_DELIVERED_ONLY", "1").strip().lower() not in TRUE:
        errors.append("OUTCOME_TRACK_DELIVERED_ONLY must be enabled")

    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("paths", nargs="+", type=Path)
    args = parser.parse_args()
    failed = False
    for path in args.paths:
        errors = validate(path)
        if errors:
            failed = True
            print(f"{path}: BLOCKED")
            for error in errors:
                print(f"  - {error}")
        else:
            print(f"{path}: VALID")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
