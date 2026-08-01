#!/usr/bin/env python3
"""Build a redacted certification bundle without manufacturing PASS results."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

PASS = "PASS"
BLOCKED = "BLOCKED"
SAFE_EXPECTED_OFF = "SAFE_EXPECTED_OFF"
NOT_IN_SCOPE = "NOT_IN_SCOPE"
ALLOWED_EXTERNAL_TYPES = {"sandbox external", "live read-only", "live write canary"}

ARTIFACTS = {
    "migration.json": "SIGNALRANK_MIGRATION_EVIDENCE",
    "paper_certification.json": "SIGNALRANK_CERTIFICATION_PAPER_EVIDENCE",
    "metaapi_demo_certification.json": "SIGNALRANK_CERTIFICATION_METAAPI_DEMO_EVIDENCE",
    "bybit_testnet_certification.json": "SIGNALRANK_CERTIFICATION_BYBIT_TESTNET_EVIDENCE",
    "paystack_test_certification.json": "SIGNALRANK_CERTIFICATION_PAYSTACK_TEST_EVIDENCE",
    "provider_certification.json": "SIGNALRANK_CERTIFICATION_LIVE_PROVIDER_CERTIFICATION_EVIDENCE",
    "queue_certification.json": "SIGNALRANK_CERTIFICATION_QUEUE_EVIDENCE",
    "scheduler_certification.json": "SIGNALRANK_CERTIFICATION_SCHEDULER_EVIDENCE",
    "security_scan_summary.json": "SIGNALRANK_CERTIFICATION_SECURITY_SCANS_EVIDENCE",
    "full_system_e2e.json": "SIGNALRANK_CERTIFICATION_FULL_SYSTEM_E2E_EVIDENCE",
}

SECRET_PATTERN = re.compile(r"(token|secret|password|api[_-]?key|private[_-]?key|database_url|redis_url)", re.I)


def _value(name: str) -> str:
    return str(os.getenv(name) or "").strip()


def _redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: "<redacted>" if SECRET_PATTERN.search(str(key)) else _redact(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_redact(item) for item in value]
    return value


def _load_proof(env_name: str, artifact_name: str) -> dict[str, Any]:
    raw = _value(env_name)
    if not raw:
        return {
            "status": BLOCKED,
            "artifact": artifact_name,
            "evidence_type": "integration",
            "detail": f"{env_name} is missing; no proof was supplied",
        }
    source = Path(raw)
    if not source.is_absolute():
        source = ROOT / source
    if not source.is_file():
        return {
            "status": BLOCKED,
            "artifact": artifact_name,
            "evidence_type": "integration",
            "detail": "referenced proof file does not exist",
            "reference": str(source),
        }
    try:
        payload = json.loads(source.read_text(encoding="utf-8"))
    except Exception as exc:
        return {
            "status": BLOCKED,
            "artifact": artifact_name,
            "evidence_type": "integration",
            "detail": f"invalid proof JSON: {type(exc).__name__}",
            "reference": str(source),
        }
    status = str(payload.get("status") or BLOCKED)
    evidence_type = str(payload.get("evidence_type") or "").lower()
    if status == PASS and artifact_name != "migration.json" and evidence_type not in ALLOWED_EXTERNAL_TYPES:
        payload["status"] = BLOCKED
        payload["detail"] = "PASS rejected: evidence_type is not external"
    payload["source_reference"] = str(source)
    return _redact(payload)


def _git(*args: str) -> str:
    try:
        return subprocess.check_output(["git", *args], cwd=ROOT, text=True, stderr=subprocess.DEVNULL).strip()
    except Exception:
        return "unknown"


def _deployment_payload(profile: str) -> dict[str, Any]:
    from core.version import APP_VERSION, RELEASE_FINGERPRINT, get_version_banner, runtime_commit_matches_expected

    railway = bool(_value("RAILWAY_DEPLOYMENT_ID"))
    commit_ok, commit_detail = runtime_commit_matches_expected()
    return {
        "status": PASS if railway and commit_ok else BLOCKED,
        "evidence_type": "live read-only" if railway else "integration",
        "application_version": APP_VERSION,
        "release": RELEASE_FINGERPRINT,
        "version_banner": get_version_banner(),
        "git_commit": _value("RAILWAY_GIT_COMMIT_SHA") or _git("rev-parse", "HEAD"),
        "git_branch": _value("RAILWAY_GIT_BRANCH") or _git("branch", "--show-current"),
        "railway_deployment_id": _value("RAILWAY_DEPLOYMENT_ID") or None,
        "railway_project": _value("RAILWAY_PROJECT_NAME") or _value("RAILWAY_PROJECT_ID") or None,
        "railway_service": _value("RAILWAY_SERVICE_NAME") or None,
        "environment_profile": profile,
        "detail": commit_detail if railway else "local bundle; Railway deployment proof unavailable",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", choices=("staging-certification", "production-advisory", "production-live-owner-canary"), default=_value("SIGNALRANK_ENV_PROFILE") or "production-advisory")
    parser.add_argument("--deployment-id", default=_value("RAILWAY_DEPLOYMENT_ID"))
    parser.add_argument("--output-root", default="artifacts/certification")
    args = parser.parse_args()

    generated_at = datetime.now(timezone.utc)
    raw_id = args.deployment_id or generated_at.strftime("local-%Y%m%dT%H%M%SZ")
    deployment_id = re.sub(r"[^A-Za-z0-9_.-]+", "-", raw_id)
    root = Path(args.output_root)
    if not root.is_absolute():
        root = ROOT / root
    output = root / deployment_id
    output.mkdir(parents=True, exist_ok=False)

    results: dict[str, dict[str, Any]] = {}
    deployment = _deployment_payload(args.profile)
    (output / "deployment.json").write_text(json.dumps(deployment, indent=2, sort_keys=True), encoding="utf-8")
    results["deployment.json"] = deployment

    for filename, env_name in ARTIFACTS.items():
        payload = _load_proof(env_name, filename)
        (output / filename).write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        results[filename] = payload

    required = set(ARTIFACTS) | {"deployment.json"}
    blockers = sorted(name for name in required if results[name].get("status") != PASS)
    summary = {
        "status": PASS if not blockers else BLOCKED,
        "report_id": deployment_id,
        "generated_at": generated_at.isoformat(),
        "profile": args.profile,
        "blockers": blockers,
        "artifacts": {name: payload.get("status") for name, payload in sorted(results.items())},
        "statement": "No missing or unverified evidence was converted to PASS.",
    }
    (output / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    rollback = """# Rollback plan\n\n1. Set `GLOBAL_EXECUTION_KILL_SWITCH=1` and disable all new real execution flags.\n2. Preserve broker reconciliation for already-open positions; do not blindly resubmit ambiguous orders.\n3. Roll Railway back to the last verified commit and verify `/readyz`.\n4. Restore the verified database backup only after an owner-approved data-impact review.\n5. Drain or quarantine delivery queues with the repository recovery commands.\n6. Reconcile broker, payment, execution and performance ledgers before reopening traffic.\n"""
    (output / "rollback_plan.md").write_text(rollback, encoding="utf-8")
    print(json.dumps({"output": str(output), **summary}, sort_keys=True))
    return 0 if summary["status"] == PASS else 2


if __name__ == "__main__":
    raise SystemExit(main())
