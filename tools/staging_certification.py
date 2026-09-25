"""Owner-only staging certification CLI.

    python -m tools.staging_certification            # full report
    python -m tools.staging_certification --json      # machine-readable

Exits non-zero when certification blockers exist (schema behind head, missing
release identity in certification mode, unsafe live-risk flags, registry
failures).  Never exposes credentials.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
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


REGISTRIES = (
    "provider_registry", "instrument_registry", "entitlement_catalogue",
    "strategy_registry", "model_registry",
)
LIVE_FLAGS = (
    "REAL_EXECUTION_ENABLED", "AUTO_EXECUTION_ENABLED", "AUTO_TRADE_ENABLED",
    "COPY_TRADE_ENABLED", "MT5_ALLOW_LIVE_ACCOUNTS", "REAL_PAYOUTS_ENABLED",
    "PAYSTACK_TRANSFERS_ENABLED",
)


def collect_report(*, runtime_schema: bool = False) -> dict:
    report: dict = {
        "environment": environment_name(),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "scope": "runtime_admission" if runtime_schema else "offline_preflight",
        # Admission is necessary, but is not E2E, soak or trading certification.
        "full_certification": False,
    }

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
        report["release"] = {"error": type(exc).__name__}

    # Schema
    try:
        from alembic.config import Config
        from alembic.script import ScriptDirectory

        script = ScriptDirectory.from_config(Config(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "alembic.ini")))
        heads = script.get_heads()
        report["schema"] = {"expected_head": heads[0] if len(heads) == 1 else None, "single_head": len(heads) == 1}
    except Exception as exc:
        report["schema"] = {"error": type(exc).__name__}

    if runtime_schema:
        try:
            from scripts.assert_database_schema import check_schema

            report["runtime_schema"] = check_schema()
        except Exception as exc:
            # Driver exceptions may contain connection strings or passwords.
            report["runtime_schema"] = {"ok": False, "error": type(exc).__name__}

    # Registries (zero-network diagnostics)
    try:
        from core.startup_diagnostics import (
            entitlement_catalogue_diagnostics,
            instrument_registry_diagnostics,
            model_registry_diagnostics,
            provider_registry_diagnostics,
            strategy_registry_diagnostics,
        )

        report["provider_registry"] = provider_registry_diagnostics(_env())
        report["instrument_registry"] = instrument_registry_diagnostics()
        report["entitlement_catalogue"] = entitlement_catalogue_diagnostics()
        report["strategy_registry"] = strategy_registry_diagnostics()
        report["model_registry"] = model_registry_diagnostics(_env())
    except Exception as exc:
        report["registries"] = {"error": type(exc).__name__}

    # Safety flags
    safety = {}
    for flag in LIVE_FLAGS:
        safety[flag] = str(os.getenv(flag, "") or "0")
    report["safety_flags"] = safety

    # Telegram/Redis/DB connectivity status (zero-secret)
    report["telegram_bot_token_set"] = bool(os.getenv("TELEGRAM_BOT_TOKEN", "").strip())
    report["database_url_set"] = bool(os.getenv("DATABASE_URL", "").strip())
    report["redis_url_set"] = bool(
        (os.getenv("REDIS_URL") or os.getenv("REDIS_STATE_URL") or os.getenv("REDIS_DELIVERY_URL") or "").strip()
    )
    return report


def blockers(report: dict, *, require_runtime: bool = True) -> list[str]:
    out: list[str] = []
    release = report.get("release") or {}
    if release.get("error") or not release:
        out.append("release_identity:unavailable")
    elif require_runtime and release.get("commit_matches_expected") is not True:
        out.append(f"release_identity:{release.get('commit_detail', 'commit_mismatch')}")
    schema = report.get("schema") or {}
    if schema.get("single_head") is not True or not schema.get("expected_head"):
        out.append("schema_single_head_unproven")
    for name in REGISTRIES:
        diagnostic = report.get(name) or {}
        if diagnostic.get("available") is not True or diagnostic.get("error"):
            out.append(f"registry_unavailable:{name}")
    safety = report.get("safety_flags") or {}
    for flag in LIVE_FLAGS:
        if flag not in safety or str(safety[flag]).strip().lower() not in ("0", "", "false", "no", "off"):
            out.append(f"unsafe_live_risk_flag:{flag}")
    if require_runtime:
        if not report.get("database_url_set"):
            out.append("database_url_missing")
        runtime = report.get("runtime_schema") or {}
        if (
            runtime.get("ok") is not True
            or runtime.get("alembic_current") != schema.get("expected_head")
            or runtime.get("alembic_expected_head") != schema.get("expected_head")
        ):
            out.append("runtime_schema_unproven")
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="Staging certification report")
    parser.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    parser.add_argument("--offline", action="store_true", help="zero-network preflight only; does not certify runtime")
    args = parser.parse_args()
    report = collect_report(runtime_schema=not args.offline)
    found = blockers(report, require_runtime=not args.offline)
    report["certification_blockers"] = found
    report["status"] = "BLOCKED" if found else ("PREFLIGHT_PASS" if args.offline else "RUNTIME_ADMISSION_PASS")
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True, default=str))
    else:
        for section, payload in report.items():
            print(f"[{section}] {json.dumps(payload, sort_keys=True, default=str)}")
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
