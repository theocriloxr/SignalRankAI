from datetime import datetime, timedelta, timezone
import pytest

from scripts.soak_report import evaluate

NOW = datetime(2026, 10, 3, 20, tzinfo=timezone.utc)


def observations():
    return [{
        "observed_at": (NOW - timedelta(hours=24) + timedelta(minutes=5*i)).isoformat(),
        "release_sha": "a"*40, "source_sha256": "b"*64,
        "configuration_sha256": "c"*64, "schema_head": "0048_runtime_schema_bridge",
        "environment_id": "owned-monitor-environment",
        "deployment_ids": {"frontdoor": "owned-frontdoor", "engine": "owned-engine"},
        "safety_ok": True, "readiness_ok": True,
        "duplicate_deliveries": 0, "duplicate_orders": 0, "unhandled_errors": 0,
    } for i in range(289)]


def test_continuous_same_release_monitor_window_passes():
    result = evaluate(observations(), now=NOW)
    assert result["soak_passed"]
    assert result["hours_observed"] == 24


def test_claimed_hours_without_monitor_evidence_never_pass():
    assert not evaluate([{"hours": 72, "safety_ok": True}], now=NOW)["soak_passed"]


@pytest.mark.parametrize("defect", ["gap", "identity", "counter", "missing", "future", "stale", "unordered", "minimum"])
def test_incomplete_changed_or_unsafe_monitor_evidence_is_rejected(defect):
    samples = observations()
    kwargs = {"now": NOW}
    if defect == "gap": samples.pop(100)
    if defect == "identity": samples[100]["deployment_ids"] = {"engine": "replacement"}
    if defect == "counter": samples[100]["duplicate_orders"] = 1
    if defect == "missing": samples[100].pop("readiness_ok")
    if defect == "future": samples[-1]["observed_at"] = (NOW + timedelta(minutes=1)).isoformat()
    if defect == "stale": kwargs["now"] = NOW + timedelta(minutes=6)
    if defect == "unordered": samples[100], samples[101] = samples[101], samples[100]
    if defect == "minimum": kwargs["minimum_hours"] = 1
    assert not evaluate(samples, **kwargs)["soak_passed"]


@pytest.mark.parametrize("counter", [-1, True, float("nan"), "0", None])
def test_invalid_interval_counter_cannot_hide_failures(counter):
    samples = observations()
    samples[100]["unhandled_errors"] = counter
    assert not evaluate(samples, now=NOW)["soak_passed"]
