#!/usr/bin/env python3
"""Static/runtime verifier for SignalRankAI v1.3.6.5 Railway decomposition."""
from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def require(condition: bool, label: str) -> None:
    if not condition:
        raise SystemExit(f"FAIL: {label}")
    print(f"PASS: {label}")


def require_text(path: str, *markers: str) -> str:
    text = (ROOT / path).read_text(encoding="utf-8")
    missing = [marker for marker in markers if marker not in text]
    require(not missing, f"{path} markers {missing or 'present'}")
    return text


def main() -> int:
    from core.version import APP_VERSION, RELEASE_FINGERPRINT
    from runtime.roles import RunMode, parse_run_mode, process_ownership

    require(APP_VERSION == "1.3.6.5", "runtime version")
    require(
        RELEASE_FINGERPRINT == "v1.3.6.5-production-integrity-hardening-20260802",
        "release fingerprint",
    )
    require(parse_run_mode("frontdoor") is RunMode.FRONTDOOR, "frontdoor canonical role")
    require(parse_run_mode("webhook") is RunMode.FRONTDOOR, "webhook compatibility alias")

    ownership = process_ownership(
        "frontdoor",
        {
            "DECOMPOSED_TOPOLOGY_ENABLED": "1",
            "RUN_ENGINE_LOOP": "1",
            "RUN_WORKER_LOOP": "1",
        },
    )
    require(ownership.http and ownership.telegram and ownership.scheduler, "frontdoor owns ingress")
    require(not ownership.engine and not ownership.worker, "frontdoor hard-disables heavy loops")

    try:
        process_ownership("all", {"DECOMPOSED_TOPOLOGY_ENABLED": "1"})
    except ValueError:
        pass
    else:
        raise SystemExit("FAIL: decomposed topology accepted hidden monolith")
    print("PASS: decomposed topology rejects hidden monolith")

    require_text(
        "start.sh",
        "_start_frontdoor()",
        'export RUN_ENGINE_LOOP="0"',
        'export RUN_WORKER_LOOP="0"',
        "refusing hidden monolith fallback",
    )
    require_text(
        "railway_main.py",
        "[runtime_ownership]",
        "Engine loop skipped by ownership",
        "Worker loop skipped by ownership",
        "railway_main:app cannot own RUN_MODE=",
    )
    require_text(
        "db/session.py",
        '"frontdoor"',
        "Railway decomposed role=%s",
        "DB_POOL_RAILWAY_ABSOLUTE_CAP",
    )
    split = require_text(
        "split_signalrank_railway.ps1",
        'RUN_MODE = "frontdoor"',
        'DB_ROLE = "frontdoor"',
        'DB_ROLE = "engine"',
        'DB_ROLE = "worker"',
        'STARTUP_OPS_ENABLED = "0"',
        'Set-ServiceConfig -Service $SourceService -Path "healthcheckPath" -Value "/readyz"',
    )
    require(split.count('DECOMPOSED_TOPOLOGY_ENABLED = "1"') == 3, "all three services are decomposed")

    railway = json.loads((ROOT / "railway.json").read_text(encoding="utf-8"))
    deploy = railway.get("deploy") or {}
    require(deploy.get("startCommand") == "bash start.sh", "neutral Railway start command")
    require("healthcheckPath" not in deploy, "healthcheck is frontdoor service-specific")
    require("preDeployCommand" not in deploy, "predeploy is frontdoor service-specific")

    require((ROOT / "db/migrations/versions/0033_ml_learning_runtime.py").exists(), "migration 0033 retained")
    require((ROOT / "db/migrations/versions/0034_production_integrity.py").exists(), "migration 0034 integrity head present")
    print("overall=PASS release=v1.3.6.5")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
