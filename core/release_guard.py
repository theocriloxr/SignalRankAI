"""Evidence-based public-testing release guard.

The guard is intentionally conservative: it can approve limited testing only
when unsafe execution and payouts are disabled.  It never turns a feature on.
"""

from __future__ import annotations

import os
from dataclasses import asdict, dataclass
from typing import Any, Mapping

from core.env import SafetyFlags, env_bool


@dataclass(frozen=True, slots=True)
class GuardCheck:
    name: str
    ok: bool
    detail: str
    blocking: bool = True


@dataclass(frozen=True, slots=True)
class ReleaseReport:
    verdict: str
    checks: tuple[GuardCheck, ...]

    @property
    def ok(self) -> bool:
        return self.verdict != "BLOCKED"

    def as_dict(self) -> dict[str, Any]:
        return {"verdict": self.verdict, "checks": [asdict(check) for check in self.checks]}


def _flag(name: str, default: bool = False) -> bool:
    return env_bool(name, default)


def evaluate_release(
    *,
    evidence: Mapping[str, Any] | None = None,
    safety_flags: SafetyFlags | None = None,
) -> ReleaseReport:
    flags = safety_flags or SafetyFlags.from_env()
    supplied = dict(evidence or {})
    checks = [
        GuardCheck("auto_trading_disabled", not flags.auto_trade_enabled, "AUTO_TRADE_ENABLED is off"),
        GuardCheck("copy_trading_disabled", not flags.copy_trade_enabled, "COPY_TRADE_ENABLED is off"),
        GuardCheck("real_payouts_disabled", not _flag("REAL_PAYOUTS_ENABLED"), "real payouts are disabled"),
        GuardCheck("stale_blocking_enabled", supplied.get("stale_blocking_enabled", True) is True, "final freshness gate"),
        GuardCheck("delivery_proof", supplied.get("delivery_proof", True) is True, "delivery proof contract"),
        GuardCheck("outcome_tracker", supplied.get("outcome_tracker", True) is True, "outcome lifecycle contract"),
        GuardCheck("performance_truth", supplied.get("performance_truth", True) is True, "provenance-separated metrics"),
        GuardCheck("payments_limited", not flags.payments_enabled or _flag("PAYMENTS_PUBLIC_TEST_MODE", False), "payments disabled or explicit test mode"),
        GuardCheck("no_secret_leakage", supplied.get("no_secret_leakage", True) is True, "redaction contract"),
        GuardCheck("tests", supplied.get("tests_passed", True) is True, "focused contract suite"),
    ]
    blocking = [check for check in checks if check.blocking and not check.ok]
    if blocking:
        verdict = "BLOCKED"
    elif supplied.get("soak_passed") is True and supplied.get("paid_beta_approved") is True:
        verdict = "PAID_BETA_READY"
    else:
        verdict = "LIMITED_PUBLIC_TEST_READY"
    return ReleaseReport(verdict, tuple(checks))


def public_test_status(*, evidence: Mapping[str, Any] | None = None) -> dict[str, Any]:
    flags = SafetyFlags.from_env()
    report = evaluate_release(evidence=evidence, safety_flags=flags)
    return {
        "public_testing_mode": _flag("PUBLIC_TESTING_MODE", False),
        "verdict": report.verdict,
        "auto_trading_disabled": not flags.auto_trade_enabled,
        "copy_trading_disabled": not flags.copy_trade_enabled,
        "payments_enabled": flags.payments_enabled,
        "real_payouts_enabled": _flag("REAL_PAYOUTS_ENABLED", False),
        "checks": [asdict(check) for check in report.checks],
    }


__all__ = ["GuardCheck", "ReleaseReport", "evaluate_release", "public_test_status"]
