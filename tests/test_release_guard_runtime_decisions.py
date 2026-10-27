from dataclasses import replace
import pytest

from core import release_guard as guard
from core.env import SafetyFlags
from core.financial_activation import FinancialActivationReport

REQUIRED = {
    "stale_blocking_enabled": "FRESHNESS_CERTIFICATION_ID",
    "delivery_proof": "DELIVERY_LIFECYCLE_CERTIFICATION_ID",
    "outcome_tracker": "OUTCOME_TRACKER_CERTIFICATION_ID",
    "shadow_tracking": "SHADOW_TRACKING_CERTIFICATION_ID",
    "engine_pulse_integrity": "ENGINE_PULSE_CERTIFICATION_ID",
    "performance_truth": "PERFORMANCE_TRUTH_CERTIFICATION_ID",
    "no_secret_leakage": "SECRET_SCAN_CERTIFICATION_ID",
    "tests_passed": "TEST_CERTIFICATION_ID",
    "ohlc_pipeline": "OHLC_PIPELINE_CERTIFICATION_ID",
    "telegram_delivery_lifecycle": "TELEGRAM_LIFECYCLE_CERTIFICATION_ID",
    "profile_routing": "PROFILE_ROUTING_CERTIFICATION_ID",
    "paper_trading_integrity": "PAPER_TRADING_CERTIFICATION_ID",
    "asset_discovery": "ASSET_DISCOVERY_CERTIFICATION_ID",
    "ml_calibration": "ML_CALIBRATION_ARTIFACT_ID",
}


@pytest.fixture
def safe_local_guard(monkeypatch):
    import db.session as db
    for name in REQUIRED.values(): monkeypatch.delenv(name, raising=False)
    for name in ("DB_POOL_DISABLE_RAILWAY_CAP", "DB_POOL_ALLOW_UNCAPPED_RAILWAY", "PUBLIC_TESTING_MODE",
                 "ALLOW_STATIC_ASSET_FALLBACK", "PUBLIC_WIN_RATE_MARKETING_ENABLED", "PAYMENTS_PUBLIC_ENABLED"):
        monkeypatch.setenv(name, "0")
    monkeypatch.setattr(db, "_effective_pool_settings", lambda: (2, 0))
    monkeypatch.setattr(db, "_is_railway_runtime", lambda: True)
    monkeypatch.setattr(db, "_engines_by_loop", {})
    monkeypatch.setattr(guard, "evaluate_financial_activation", lambda: FinancialActivationReport(False, False, False, True, ()))
    return {key: True for key in REQUIRED}


def test_complete_limited_testing_evidence_never_enables_money(safe_local_guard):
    flags = SafetyFlags()
    report = guard.evaluate_release(evidence=safe_local_guard, safety_flags=flags)
    assert report.verdict == "LIMITED_PUBLIC_TEST_READY"
    assert flags.enabled_names() == ()
    assert all(check["ok"] for check in report.as_dict()["checks"])


@pytest.mark.parametrize("missing", list(REQUIRED))
def test_missing_runtime_acceptance_proof_blocks_release(safe_local_guard, missing):
    safe_local_guard.pop(missing)
    assert not guard.evaluate_release(evidence=safe_local_guard, safety_flags=SafetyFlags()).ok


def test_failed_current_observation_overrides_stale_environment_certificate(monkeypatch, safe_local_guard):
    monkeypatch.setenv("DELIVERY_LIFECYCLE_CERTIFICATION_ID", "old-release-observation")
    safe_local_guard["delivery_proof"] = False
    report = guard.evaluate_release(evidence=safe_local_guard, safety_flags=SafetyFlags())
    assert report.verdict == "BLOCKED"
    assert not next(check for check in report.checks if check.name == "delivery_proof").ok


def test_missing_engine_inventory_blocks_release(monkeypatch, safe_local_guard):
    import db.session as db
    monkeypatch.delattr(db, "_engines_by_loop")
    assert guard.evaluate_release(evidence=safe_local_guard, safety_flags=SafetyFlags()).verdict == "BLOCKED"


def test_accidental_pool_multiplication_blocks_release(monkeypatch, safe_local_guard):
    import db.session as db
    monkeypatch.setattr(db, "_engines_by_loop", {1: object(), 2: object(), 3: object()})
    assert guard.evaluate_release(evidence=safe_local_guard, safety_flags=SafetyFlags()).verdict == "BLOCKED"


def test_invalid_financial_contract_cannot_be_offset_by_test_evidence(monkeypatch, safe_local_guard):
    monkeypatch.setattr(guard, "evaluate_financial_activation", lambda: FinancialActivationReport(True, True, True, False, ()))
    flags = replace(SafetyFlags(), auto_trade_enabled=True, copy_trade_enabled=True, real_payouts_enabled=True)
    report = guard.evaluate_release(evidence=safe_local_guard, safety_flags=flags)
    assert report.verdict == "BLOCKED"
    assert all(not check.ok for check in report.checks if check.name in {"auto_trading_safe", "copy_trading_safe", "real_payouts_safe", "financial_activation_contract"})


@pytest.mark.parametrize("soak,approval,expected", [(False,True,"LIMITED_PUBLIC_TEST_READY"), (True,False,"LIMITED_PUBLIC_TEST_READY"), (True,True,"PAID_BETA_READY")])
def test_paid_testing_requires_both_soak_and_approval(safe_local_guard, soak, approval, expected):
    safe_local_guard.update(soak_passed=soak, paid_beta_approved=approval)
    assert guard.evaluate_release(evidence=safe_local_guard, safety_flags=SafetyFlags()).verdict == expected


@pytest.mark.parametrize("testing,pool,overflow,override,allowed", [
    (True,2,0,True,True), (True,5,0,True,False), (True,2,1,False,False),
    (False,2,0,True,False), (False,8,2,False,True), (False,9,2,False,False),
    (False,8,3,False,False),
])
def test_release_checks_effective_connection_limits(monkeypatch, safe_local_guard, testing, pool, overflow, override, allowed):
    import db.session as db
    monkeypatch.setenv("PUBLIC_TESTING_MODE", str(int(testing)))
    monkeypatch.setenv("DB_POOL_DISABLE_RAILWAY_CAP", str(int(override)))
    monkeypatch.setattr(db, "_effective_pool_settings", lambda: (pool, overflow))
    assert guard.evaluate_release(evidence=safe_local_guard, safety_flags=SafetyFlags()).ok is allowed


def test_pool_inventory_failure_blocks_without_disclosing_exception_values(monkeypatch, safe_local_guard):
    import db.session as db
    def unavailable(): raise RuntimeError("private-fixture-detail")
    monkeypatch.setattr(db, "_effective_pool_settings", unavailable)
    report = guard.evaluate_release(evidence=safe_local_guard, safety_flags=SafetyFlags())
    assert not report.ok
    assert "private-fixture-detail" not in str(report.as_dict())


def test_public_status_retains_disabled_financial_state(monkeypatch, safe_local_guard):
    monkeypatch.setattr(guard.SafetyFlags, "from_env", lambda: SafetyFlags())
    status = guard.public_test_status(evidence=safe_local_guard)
    assert not status["auto_trading_enabled"]
    assert not status["copy_trading_enabled"]
    assert not status["real_payouts_enabled"]
    assert status["verdict"] == "LIMITED_PUBLIC_TEST_READY"
