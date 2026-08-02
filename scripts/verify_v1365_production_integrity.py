#!/usr/bin/env python3
"""Static and deterministic verifier for SignalRankAI v1.3.6.6.

This verifier intentionally does not activate live money or assert a win rate. It
proves that the release contains the fail-closed controls required before runtime
certification.
"""
from __future__ import annotations

import ast
import json
import os
from datetime import datetime, timezone, timedelta
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def require(condition: bool, label: str) -> None:
    if not condition:
        raise SystemExit(f"FAIL: {label}")
    print(f"PASS: {label}")


def text(path: str, *markers: str) -> str:
    value = (ROOT / path).read_text(encoding="utf-8")
    missing = [marker for marker in markers if marker not in value]
    require(not missing, f"{path} markers")
    return value


def parse(path: str) -> None:
    ast.parse((ROOT / path).read_text(encoding="utf-8"), filename=path)
    print(f"PASS: syntax {path}")


def main() -> int:
    os.environ.setdefault("ALLOW_STATIC_ASSET_FALLBACK", "0")
    os.environ.setdefault("PUBLIC_CLAIM_MIN_TERMINAL_SAMPLE", "200")
    os.environ.setdefault("PUBLIC_CLAIM_MIN_UNIQUE_THESES", "100")
    os.environ.setdefault("PUBLIC_CLAIM_MIN_TERMINAL_COVERAGE", "0.95")

    from core.version import APP_VERSION, RELEASE_FINGERPRINT
    from core.production_integrity import (
        evaluate_public_win_rate_claim,
        evaluate_signal_freshness,
        signal_thesis_fingerprint,
    )
    from core.live_execution_integrity import evaluate_live_signal_admission

    require(APP_VERSION == "1.3.6.6", "release version")
    require(RELEASE_FINGERPRINT == "v1.3.6.6-production-integrity-hardening-20260802", "fingerprint")
    require((ROOT / "db/migrations/versions/0034_production_integrity.py").exists(), "migration 0034")

    for path in (
        "core/production_integrity.py",
        "core/signal_quality_gate.py",
        "core/live_execution_integrity.py",
        "core/outcome_ordering.py",
        "services/profile_demand.py",
        "services/outcome_reconciliation.py",
        "data/pair_discovery.py",
        "core/paper_trading_service.py",
        "engine/core.py",
        "services/performance_ledger.py",
    ):
        parse(path)

    text("engine/core.py", "thesis_fingerprint", "PROFILE_DRIVEN_UNIVERSE_ENABLED", "PROFILE_DRIVEN_TIMEFRAMES_ENABLED")
    text("core/paper_trading_service.py", "duplicate_open_asset", "PAPER_MAX_ENTRY_DEVIATION_BPS", "PAPER_MAX_TOTAL_EXPOSURE_PCT")
    text("services/performance_ledger.py", "PERFORMANCE_CERTIFIED_MIN_TERMINAL_COVERAGE", "thesis_fingerprint")
    text("engine/shadow_outcome_worker.py", "created_at", "ambiguous")
    text("engine/admin_pulse.py", "Confirmed recipient deliveries", "Decision rows evaluated")
    text("core/financial_activation.py", "PRODUCTION_INTEGRITY_CERTIFICATION_ID", "ML_CALIBRATION_ARTIFACT_ID", "ASSET_DISCOVERY_CERTIFICATION_ID")
    text("core/release_guard.py", "asset_discovery", "profile_routing", "ml_calibration")
    text("signalrank_telegram/commands.py", "PROVISIONAL", "NOT FOR PUBLIC CLAIMS")
    text("signalrank_telegram/extended_commands.py", "paper_close_all")

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    stale = evaluate_signal_freshness(timeframe="1h", generated_at=now - timedelta(hours=2), now=now, purpose="paper")
    require(not stale.ok and stale.reason == "signal_stale", "paper stale signal rejected")

    a = signal_thesis_fingerprint({"asset": "BTCUSDT", "direction": "SELL", "strategy": "EMA Trend", "regime": "trend", "entry": 63000, "timeframe": "15m"})
    b = signal_thesis_fingerprint({"asset": "BTCUSDT", "direction": "SHORT", "strategy": "EMA Trend", "regime": "trend", "entry": 63020, "timeframe": "1h"})
    require(a == b, "cross-timeframe repricing collapses to one thesis")

    unsupported = evaluate_public_win_rate_claim(wins=120, losses=80, delivered=240, resolved=200, unique_theses=120)
    require(not unsupported.allowed, "60 percent claim blocked without confidence/coverage proof")
    supported = evaluate_public_win_rate_claim(wins=150, losses=50, delivered=205, resolved=200, unique_theses=150)
    require(supported.allowed, "claim allowed only after statistical gate")

    for key in ("PRODUCTION_INTEGRITY_CERTIFIED", "LIVE_RUNTIME_CERTIFICATION_ID"):
        os.environ.pop(key, None)
    live = evaluate_live_signal_admission({"asset": "BTCUSDT", "direction": "long", "timeframe": "1h", "generated_at": now})
    require(not live.allowed, "live execution fails closed without certification")

    railway = json.loads((ROOT / "railway.json").read_text(encoding="utf-8"))
    require((railway.get("deploy") or {}).get("startCommand") == "bash start.sh", "neutral Railway start command")
    require("healthcheckPath" not in (railway.get("deploy") or {}), "role-specific healthcheck preserved")

    print("overall=PASS release=v1.3.6.6 live_activation=BLOCKED_UNTIL_RUNTIME_CERTIFIED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
