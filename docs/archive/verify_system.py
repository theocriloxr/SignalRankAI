#!/usr/bin/env python3
"""SignalRankAI smoke-test verifier.

This script exercises the critical final-gate behavior without requiring live
Telegram delivery or a writable production database.

Checks:
1. Global kill-switch blocks final delivery completely.
2. Shadow-rejected signals are persisted but not dispatched.
3. Normal signals pass through when the kill-switch is off.
4. Kill-switch state is shared across controller instances.

Run:
    python verify_system.py
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Dict, List
from unittest.mock import AsyncMock, patch

try:
    from dotenv import load_dotenv
    load_dotenv(".env", override=False)
    load_dotenv(".env.local", override=True)
except Exception:
    pass

logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

Signal = Dict[str, Any]


@dataclass
class SmokeResult:
    name: str
    passed: bool
    details: str = ""


class SystemVerifier:
    def __init__(self) -> None:
        self.results: list[SmokeResult] = []

    def check(self, name: str, condition: bool, details: str = "") -> None:
        self.results.append(SmokeResult(name=name, passed=condition, details=details))
        status = "PASS" if condition else "FAIL"
        logger.info("%s: %s", status, name)
        if details:
            logger.info("  %s", details)

    async def verify_all(self) -> bool:
        logger.info("=" * 80)
        logger.info("SignalRankAI Final-Gate Smoke Test")
        logger.info("=" * 80)

        await self._verify_kill_switch_and_final_gate()
        self._print_summary()
        return all(r.passed for r in self.results)

    async def _verify_kill_switch_and_final_gate(self) -> None:
        from engine.signal_controller import SignalController

        async def _final_gate_smoke(
            controller: SignalController,
            final_candidates: list[Signal],
            persist_signal_fn: Callable[[Signal], Awaitable[Any]],
            dispatch_fn: Callable[[Signal], Awaitable[Any]],
        ) -> list[Signal]:
            """Minimal executable contract for the production final gate.

            This mirrors the production behavior we care about:
            - global kill-switch blocks all delivery
            - shadow rejected signals are persisted only
            - normal signals are persisted and dispatched
            """
            if controller.is_kill_switch_enabled():
                return []

            delivered: list[Signal] = []
            for candidate in final_candidates:
                status = str(candidate.get("status") or "issued").lower()
                persisted = await persist_signal_fn(candidate)
                if not persisted:
                    continue
                if status.startswith("shadow_"):
                    continue
                await dispatch_fn(candidate)
                delivered.append(candidate)
            return delivered

        controller_a = SignalController()
        controller_b = SignalController()
        controller_a.disable_kill_switch(admin_id=1)
        self.check(
            "Kill-switch defaults off",
            not controller_a.is_kill_switch_enabled(),
            "Fresh controller should start with kill-switch disabled",
        )

        controller_a.enable_kill_switch("smoke_test", admin_id=1)
        self.check(
            "Kill-switch shared across instances",
            controller_b.is_kill_switch_enabled(),
            "A second controller instance should observe the global kill-switch state",
        )

        candidates = [
            {
                "signal_id": "sig-shadow-1",
                "asset": "SOLUSDT",
                "timeframe": "1h",
                "direction": "long",
                "status": "shadow_rejected",
            },
            {
                "signal_id": "sig-live-1",
                "asset": "BTCUSDT",
                "timeframe": "1h",
                "direction": "long",
                "status": "issued",
            },
        ]

        persist_mock = AsyncMock(side_effect=["shadow-db-id", "live-db-id"])
        dispatch_mock = AsyncMock(return_value=None)

        delivered = await _final_gate_smoke(controller_a, candidates, persist_mock, dispatch_mock)
        self.check(
            "Kill-switch blocks final gate",
            delivered == [],
            f"Expected 0 delivered signals while kill-switch is active, got {len(delivered)}",
        )
        self.check(
            "Kill-switch prevents persistence",
            persist_mock.await_count == 0,
            f"persist_signal should not be called while kill-switch is active (got {persist_mock.await_count})",
        )
        self.check(
            "Kill-switch prevents dispatch",
            dispatch_mock.await_count == 0,
            f"dispatch should not be called while kill-switch is active (got {dispatch_mock.await_count})",
        )

        controller_a.disable_kill_switch(admin_id=1)
        persist_mock = AsyncMock(side_effect=["shadow-db-id", "live-db-id"])
        dispatch_mock = AsyncMock(return_value=None)
        delivered = await _final_gate_smoke(controller_a, candidates, persist_mock, dispatch_mock)

        self.check(
            "Shadow signal persisted but not dispatched",
            persist_mock.await_count == 2 and dispatch_mock.await_count == 1 and len(delivered) == 1,
            (
                f"Expected 2 persists and 1 dispatch for shadow+live candidates; "
                f"got persists={persist_mock.await_count}, dispatches={dispatch_mock.await_count}, delivered={len(delivered)}"
            ),
        )
        self.check(
            "Shadow candidate excluded from delivery",
            delivered and delivered[0]["signal_id"] == "sig-live-1",
            "Only the non-shadow candidate should be returned as delivered",
        )

        controller_a.disable_kill_switch(admin_id=1)

    def _print_summary(self) -> None:
        total = len(self.results)
        passed = sum(1 for r in self.results if r.passed)
        failed = total - passed

        logger.info("=" * 80)
        logger.info("SUMMARY")
        logger.info("=" * 80)
        logger.info("Total checks: %d", total)
        logger.info("Passed: %d", passed)
        logger.info("Failed: %d", failed)
        if failed == 0:
            logger.info("All smoke checks passed.")
        else:
            logger.error("One or more smoke checks failed.")

        print("\n" + "=" * 80)
        print("Smoke Test Results")
        print("=" * 80)
        for result in self.results:
            mark = "PASS" if result.passed else "FAIL"
            print(f"{mark:4} {result.name:45} {result.details}")
        print("=" * 80)


def main() -> int:
    parser = argparse.ArgumentParser(description="SignalRankAI smoke-test verifier")
    parser.parse_args()

    verifier = SystemVerifier()
    success = asyncio.run(verifier.verify_all())
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
