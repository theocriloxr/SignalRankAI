"""Evidence-based public-testing release guard.

The guard is intentionally conservative: it can approve limited testing only
when unsafe execution and payouts are disabled.  It never turns a feature on.
"""

from __future__ import annotations

import os
from dataclasses import asdict, dataclass
from typing import Any, Mapping

from core.env import SafetyFlags, env_bool, env_int
from core.financial_activation import evaluate_financial_activation


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


def _evidence(supplied: Mapping[str, Any], key: str, certification_env: str) -> bool:
    if supplied.get(key) is True:
        return True
    return bool(str(os.getenv(certification_env) or "").strip())


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
    financial = evaluate_financial_activation()
    checks = [
        GuardCheck("auto_trading_safe", not flags.auto_trade_enabled or financial.ok, "AUTO trading is off or its full live-financial contract passes"),
        GuardCheck("copy_trading_safe", not flags.copy_trade_enabled or financial.ok, "COPY trading is off or its full live-financial contract passes"),
        GuardCheck("real_payouts_safe", not flags.real_payouts_enabled or financial.ok, "real payouts are off or their manual-approval contract passes"),
        GuardCheck("financial_activation_contract", financial.ok, "live-money dependency graph is valid"),
        GuardCheck(
            "stale_blocking_enabled",
            _evidence(supplied, "stale_blocking_enabled", "FRESHNESS_CERTIFICATION_ID"),
            "final freshness gate requires explicit verification evidence",
        ),
        GuardCheck(
            "delivery_proof",
            _evidence(supplied, "delivery_proof", "DELIVERY_LIFECYCLE_CERTIFICATION_ID"),
            "delivery proof requires explicit end-to-end evidence",
        ),
        GuardCheck(
            "outcome_tracker",
            _evidence(supplied, "outcome_tracker", "OUTCOME_TRACKER_CERTIFICATION_ID"),
            "outcome lifecycle requires explicit verification evidence",
        ),
        GuardCheck(
            "shadow_tracking",
            _evidence(supplied, "shadow_tracking", "SHADOW_TRACKING_CERTIFICATION_ID"),
            "shadow rejected-signal tracking and false-negative classification require certification",
        ),
        GuardCheck(
            "engine_pulse_integrity",
            _evidence(supplied, "engine_pulse_integrity", "ENGINE_PULSE_CERTIFICATION_ID"),
            "Engine Pulse counters, source attribution and reconciliation require certification",
        ),
        GuardCheck(
            "performance_truth",
            _evidence(supplied, "performance_truth", "PERFORMANCE_TRUTH_CERTIFICATION_ID"),
            "provenance-separated metrics require explicit verification evidence",
        ),
        GuardCheck(
            "payments_configured",
            not flags.payments_enabled
            or _flag("PAYMENTS_PUBLIC_TEST_MODE", False)
            or not _flag("PAYMENTS_PUBLIC_ENABLED", False)
            or (str(os.getenv("PAYSTACK_SECRET_KEY") or "").strip().startswith("sk_live_")
                and str(os.getenv("PAYSTACK_PUBLIC_KEY") or "").strip().startswith("pk_live_")),
            "public payments require a live Paystack key pair",
        ),
        GuardCheck(
            "no_secret_leakage",
            _evidence(supplied, "no_secret_leakage", "SECRET_SCAN_CERTIFICATION_ID"),
            "secret scan/redaction requires explicit evidence",
        ),
        GuardCheck(
            "tests",
            _evidence(supplied, "tests_passed", "TEST_CERTIFICATION_ID"),
            "test result requires explicit evidence",
        ),
        GuardCheck(
            "ohlc_pipeline",
            _evidence(supplied, "ohlc_pipeline", "OHLC_PIPELINE_CERTIFICATION_ID"),
            "at least one asset must produce usable required OHLC",
        ),
        GuardCheck(
            "telegram_delivery_lifecycle",
            _evidence(supplied, "telegram_delivery_lifecycle", "TELEGRAM_LIFECYCLE_CERTIFICATION_ID"),
            "Telegram send, proof, active message, and WATCHING_ENTRY require explicit evidence",
        ),
        GuardCheck(
            "profile_routing",
            _evidence(supplied, "profile_routing", "PROFILE_ROUTING_CERTIFICATION_ID"),
            "profile-driven discovery, ranking, delivery, paper and broker routing require certification",
        ),
        GuardCheck(
            "paper_trading_integrity",
            _evidence(supplied, "paper_trading_integrity", "PAPER_TRADING_CERTIFICATION_ID"),
            "freshness, one-asset exposure, close-all and ledger accounting require certification",
        ),
        GuardCheck(
            "asset_discovery",
            _evidence(supplied, "asset_discovery", "ASSET_DISCOVERY_CERTIFICATION_ID")
            and not _flag("ALLOW_STATIC_ASSET_FALLBACK", False),
            "dynamic provider-backed discovery must be certified and static fallback disabled",
        ),
        GuardCheck(
            "ml_calibration",
            _evidence(supplied, "ml_calibration", "ML_CALIBRATION_ARTIFACT_ID"),
            "public probability and live execution require a persisted validated calibration artifact",
        ),
        GuardCheck(
            "public_claim_evidence",
            (not _flag("PUBLIC_WIN_RATE_MARKETING_ENABLED", False))
            or _evidence(supplied, "public_claim_evidence", "PERFORMANCE_CLAIM_CERTIFICATION_ID"),
            "a public win-rate claim requires a separately certified statistical report",
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
        "auto_trading_enabled": flags.auto_trade_enabled,
        "copy_trading_enabled": flags.copy_trade_enabled,
        "financial_activation": evaluate_financial_activation().as_dict(),
        "payments_enabled": flags.payments_enabled,
        "real_payouts_enabled": _flag("REAL_PAYOUTS_ENABLED", False),
        "checks": [asdict(check) for check in report.checks],
    }


__all__ = ["GuardCheck", "ReleaseReport", "evaluate_release", "public_test_status"]
