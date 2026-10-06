"""Health ownership and cache leases must fail closed during monitor outages."""
import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from engine.adaptive import lifecycle, profiles


@pytest.mark.parametrize("invalid", ["nan", "inf", "0", "301", "bad"])
def test_invalid_health_cadence_cannot_issue_an_approval(invalid, monkeypatch):
    monkeypatch.setenv("ADAPTIVE_HEALTH_INTERVAL_SECONDS", invalid)
    with pytest.raises(ValueError):
        lifecycle.approval_lease("profile")


def test_expired_cache_approval_cannot_survive_an_unavailable_monitor(monkeypatch):
    clock = [1000.0]
    monkeypatch.setattr(lifecycle.time, "time", lambda: clock[0])
    monkeypatch.setenv("ADAPTIVE_HEALTH_INTERVAL_SECONDS", "60")
    payload = {"profile_id": "approved", "asset": "BTCUSDT", "asset_class": "crypto", "state": "CANARY",
               "health_lease": lifecycle.approval_lease("approved")}
    cache = SimpleNamespace(get_sync=lambda key: json.dumps(payload))
    monkeypatch.setattr(profiles, "state", cache)
    resolver = profiles.ProfileResolver()
    assert resolver.resolve("BTCUSDT", "crypto").profile_id == "approved"
    # Model Redis/PG cache continuing to return old bytes after a monitor outage.
    clock[0] = 1150.0
    assert resolver.resolve("BTCUSDT", "crypto").metadata["neutral_fallback"] is True


@pytest.mark.parametrize("variant", ["missing", "nonfinite", "future", "wrong_profile", "wrong_asset", "unbounded"])
def test_unverifiable_cache_approvals_use_the_neutral_baseline(monkeypatch, variant):
    monkeypatch.setattr(lifecycle.time, "time", lambda: 1000.0)
    payload = {"profile_id": "approved", "asset": "BTCUSDT", "state": "CANARY",
               "health_lease": lifecycle.approval_lease("approved")}
    if variant == "missing":
        payload.pop("health_lease")
    elif variant == "nonfinite":
        payload["health_lease"]["expires_at"] = float("nan")
    elif variant == "future":
        payload["health_lease"]["issued_at"] = 1010.0
    elif variant == "wrong_profile":
        payload["health_lease"]["profile_id"] = "another"
    elif variant == "wrong_asset":
        payload["asset"] = "AAPL"
    elif variant == "unbounded":
        payload["health_lease"]["expires_at"] = 2000.0
    monkeypatch.setattr(profiles, "state", SimpleNamespace(get_sync=lambda key: json.dumps(payload)))
    assert profiles.ProfileResolver().resolve("BTCUSDT", "crypto").metadata["neutral_fallback"]


@pytest.mark.asyncio
@pytest.mark.parametrize("fails", [False, True])
async def test_health_loop_runs_with_optimization_disabled_and_preserves_failure_evidence(monkeypatch, fails):
    from engine.adaptive import learning
    from core import redis_state

    stop = asyncio.Event()
    writes = []
    async def monitor():
        stop.set()
        if fails:
            raise ConnectionError("synthetic database outage")
        return {"published": 2, "suspended_assets": [], "restored_profiles": []}
    check = AsyncMock(side_effect=monitor)
    monkeypatch.setenv("ADAPTIVE_OPTIMISATION_ENABLED", "0")
    monkeypatch.setenv("ADAPTIVE_HEALTH_INTERVAL_SECONDS", "15")
    monkeypatch.setattr(learning, "monitor_profile_health", check)
    monkeypatch.setattr(redis_state, "state", SimpleNamespace(
        get_sync=lambda key: "1", set_sync=lambda key, value, **kwargs: writes.append((key, json.loads(value)))))
    await lifecycle.profile_health_loop(stop)
    check.assert_awaited_once()
    assert writes[0][0] == "adaptive:health:last_check"
    assert writes[0][1]["status"] == ("ERROR" if fails else "COMPLETED")
    assert writes[0][1]["broker_fills_certified"] is False
    assert len(writes) == 1, "failed monitor must not issue profile cache approvals"


@pytest.mark.asyncio
async def test_analytics_owns_health_when_research_is_disabled(monkeypatch):
    from runtime import analytics

    for name in ("OPENAI_STARTUP_PROBE_ENABLED", "SHADOW_TRACKING_ENABLED", "ASSET_LEARNING_ENABLED",
                 "DYNAMIC_INSTRUMENT_DISCOVERY_ENABLED", "ML_DRIFT_MONITOR_ENABLED", "ANALYTICS_ML_TRAIN_ENABLED",
                 "LEARNING_HISTORY_RETENTION_ENABLED", "CONTINUOUS_IMPROVEMENT_REVIEW_ENABLED",
                 "ADAPTIVE_LEARNING_WORKER_ENABLED"):
        monkeypatch.setenv(name, "0")
    stop = asyncio.Event()
    async def monitor(event):
        assert event is stop
        event.set()
    health = AsyncMock(side_effect=monitor)
    research = AsyncMock()
    monkeypatch.setattr(lifecycle, "profile_health_loop", health)
    monkeypatch.setattr(lifecycle, "adaptive_learning_loop", research)
    await analytics.run_async(stop)
    health.assert_awaited_once()
    research.assert_not_awaited()


