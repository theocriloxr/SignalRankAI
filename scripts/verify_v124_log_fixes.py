#!/usr/bin/env python3
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def require(condition: bool, label: str) -> None:
    if not condition:
        raise AssertionError(label)
    print(f"PASS {label}")


def main() -> int:
    from core.version import APP_VERSION, RELEASE_FINGERPRINT
    from runtime_safety import apply_runtime_safety_environment

    require(APP_VERSION == "1.2.4", "code version")
    require(RELEASE_FINGERPRINT == "v1.2.4-runtime-admission-advisory-pipeline-20260729", "release fingerprint")

    env = {
        "RAILWAY_ENVIRONMENT_NAME": "staging",
        "APP_ENV": "production",
        "FULL_SYSTEM_STAGING_TEST_MODE": "1",
        "FULL_SYSTEM_STAGING_TEST_ACK": "I_UNDERSTAND_STAGING_TESTS_CAN_TRIGGER_EXTERNAL_ACTIONS",
        "OWNER_TELEGRAM_ID": "1409578077",
        "PROXY_VALIDATION_ENABLED": "1",
    }
    result = apply_runtime_safety_environment(env)
    require(result.environment == "staging", "Railway environment precedence")
    require(result.full_system_test_enabled, "full-system staging active")
    require(env.get("PAPER_WORKER_DB_PRIORITY") == "interactive", "paper DB admission")
    require(env.get("ADAPTIVE_CANDLE_DB_PRIORITY") == "interactive", "adaptive DB admission")
    require(env.get("PROXY_VALIDATION_ENABLED") == "0", "proxy fail-safe")
    require(env.get("STAGING_QUALITY_GATES_ADVISORY") == "1", "staging advisory gates")

    engine = (ROOT / "engine/core.py").read_text(encoding="utf-8")
    require("'atr_pct': _filter_atr_pct" in engine, "advanced filter ATR context")
    require("_append_staging_advisory" in engine, "advisory signal marker")
    require("_maybe_log_heatmap(asset, cycle_no, len(final_signals))" in engine, "always-on gate telemetry")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
