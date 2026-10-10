"""Baseline provenance, forward separation, governed limits and missing evidence."""
from dataclasses import asdict, replace
from datetime import datetime, timedelta, timezone

import pytest

from engine.adaptive.health_baselines import (HealthConditions, SCOPE, CONDITIONS_VERSION,
    _hash, profile_hash, build_baseline_payload, baseline_valid, compare_health_baseline)


def limits(**changes):
    policy = HealthConditions(30, 0.20, 5.0, 15, 0.50, 0.10, False)
    return replace(policy, **changes)


def observations(count=100, *, start=None, values=None, probability=None, version="fixture-calibration"):
    start = start or datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=10)
    return [{"signal_id": f"observation-{i:03d}", "created_at": start + timedelta(minutes=i * 2),
        "closed_at": start + timedelta(minutes=i * 2 + 1), "r_multiple": values[i] if values is not None else (1.0 if i % 2 else -0.5),
        "ml_calibration_validated": probability is not None, "ml_probability_calibrated": probability,
        "ml_calibration_version": version, "ml_calibration_validation_rows": 250,
        "ml_calibration_brier": 0.16, "ml_calibration_ece": 0.04} for i in range(count)]


def approved(conditions=None):
    identity = {"profile_id": "fixture-profile", "asset": "BTCUSDT", "asset_class": "crypto", "version": 1}
    payload = build_baseline_payload(observations(), conditions or limits())
    baseline = {"baseline_id": "fixture-baseline", "profile_id": identity["profile_id"], "profile_version": 1,
        "profile_hash": profile_hash(identity), "approved_by": 42,
        "approved_at": datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=7),
        "evidence_scope": SCOPE, "conditions_version": CONDITIONS_VERSION, "payload": payload,
        "content_hash": _hash(payload)}
    assert baseline_valid(baseline, identity)
    return baseline, identity


def forward(count=30, **kwargs):
    return observations(count, start=datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=2), **kwargs)


@pytest.mark.parametrize("field,value", [("minimum_live_samples", True), ("minimum_live_samples", 251),
    ("minimum_live_samples", 19), ("maximum_drawdown_r", float("nan")), ("maximum_drawdown_r", 0),
    ("maximum_expectancy_decay_r", -1), ("maximum_profit_factor_decay_fraction", 1.1),
    ("maximum_brier_increase", float("inf")), ("calibration_required", "yes"),
    ("maximum_drawdown_duration_observations", 0)])
def test_owner_conditions_reject_invalid_limits(field, value):
    with pytest.raises(ValueError):
        limits(**{field: value})


@pytest.mark.parametrize("mode", ["small", "duplicate", "nonfinite", "no_losses", "negative", "backwards"])
def test_baseline_approval_cannot_manufacture_qualification(mode):
    rows = observations(99 if mode == "small" else 100)
    if mode == "duplicate":
        rows[1]["signal_id"] = rows[0]["signal_id"]
    elif mode == "nonfinite":
        rows[0]["r_multiple"] = float("inf")
    elif mode in {"no_losses", "negative"}:
        for row in rows:
            row["r_multiple"] = 1 if mode == "no_losses" else -1
    elif mode == "backwards":
        rows[0]["closed_at"] = rows[0]["created_at"] - timedelta(minutes=1)
    with pytest.raises(ValueError):
        build_baseline_payload(rows, limits())


@pytest.mark.parametrize("change", ["version", "asset", "weights", "payload", "scope", "condition_version", "future_approval"])
def test_unverified_or_changed_baselines_never_compare_as_passing(change):
    baseline, identity = approved()
    if change in {"version", "asset", "weights"}:
        identity[{"version": "version", "asset": "asset", "weights": "family_weights"}[change]] = 2 if change == "version" else "OTHER" if change == "asset" else {"trend": 1.15}
    elif change == "payload":
        baseline["payload"]["metrics"]["expectancy_r"] = 10
    elif change == "scope":
        baseline["evidence_scope"] = "broker_fills"
    elif change == "condition_version":
        baseline["conditions_version"] = "unknown"
    else:
        baseline["approved_at"] = datetime.now(timezone.utc) + timedelta(days=1)
    assert not baseline_valid(baseline, identity)
    assert compare_health_baseline(baseline, identity, forward())["approved_baseline_comparison"] == "INVALID"


def test_approved_delivery_limits_do_not_annualize_trade_r_or_certify_broker_fills():
    baseline, identity = approved()
    result = compare_health_baseline(baseline, identity, forward())
    assert result["approved_baseline_comparison"] == "WITHIN_LIMITS"
    assert result["live_comparison_metrics"]["annualized_sharpe"] is None
    assert result["live_comparison_metrics"]["max_drawdown_r"] == 0.5
    assert result["broker_fills_certified"] is False
    assert "fill_rate" in baseline["payload"]["unavailable_metrics"]


def test_decisions_before_approval_cannot_supply_forward_evidence_even_when_closed_after():
    baseline, identity = approved()
    rows = observations()
    for row in rows:
        row["closed_at"] = baseline["approved_at"] + timedelta(days=1)
    result = compare_health_baseline(baseline, identity, rows + forward(29))
    assert result["approved_baseline_comparison"] == "INSUFFICIENT"
    assert result["baseline_sample_size"] == 29
    assert result["live_comparison_metrics"] is None


def test_fixed_owner_limits_detect_decay_without_universal_sharpe_or_drawdown_multipliers():
    baseline, identity = approved()
    result = compare_health_baseline(baseline, identity, forward(values=[-0.5] * 30))
    assert result["approved_baseline_comparison"] == "BREACHED"
    assert set(result["baseline_reasons"]) == {"EXPECTANCY_DECAY", "DRAWDOWN_EXCEEDED", "DRAWDOWN_DURATION_EXCEEDED", "PROFIT_FACTOR_DECAY"}