@pytest.mark.parametrize("status,age,expected", [("COMPLETED", 10, "COMPLETED"),
    ("ERROR", 10, "ERROR"), ("COMPLETED", 151, "STALE"), ("COMPLETED", -10, "STALE")])
def test_health_report_exposes_stale_and_failed_checks(monkeypatch, status, age, expected):
    monkeypatch.setattr(lifecycle.time, "time", lambda: 1000.0)
    report = {"checked_at_epoch": 1000 - age, "interval_seconds": 60, "status": status,
              "broker_fills_certified": True}
    result = lifecycle.health_monitor_snapshot(SimpleNamespace(get_sync=lambda _: json.dumps(report)))
    assert result["status"] == expected
    assert result["fresh"] == (expected != "STALE")
    assert result["broker_fills_certified"] is False


def test_cache_outage_cannot_approve_a_profile_or_crash_operator_diagnostics(monkeypatch):
    def unavailable(_):
        raise ConnectionError("synthetic cache outage")
    store = SimpleNamespace(get_sync=unavailable)
    monkeypatch.setattr(profiles, "state", store)
    assert profiles.ProfileResolver().resolve("BTCUSDT", "crypto").metadata["neutral_fallback"]
    assert lifecycle.health_monitor_snapshot(store)["status"] == "UNAVAILABLE"


@pytest.mark.asyncio
@pytest.mark.parametrize("failed_task", ["health", "research", "startup"])
async def test_analytics_cleans_up_and_exits_when_a_required_worker_fails(monkeypatch, failed_task):
    from runtime import analytics
    from engine import shadow_outcome_worker

    for name in ("OPENAI_STARTUP_PROBE_ENABLED", "SHADOW_TRACKING_ENABLED", "ASSET_LEARNING_ENABLED",
                 "DYNAMIC_INSTRUMENT_DISCOVERY_ENABLED", "ML_DRIFT_MONITOR_ENABLED", "ANALYTICS_ML_TRAIN_ENABLED",
                 "LEARNING_HISTORY_RETENTION_ENABLED", "CONTINUOUS_IMPROVEMENT_REVIEW_ENABLED"):
        monkeypatch.setenv(name, "0")
    monkeypatch.setenv("ADAPTIVE_LEARNING_WORKER_ENABLED", "1")
    cleaned = set()
    async def worker(stop, name):
        try:
            if name == failed_task:
                raise ConnectionError("synthetic worker outage")
            await stop.wait()
        finally:
            cleaned.add(name)
    monkeypatch.setattr(lifecycle, "profile_health_loop", lambda stop: worker(stop, "health"))
    monkeypatch.setattr(lifecycle, "adaptive_learning_loop", lambda stop: worker(stop, "research"))
    stop = asyncio.Event()
    if failed_task == "startup":
        async def broken_start():
            await asyncio.sleep(0)
            raise ConnectionError("synthetic startup outage")
        shadow = SimpleNamespace(start=AsyncMock(side_effect=broken_start), stop=AsyncMock())
        monkeypatch.setenv("SHADOW_TRACKING_ENABLED", "1")
        monkeypatch.setattr(shadow_outcome_worker, "shadow_outcome_worker", shadow)
    with pytest.raises((RuntimeError, ConnectionError)):
        await analytics.run_async(stop)
    assert stop.is_set()
    assert cleaned == {"health", "research"}
    if failed_task == "startup":
        shadow.stop.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("name,value", [("ADAPTIVE_DRIFT_MAX_BRIER", "nan"),
    ("ADAPTIVE_DRIFT_MAX_BRIER", "inf"), ("ADAPTIVE_DRIFT_MAX_BRIER", "1.1"),
    ("ADAPTIVE_DRIFT_MAX_DRAWDOWN_R", "nan"), ("ADAPTIVE_DRIFT_MIN_LIVE_SAMPLES", "251")])
async def test_invalid_health_thresholds_fail_before_querying_the_database(monkeypatch, name, value):
    from engine.adaptive import learning
    monkeypatch.setenv(name, value)
    database = SimpleNamespace(execute=AsyncMock())
    with pytest.raises(ValueError, match="invalid_adaptive_health_thresholds"):
        await learning._monitor_runtime_profiles(database)
    database.execute.assert_not_awaited()
