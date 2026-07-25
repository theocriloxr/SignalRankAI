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


def as_float(values: dict[str, str], key: str, default: float) -> float:
    try:
        return float(values.get(key, str(default)))
    except ValueError:
        return default


def validate(path: Path) -> list[str]:
    values, keys = parse_env(path)
    errors: list[str] = []
    duplicates = sorted(key for key, count in Counter(keys).items() if count > 1)
    if duplicates:
        errors.append("duplicate keys: " + ", ".join(duplicates))

    for key in (
        "AUTO_TRADE_ENABLED",
        "COPY_TRADE_ENABLED",
        "REAL_EXECUTION_ENABLED",
        "MT5_ALLOW_LIVE_ACCOUNTS",
        "REAL_PAYOUTS_ENABLED",
    ):
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

    if "UVICORN_WORKERS" in values and as_int(values, "UVICORN_WORKERS", 0) != 1:
        errors.append("Railway Hobby profile must use UVICORN_WORKERS=1")

    if "REDIS_MAX_CONNECTIONS" in values:
        redis_connections = as_int(values, "REDIS_MAX_CONNECTIONS", 0)
        if redis_connections < 1 or redis_connections > 64:
            errors.append("REDIS_MAX_CONNECTIONS must be between 1 and 64")

    if is_true(values, "REQUIRE_DISTINCT_DELIVERY_REDIS"):
        state_url = values.get("STATE_REDIS_URL") or values.get("REDIS_URL") or ""
        delivery_url = values.get("DELIVERY_REDIS_URL") or ""
        if not state_url or not delivery_url:
            errors.append("STATE_REDIS_URL and DELIVERY_REDIS_URL are required")
        elif state_url == delivery_url:
            errors.append("DELIVERY_REDIS_URL must reference a distinct Redis service")

    if is_true(values, "RESOURCE_GUARD_ENABLED"):
        if as_int(values, "APP_MEMORY_LIMIT_MB", 0) < 0:
            errors.append("APP_MEMORY_LIMIT_MB must be zero (auto) or positive")
        if as_int(values, "APP_MEMORY_RECOVERY_MARGIN_MB", 32) < 0:
            errors.append("APP_MEMORY_RECOVERY_MARGIN_MB must be non-negative")
        if as_int(values, "RESOURCE_RECOVERY_SAMPLES", 3) < 1:
            errors.append("RESOURCE_RECOVERY_SAMPLES must be at least 1")

        ordered_groups = (
            (
                "memory ratios",
                as_float(values, "APP_MEMORY_SOFT_RATIO", 0.72),
                as_float(values, "APP_MEMORY_HARD_RATIO", 0.88),
                as_float(values, "APP_MEMORY_CRITICAL_RATIO", 0.96),
                1.0,
            ),
            (
                "CPU thresholds",
                as_float(values, "RESOURCE_CPU_SOFT_PERCENT", 75.0),
                as_float(values, "RESOURCE_CPU_HARD_PERCENT", 90.0),
                as_float(values, "RESOURCE_CPU_CRITICAL_PERCENT", 98.0),
                100.0,
            ),
            (
                "event-loop thresholds",
                as_float(values, "RESOURCE_EVENT_LOOP_SOFT_MS", 100.0),
                as_float(values, "RESOURCE_EVENT_LOOP_HARD_MS", 500.0),
                as_float(values, "RESOURCE_EVENT_LOOP_CRITICAL_MS", 2000.0),
                None,
            ),
            (
                "DB queue thresholds",
                as_float(values, "RESOURCE_DB_QUEUE_SOFT", 2.0),
                as_float(values, "RESOURCE_DB_QUEUE_HARD", 6.0),
                as_float(values, "RESOURCE_DB_QUEUE_CRITICAL", 12.0),
                None,
            ),
            (
                "DB wait thresholds",
                as_float(values, "RESOURCE_DB_WAIT_SOFT_MS", 250.0),
                as_float(values, "RESOURCE_DB_WAIT_HARD_MS", 1000.0),
                as_float(values, "RESOURCE_DB_WAIT_CRITICAL_MS", 5000.0),
                None,
            ),
            (
                "Redis latency thresholds",
                as_float(values, "RESOURCE_REDIS_SOFT_MS", 50.0),
                as_float(values, "RESOURCE_REDIS_HARD_MS", 200.0),
                as_float(values, "RESOURCE_REDIS_CRITICAL_MS", 1000.0),
                None,
            ),
            (
                "delivery queue ratios",
                as_float(values, "RESOURCE_DELIVERY_QUEUE_SOFT_RATIO", 0.60),
                as_float(values, "RESOURCE_DELIVERY_QUEUE_HARD_RATIO", 0.80),
                as_float(values, "RESOURCE_DELIVERY_QUEUE_CRITICAL_RATIO", 0.95),
                1.0,
            ),
            (
                "provider error ratios",
                as_float(values, "RESOURCE_PROVIDER_ERROR_SOFT_RATIO", 0.10),
                as_float(values, "RESOURCE_PROVIDER_ERROR_HARD_RATIO", 0.30),
                as_float(values, "RESOURCE_PROVIDER_ERROR_CRITICAL_RATIO", 0.60),
                1.0,
            ),
            (
                "RetryAfter ratios",
                as_float(values, "RESOURCE_RETRY_AFTER_SOFT_RATIO", 0.02),
                as_float(values, "RESOURCE_RETRY_AFTER_HARD_RATIO", 0.10),
                as_float(values, "RESOURCE_RETRY_AFTER_CRITICAL_RATIO", 0.25),
                1.0,
            ),
            (
                "pending task thresholds",
                as_float(values, "RESOURCE_PENDING_TASKS_SOFT", 100.0),
                as_float(values, "RESOURCE_PENDING_TASKS_HARD", 300.0),
                as_float(values, "RESOURCE_PENDING_TASKS_CRITICAL", 1000.0),
                None,
            ),
        )
        for label, soft, hard, critical, maximum in ordered_groups:
            if not (0 < soft < hard < critical):
                errors.append(f"{label} must satisfy 0 < soft < hard < critical")
            elif maximum is not None and critical > maximum:
                errors.append(f"{label} critical threshold exceeds {maximum:g}")

        hysteresis = as_float(values, "RESOURCE_RECOVERY_HYSTERESIS_RATIO", 0.10)
        if not 0 <= hysteresis <= 0.50:
            errors.append("RESOURCE_RECOVERY_HYSTERESIS_RATIO must be between 0 and 0.50")

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
