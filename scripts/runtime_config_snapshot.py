#!/usr/bin/env python3
"""Validate a Railway environment profile and emit a secret-safe snapshot.

This tool never prints secret values.  It is suitable for CI, release evidence,
and a Railway pre-deploy command.  It validates the selected profile against
known single-service safety invariants and can optionally compare the process
environment with the profile.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
from typing import Mapping

ROOT = Path(__file__).resolve().parents[1]
SECRET_PATTERN = re.compile(r"(?:TOKEN|SECRET|PASSWORD|PRIVATE|ENCRYPTION|API_KEY|DATABASE_URL|REDIS_URL)", re.I)


@dataclass(frozen=True, slots=True)
class ConfigFinding:
    level: str
    code: str
    message: str


@dataclass(frozen=True, slots=True)
class ConfigSnapshot:
    profile: str
    generated_at: str
    profile_sha256: str
    values: dict[str, str]
    findings: list[dict[str, str]]
    valid: bool


def parse_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if key and re.fullmatch(r"[A-Z][A-Z0-9_]*", key):
            values[key] = value.strip()
    return values


def _truthy(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _integer(values: Mapping[str, str], key: str, default: int = 0) -> int:
    try:
        return int(str(values.get(key, default)).strip())
    except (TypeError, ValueError):
        return default


def redact_values(values: Mapping[str, str]) -> dict[str, str]:
    output: dict[str, str] = {}
    for key, value in sorted(values.items()):
        if SECRET_PATTERN.search(key):
            output[key] = "<configured>" if str(value).strip() else "<missing>"
        else:
            output[key] = str(value)
    return output


def validate_config(values: Mapping[str, str], *, profile_name: str = "") -> list[ConfigFinding]:
    findings: list[ConfigFinding] = []

    def error(code: str, message: str) -> None:
        findings.append(ConfigFinding("error", code, message))

    def warning(code: str, message: str) -> None:
        findings.append(ConfigFinding("warning", code, message))

    app_env = str(values.get("APP_ENV", "")).strip().lower()
    if app_env == "production" and _truthy(values.get("PUBLIC_TESTING_MODE")):
        error("production_public_testing", "PUBLIC_TESTING_MODE must be disabled in production")

    if _integer(values, "UVICORN_WORKERS", 1) != 1:
        error("worker_count", "Railway Hobby monolith requires exactly one Uvicorn worker")

    for key in ("DB_POOL_SIZE", "DB_POOL_SIZE_RAILWAY"):
        if _integer(values, key, 2) > 2:
            error("db_pool_cap", f"{key} exceeds the safe monolith cap of 2")
    for key in ("DB_MAX_OVERFLOW", "DB_MAX_OVERFLOW_RAILWAY"):
        if _integer(values, key, 0) != 0:
            error("db_overflow", f"{key} must be 0 for the Railway monolith")
    if _integer(values, "REDIS_MAX_CONNECTIONS", 24) > 24:
        error("redis_pool_cap", "REDIS_MAX_CONNECTIONS exceeds the safe default of 24")

    state_url = str(values.get("STATE_REDIS_URL") or values.get("REDIS_URL") or "").strip()
    delivery_url = str(values.get("DELIVERY_REDIS_URL") or "").strip()
    if not state_url:
        error("state_redis_missing", "STATE_REDIS_URL or REDIS_URL is required")
    if not delivery_url:
        error("delivery_redis_missing", "DELIVERY_REDIS_URL is required")
    if _truthy(values.get("REQUIRE_DISTINCT_DELIVERY_REDIS", "1")) and state_url and delivery_url and state_url == delivery_url:
        error("redis_not_distinct", "State and delivery Redis services must be distinct")

    execution_enabled = any(
        _truthy(values.get(key))
        for key in ("AUTO_TRADE_ENABLED", "COPY_TRADE_ENABLED", "REAL_EXECUTION_ENABLED")
    )
    if execution_enabled:
        if not _truthy(values.get("REAL_EXECUTION_ENABLED")):
            error("execution_gate", "AUTO/COPY trading cannot be enabled while REAL_EXECUTION_ENABLED is off")
        if not _truthy(values.get("MT5_ALLOW_LIVE_ACCOUNTS")):
            warning("live_accounts_off", "execution is enabled but live broker accounts remain disabled")
        if not str(values.get("ENCRYPTION_KEY") or "").strip():
            error("encryption_key_missing", "execution requires ENCRYPTION_KEY")

    if _truthy(values.get("PAYMENTS_PUBLIC_ENABLED")) and not str(values.get("PAYSTACK_SECRET_KEY") or "").strip():
        error("paystack_secret_missing", "public payments require PAYSTACK_SECRET_KEY")

    if app_env == "production" and _truthy(values.get("ML_OFFLINE_BOOTSTRAP_ENABLED")):
        error("synthetic_ml", "synthetic/offline ML bootstrap must be disabled in production")
    for key in ("ML_TRAIN_ENABLED", "ANALYTICS_ML_TRAIN_ENABLED", "ML_DRIFT_MONITOR_ENABLED"):
        if app_env == "production" and _truthy(values.get(key)) and str(values.get("RUN_MODE", "all")) == "all":
            warning("monolith_heavy_ml", f"{key} is enabled in the live monolith")

    if _truthy(values.get("DELIVERY_FRESHNESS_TIMEOUT_FAIL_OPEN")):
        error("delivery_fail_open", "delivery freshness timeout must fail closed")
    if _truthy(values.get("DELIVERY_FRESHNESS_ERROR_FAIL_OPEN")):
        error("delivery_fail_open", "delivery freshness errors must fail closed")
    if _truthy(values.get("DELIVERY_MISSING_PRICE_FAIL_OPEN")):
        error("delivery_fail_open", "missing delivery price must fail closed")

    if not _truthy(values.get("OUTCOME_TRACK_DELIVERED_ONLY", "1")):
        error("outcome_truth", "production outcomes must be delivery-proof based")
    if not _truthy(values.get("PORTFOLIO_EXPOSURE_REQUIRE_DELIVERED", "1")):
        error("exposure_truth", "portfolio exposure must require delivery proof")

    if _truthy(values.get("AUTO_MIGRATE")) or _truthy(values.get("RUN_DB_MIGRATIONS_AT_BOOT")):
        warning("auto_migrate", "automatic migration should be enabled only for one controlled deployment")

    for key in ("DATABASE_URL", "TELEGRAM_BOT_TOKEN", "TELEGRAM_WEBHOOK_SECRET", "WEBHOOK_DOMAIN", "OWNER_IDS", "ENCRYPTION_KEY"):
        if not str(values.get(key) or "").strip():
            warning("required_secret_missing", f"{key} is blank in {profile_name or 'configuration'}; set it securely at deployment")

    return findings


def build_snapshot(profile_path: Path, *, environment: Mapping[str, str] | None = None, merge_environment: bool = False) -> ConfigSnapshot:
    profile = parse_env_file(profile_path)
    effective = dict(profile)
    if merge_environment:
        source = os.environ if environment is None else environment
        for key in profile:
            if key in source:
                effective[key] = str(source[key])
        # Include safety-relevant variables even if they are absent from the profile.
        for key in (
            "PAYSTACK_SECRET_KEY", "REAL_EXECUTION_ENABLED", "AUTO_TRADE_ENABLED",
            "COPY_TRADE_ENABLED", "MT5_ALLOW_LIVE_ACCOUNTS",
        ):
            if key in source:
                effective[key] = str(source[key])

    findings = validate_config(effective, profile_name=profile_path.name)
    digest = hashlib.sha256(profile_path.read_bytes()).hexdigest()
    return ConfigSnapshot(
        profile=str(profile_path),
        generated_at=datetime.now(timezone.utc).isoformat(),
        profile_sha256=digest,
        values=redact_values(effective),
        findings=[asdict(item) for item in findings],
        valid=not any(item.level == "error" for item in findings),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", default="configs/env/railway-hobby-owner-beta.env.example")
    parser.add_argument("--merge-environment", action="store_true")
    parser.add_argument("--output", default="artifacts/runtime-config-snapshot.json")
    args = parser.parse_args()

    profile_path = Path(args.profile)
    if not profile_path.is_absolute():
        profile_path = ROOT / profile_path
    snapshot = build_snapshot(profile_path, merge_environment=args.merge_environment)
    output = Path(args.output)
    if not output.is_absolute():
        output = ROOT / output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(asdict(snapshot), indent=2, sort_keys=True), encoding="utf-8")

    for finding in snapshot.findings:
        print(f"{finding['level'].upper()} {finding['code']}: {finding['message']}")
    print(f"valid={snapshot.valid} output={output}")
    return 0 if snapshot.valid else 1


if __name__ == "__main__":
    raise SystemExit(main())
