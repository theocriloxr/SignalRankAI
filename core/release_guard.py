"""Evidence-based public-testing release guard.

The guard is intentionally conservative: it can approve limited testing only
when unsafe execution and payouts are disabled.  It never turns a feature on.
"""

from __future__ import annotations

import os
from dataclasses import asdict, dataclass
from typing import Any, Mapping

from core.env import SafetyFlags, env_bool, env_int


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


def _check_db_pool_safe() -> GuardCheck:
    """Verify the DB pool configuration is safe for Railway monolith."""
    try:
        from db.session import _effective_pool_settings, _is_railway_runtime, get_pool_diagnostics
        
        # Check for unsafe override env vars
        disable_cap = _flag("DB_POOL_DISABLE_RAILWAY_CAP", False)
        allow_uncapped = _flag("DB_POOL_ALLOW_UNCAPPED_RAILWAY", False)
        public_testing = _flag("PUBLIC_TESTING_MODE", False)
        
        if disable_cap or allow_uncapped:
            if public_testing:
                return GuardCheck(
                    "safe_db_pool",
                    True,
                    "unsafe override blocked by PUBLIC_TESTING_MODE",
                    blocking=False,
                )
            return GuardCheck(
                "safe_db_pool",
                False,
                "DB_POOL_DISABLE_RAILWAY_CAP or DB_POOL_ALLOW_UNCAPPED_RAILWAY override detected",
            )
        
        pool_size, max_overflow = _effective_pool_settings()
        railway = _is_railway_runtime()
        
        public_testing = _flag("PUBLIC_TESTING_MODE", False)
        
        if railway:
            if public_testing:
                # In public-testing mode, enforce the strictest limits
                if pool_size > 2 or max_overflow > 0:
                    return GuardCheck(
                        "safe_db_pool",
                        False,
                        f"PUBLIC_TESTING_MODE: Railway pool exceeds safe limit: pool_size={pool_size}, max_overflow={max_overflow}",
                    )
            else:
                # In non-testing Railway mode, allow operator-configured caps
                # but flag pools above approved threshold as a warning (non-blocking)
                if pool_size > 8 or max_overflow > 2:
                    return GuardCheck(
                        "safe_db_pool",
                        False,
                        f"Railway pool exceeds approved threshold: pool_size={pool_size}, max_overflow={max_overflow}",
                    )
        
        return GuardCheck(
            "safe_db_pool",
            True,
            f"pool_size={pool_size}, max_overflow={max_overflow}",
            blocking=False,
        )
    except Exception as exc:
        return GuardCheck(
            "safe_db_pool",
            False,
            f"DB pool check failed: {type(exc).__name__}: {exc}",
        )


def _check_multiple_engines() -> GuardCheck:
    """Verify no accidental pool multiplication across event loops."""
    try:
        from db.session import _engines_by_loop
        
        engine_count = len(_engines_by_loop)
        if engine_count > 2:
            return GuardCheck(
                "engine_capacity_budget",
                False,
                f"active pooled engines={engine_count} exceeds total connection budget",
            )
        return GuardCheck(
            "engine_capacity_budget",
            True,
            f"active_pooled_engines={engine_count}",
            blocking=False,
        )
    except Exception as exc:
        return GuardCheck(
            "engine_capacity_budget",
            True,
            f"engine inventory unavailable: {type(exc).__name__}: {exc}",
            blocking=False,
        )


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
        GuardCheck(
            "stale_blocking_enabled",
            supplied.get("stale_blocking_enabled", False) is True,
            "final freshness gate requires explicit verification evidence",
        ),
        GuardCheck(
            "delivery_proof",
            supplied.get("delivery_proof", False) is True,
            "delivery proof requires explicit end-to-end evidence",
        ),
        GuardCheck(
            "outcome_tracker",
            supplied.get("outcome_tracker", False) is True,
            "outcome lifecycle requires explicit verification evidence",
        ),
        GuardCheck(
            "performance_truth",
            supplied.get("performance_truth", False) is True,
            "provenance-separated metrics require explicit verification evidence",
        ),
        GuardCheck(
            "payments_limited",
            not flags.payments_enabled
            or _flag("PAYMENTS_PUBLIC_TEST_MODE", False)
            or not _flag("PAYMENTS_PUBLIC_ENABLED", False),
            "payments disabled, private, or explicit test mode",
        ),
        GuardCheck(
            "no_secret_leakage",
            supplied.get("no_secret_leakage", False) is True,
            "secret scan/redaction requires explicit evidence",
        ),
        GuardCheck(
            "tests",
            supplied.get("tests_passed", False) is True,
            "test result requires explicit evidence",
        ),
        GuardCheck(
            "ohlc_pipeline",
            supplied.get("ohlc_pipeline", False) is True,
            "at least one asset must produce usable required OHLC",
        ),
        GuardCheck(
            "telegram_delivery_lifecycle",
            supplied.get("telegram_delivery_lifecycle", False) is True,
            "Telegram send, proof, active message, and WATCHING_ENTRY require explicit evidence",
        ),
        # DB pool safety checks
        _check_db_pool_safe(),
        _check_multiple_engines(),
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