def test_calibration_requirement_needs_qualified_baseline_evidence():
    with pytest.raises(ValueError, match="qualified_baseline_calibration_required"):
        build_baseline_payload(observations(), limits(calibration_required=True))


def test_good_calibration_version_cannot_hide_missing_forward_version_coverage():
    baseline, identity = approved()
    conditions = limits(calibration_required=True)
    baseline["payload"] = build_baseline_payload(observations(probability=0.5), conditions)
    baseline["content_hash"] = _hash(baseline["payload"])
    good = forward(30, probability=0.5)
    small = forward(2, probability=0.01, version="new-unqualified")
    for row in small:
        row["signal_id"] += "-new"
    result = compare_health_baseline(baseline, identity, good + small)
    assert result["approved_baseline_comparison"] == "UNAVAILABLE"
    assert "CALIBRATION_COVERAGE_UNAVAILABLE" in result["baseline_reasons"]


def calibrated_rows(count, *, version, error, live=False):
    rows = forward(count, probability=0.5, version=version) if live else observations(count, probability=0.5, version=version)
    for row in rows:
        row["signal_id"] += "-" + version
        row["ml_probability_calibrated"] = 1 - error if row["r_multiple"] > 0 else error
    return rows


def test_calibration_decay_compares_matching_versions_instead_of_worst_to_worst():
    baseline, identity = approved()
    baseline["payload"] = build_baseline_payload(calibrated_rows(100, version="a", error=0.4) +
        calibrated_rows(100, version="b", error=0.1), limits(calibration_required=True))
    baseline["content_hash"] = _hash(baseline["payload"])
    result = compare_health_baseline(baseline, identity, calibrated_rows(30, version="a", error=0.3, live=True) +
        calibrated_rows(30, version="b", error=0.4, live=True))
    assert result["approved_baseline_comparison"] == "BREACHED"
    assert "CALIBRATION_DECAY" in result["baseline_reasons"]
    assert result["live_comparison_metrics"]["brier_score"] == pytest.approx(baseline["payload"]["metrics"]["brier_score"])


def test_qualified_new_calibrator_cannot_borrow_another_versions_approved_baseline():
    baseline, identity = approved()
    baseline["payload"] = build_baseline_payload(calibrated_rows(100, version="approved", error=0.4), limits(calibration_required=True))
    baseline["content_hash"] = _hash(baseline["payload"])
    result = compare_health_baseline(baseline, identity, calibrated_rows(30, version="new", error=0.2, live=True))
    assert result["approved_baseline_comparison"] == "UNAVAILABLE"
    assert "CALIBRATION_BASELINE_VERSION_MISSING" in result["baseline_reasons"]


def test_missing_baseline_is_missing_evidence_and_not_a_fabricated_loss():
    report = compare_health_baseline(None, {}, [])
    assert report["approved_baseline_comparison"] == "UNAVAILABLE"
    assert report["baseline_metrics"] is None and report["live_comparison_metrics"] is None


def test_missing_profit_factor_does_not_become_a_passing_numeric_comparison():
    baseline, identity = approved()
    result = compare_health_baseline(baseline, identity, forward(values=[1.0] * 30))
    assert result["approved_baseline_comparison"] == "UNAVAILABLE"
    assert result["baseline_checks"]["PROFIT_FACTOR_DECAY"] is None
    assert result["live_comparison_metrics"]["profit_factor"] is None
    assert "PROFIT_FACTOR_UNDEFINED_NO_LOSSES" in result["baseline_reasons"]


@pytest.mark.parametrize("age,expected", [(0, True), (149, True), (151, False), (-10, False)])
def test_publication_requires_a_fresh_and_plausible_surveillance_receipt(monkeypatch, age, expected):
    from engine.adaptive.repository import _health_receipt_fresh
    monkeypatch.setenv("ADAPTIVE_HEALTH_INTERVAL_SECONDS", "60")
    assert _health_receipt_fresh(datetime.now(timezone.utc) - timedelta(seconds=age)) is expected
    assert not _health_receipt_fresh(None)


@pytest.mark.asyncio
@pytest.mark.parametrize("tier", ["free", "pro", "ADMIN"])
async def test_only_owner_can_approve_and_customer_cannot_read_baselines(monkeypatch, tier):
    from fastapi import HTTPException
    from web import platform_api
    async def forbidden(**kwargs):
        pytest.fail("unauthorized request reached the database")
    monkeypatch.setattr(platform_api, "get_session", forbidden)
    payload = platform_api.OperatorHealthBaselineRequest(profile_id="fixture", profile_version=1,
        conditions=asdict(limits()), confirm=True)
    with pytest.raises(HTTPException) as error:
        await platform_api.operator_approve_health_baseline(payload, {"tier": tier, "id": 42})
    assert error.value.status_code == 403
    if tier != "ADMIN":
        with pytest.raises(HTTPException) as error:
            await platform_api.operator_health_baseline("fixture", {"tier": tier})
        assert error.value.status_code == 403


@pytest.mark.asyncio
async def test_owner_approval_requires_explicit_confirmation_before_database_access(monkeypatch):
    from fastapi import HTTPException
    from web import platform_api
    payload = platform_api.OperatorHealthBaselineRequest(profile_id="fixture", profile_version=1,
        conditions=asdict(limits()))
    with pytest.raises(HTTPException) as error:
        await platform_api.operator_approve_health_baseline(payload, {"tier": "OWNER", "id": 42})
    assert error.value.status_code == 422
