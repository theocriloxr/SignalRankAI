#!/usr/bin/env python3
"""Offline verifier for the v1.2.3 log-driven Railway hotfix."""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(f"FAIL {message}")
    print(f"PASS {message}")


def main() -> None:
    for name in (
        "elliott", "fibonacci", "harmonic", "ict_smc", "indicators",
        "order_flow", "price_action", "supply_demand", "wyckoff",
    ):
        importlib.import_module(f"engine.adaptive.{name}")
    require(True, "adaptive compatibility imports")

    from core.version import APP_VERSION, RELEASE_FINGERPRINT
    require(APP_VERSION == "1.2.3", "runtime version")
    require(RELEASE_FINGERPRINT.startswith("v1.2.3-"), "release fingerprint")

    from runtime_safety import FULL_SYSTEM_STAGING_TEST_ACK_VALUE, is_full_system_ack_valid
    require(is_full_system_ack_valid(FULL_SYSTEM_STAGING_TEST_ACK_VALUE), "exact staging acknowledgement")
    require(is_full_system_ack_valid(f'"{FULL_SYSTEM_STAGING_TEST_ACK_VALUE}"'), "quoted Railway acknowledgement")

    core_source = (ROOT / "engine" / "core.py").read_text(encoding="utf-8")
    stop_index = core_source.index("sig['stop_loss'] = sl")
    ultra_index = core_source.index("if _env_bool('ULTRA_QUALITY_ENABLED'", stop_index)
    require(stop_index < ultra_index, "risk levels before ultra-quality gate")
    require("_regime_candles," in core_source, "regime uses candle sequence")

    paper_source = (ROOT / "core" / "paper_trading_service.py").read_text(encoding="utf-8")
    require("except NoncriticalWriteDropped" in paper_source, "paper DB deferral handling")
    require("PAPER_WORKER_DB_PRIORITY" in paper_source, "paper DB priority control")

    profile = (ROOT / "SignalRankAI_v1.2.3_Railway_Full_System_Staging_Test.env.example").read_text(encoding="utf-8")
    require("APP_VERSION=1.2.3" in profile, "staging profile version")
    require("PROXY_VALIDATION_ENABLED=0" in profile, "proxy validation safe default")
    require("BYBIT_TESTNET=1" in profile and "MT5_ALLOW_LIVE_ACCOUNTS=0" in profile, "external sandbox boundaries")
    print("PASS v1.2.3 log-driven hotfix verification")


if __name__ == "__main__":
    main()
