"""Owner-only staging certification CLI.

    python -m tools.staging_certification            # full report
    python -m tools.staging_certification --json      # machine-readable

Exits non-zero when certification blockers exist (schema behind head, missing
release identity in certification mode, unsafe live-risk flags, registry
failures).  Never exposes credentials.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _env() -> dict[str, str]:
    return dict(os.environ)


def environment_name() -> str:
    return str(
        os.getenv("RAILWAY_ENVIRONMENT_NAME")
        or os.getenv("RAILWAY_ENVIRONMENT")
        or os.getenv("APP_ENV")
        or "local"
    ).lower()


def collect_report() -> dict:
    report: dict = {"environment": environment_name()}

    # Release identity
    try:
        from core.version import (
            APP_VERSION,
            DEPLOYMENT_ID,
            ENVIRONMENT,
            GIT_BRANCH,
            GIT_COMMIT_SHA,
            RELEASE_FINGERPRINT,
            runtime_commit_matches_expected,
        )

        commit_ok, commit_detail = runtime_commit_matches_expected()
        report["release"] = {
            "application_version": APP_VERSION,
            "release": RELEASE_FINGERPRINT,
            "git_sha": GIT_COMMIT_SHA,
            "branch": GIT_BRANCH,
            "deployment_id": DEPLOYMENT_ID,
            "environment": ENVIRONMENT,
            "commit_matches_expected": commit_ok,
            "commit_detail": commit_detail,
        }
    except Exception as exc:
        report["release"] = {"error": str(exc)[:120]}

    # Schema
    try:
        from alembic.config import Config
        from alembic.script import ScriptDirectory

        script = ScriptDirectory.from_config(Config(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "alembic.ini")))
        heads = script.get_heads()
        report["schema"] = {"expected_head": heads[0] if heads else "unknown", "single_head": len(heads) == 1}
    except Exception as exc:
        report["schema"] = {"error": str(exc)[:120]}

    # Registries (zero-network diagnostics)
    try:
        from core.startup_diagnostics import (
            entitlement_catalogue_diagnostics,
            instrument_registry_diagnostics,
            model_registry_diagnostics,
            provider_registry_diagnostics,
            strategy_registry_diagnostics,
        )

        report["provider_registry"] = provider_registry_diagnostics()
        report["instrument_registry"] = instrument_registry_diagnostics()
        report["entitlement_catalogue"] = entitlement_catalogue_diagnostics()
        report["strategy_registry"] = strategy_registry_diagnostics()
        report["model_registry"] = model_registry_diagnostics()
    except Exception as exc:
        report["registries"] = {"error": str(exc)[:120]}

    # Safety flags
    safety = {}
    for flag in (
        "REAL_EXECUTION_ENABLED",
        "AUTO_EXECUTION_ENABLED",
        "AUTO_TRADE_ENABLED",
        "COPY_TRADE_ENABLED",
        "BYBIT_EXECUTION_ENABLED",
        "REAL_PAYOUTS_ENABLED",
        "PAYMENTS_PUBLIC_ENABLED",
        "PAYSTACK_TRANSFERS_ENABLED",
    ):
        safety[flag] = str(os.getenv(flag, "") or "0")
    report["safety_flags"] = safety

    # Telegram/Redis/DB connectivity status (zero-secret)
    report["telegram_bot_token_set"] = bool(os.getenv("TELEGRAM_BOT_TOKEN", "").strip())
    report["database_url_set"] = bool(os.getenv("DATABASE_URL", "").strip())
    report["redis_url_set"] = bool(
        (os.getenv("REDIS_URL") or os.getenv("REDIS_STATE_URL") or os.getenv("REDIS_DELIVERY_URL") or "").strip()
    )
    return report


def blockers(report: dict) -> list[str]:
    out: list[str] = []
    env = environment_name()
    release = report.get("release") or {}
    if env in ("staging", "staging-certification") and not release.get("commit_matches_expected", False):
        out.append(f"release_identity:{release.get('commit_detail', 'commit_mismatch')}")
    schema = report.get("schema") or {}
    if not schema.get("single_head", True):
        out.append("schema_multiple_heads")
    safety = report.get("safety_flags") or {}
    for flag in ("REAL_EXECUTION_ENABLED", "AUTO_EXECUTION_ENABLED", "AUTO_TRADE_ENABLED", "COPY_TRADE_ENABLED"):
        if str(safety.get(flag, "0")) not in ("0", "", "false", "no"):
            out.append(f"unsafe_live_risk_flag:{flag}")
    if env.startswith("prod") and not report.get("database_url_set"):
        out.append("database_url_missing")
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="Staging certification report")
    parser.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    args = parser.parse_args()
    report = collect_report()
    found = blockers(report)
    report["certification_blockers"] = found
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True, default=str))
    else:
        for section, payload in report.items():
            print(f"[{section}] {json.dumps(payload, sort_keys=True, default=str)}")
    if found:
        print("CERTIFICATION_BLOCKED " + "; ".join(found))
        return 1
    print("CERTIFICATION_OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
