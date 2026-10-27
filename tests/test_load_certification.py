from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from scripts.load_certification import (
    build_plan,
    evaluate_certification,
    merge_shard_reports,
    percentile,
)


def _profiles(tmp_path: Path) -> Path:
    path = tmp_path / "scale.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "profiles": {
                    "test": {
                        "registered_users": 100,
                        "concurrent_users": 10,
                        "required_soak_hours": 1,
                        "slos": {
                            "webhook_ack_p95_ms": 500,
                            "webhook_ack_p99_ms": 1000,
                            "notification_queue_age_p99_seconds": 60,
                            "projection_coverage_min": 0.999,
                            "duplicate_user_visible_deliveries": 0,
                            "duplicate_live_orders": 0,
                        },
                    }
                }
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    return path


def test_sharded_plan_allocates_every_concurrent_user_once(tmp_path: Path) -> None:
    profiles = _profiles(tmp_path)
    shares = [
        build_plan(
            profile="test",
            base_url="https://staging.example.test",
            paths=["/healthz"],
            shards=3,
            shard_index=index,
            duration_seconds=30,
            profiles_path=profiles,
        ).shard_concurrency
        for index in range(3)
    ]
    assert shares == [4, 3, 3]
    assert sum(shares) == 10


def test_load_plan_rejects_invalid_target_and_shard(tmp_path: Path) -> None:
    profiles = _profiles(tmp_path)
    with pytest.raises(ValueError, match="absolute_http_url"):
        build_plan(
            profile="test",
            base_url="localhost",
            paths=["/healthz"],
            shards=1,
            shard_index=0,
            duration_seconds=30,
            profiles_path=profiles,
        )
    with pytest.raises(ValueError, match="invalid_shard_index"):
        build_plan(
            profile="test",
            base_url="https://staging.example.test",
            paths=["/healthz"],
            shards=2,
            shard_index=2,
            duration_seconds=30,
            profiles_path=profiles,
        )


def test_percentile_uses_nearest_rank() -> None:
    values = [1, 2, 3, 4, 5, 100]
    assert percentile(values, 0.50) == 3
    assert percentile(values, 0.95) == 100
    assert percentile(values, 0.99) == 100
    assert percentile([], 0.95) is None


def _shard(index: int, *, p95: float, p99: float, requests: int = 100) -> dict:
    return {
        "profile": "test",
        "target": "https://staging.example.test",
        "shards": 2,
        "shard_index": index,
        "configured_total_concurrency": 10,
        "shard_concurrency": 5,
        "requests": requests,
        "errors": 0,
        "duration_seconds": 3600.0,
        "throughput_rps": 10.0,
        "latency_ms": {"p50": 20.0, "p95": p95, "p99": p99, "max": p99},
        "status_counts": {"200": requests},
    }


def test_merge_requires_complete_unique_shard_set() -> None:
    with pytest.raises(ValueError, match="incomplete_or_duplicate_shard_set"):
        merge_shard_reports([_shard(0, p95=100, p99=200)])

    merged = merge_shard_reports(
        [_shard(0, p95=100, p99=200), _shard(1, p95=150, p99=250)]
    )
    assert merged["requests"] == 200
    assert merged["latency_ms"]["p95_worst_shard"] == 150
    assert merged["latency_ms"]["p99_worst_shard"] == 250
    assert merged["throughput_rps"] == pytest.approx(200 / 3600)


def test_scale_certification_requires_every_profile_slo(tmp_path: Path) -> None:
    profiles = _profiles(tmp_path)
    merged = merge_shard_reports(
        [_shard(0, p95=100, p99=200), _shard(1, p95=110, p99=210)]
    )
    incomplete = evaluate_certification(
        merged,
        {"webhook_ack_p95_ms": 100},
        profiles_path=profiles,
    )
    assert incomplete["status"] == "BLOCKED"
    assert incomplete["claim_allowed"] is False
    assert "projection_coverage_min" in incomplete["missing_slos"]


def test_scale_certification_passes_only_when_all_slos_and_concurrency_pass(
    tmp_path: Path,
) -> None:
    profiles = _profiles(tmp_path)
    merged = merge_shard_reports(
        [_shard(0, p95=100, p99=200), _shard(1, p95=110, p99=210)]
    )
    metrics = {
        "webhook_ack_p95_ms": 100,
        "webhook_ack_p99_ms": 250,
        "notification_queue_age_p99_seconds": 10,
        "projection_coverage_min": 0.9995,
        "duplicate_user_visible_deliveries": 0,
        "duplicate_live_orders": 0,
    }
    passed = evaluate_certification(merged, metrics, profiles_path=profiles)
    assert passed["status"] == "PASS"
    assert passed["claim_allowed"] is True
    assert passed["missing_slos"] == []
    assert passed["failed_slos"] == []

    metrics["duplicate_live_orders"] = 1
    failed = evaluate_certification(merged, metrics, profiles_path=profiles)
    assert failed["status"] == "BLOCKED"
    assert failed["claim_allowed"] is False
    assert "duplicate_live_orders" in failed["failed_slos"]


def test_large_scale_profile_is_100k_and_20k_concurrent() -> None:
    plan = build_plan(
        profile="large_scale",
        base_url="https://signalrankai-staging.up.railway.app",
        paths=["/healthz"],
        shards=32,
        shard_index=0,
        duration_seconds=60,
    )
    assert plan.registered_users == 100000
    assert plan.total_concurrency == 20000
    assert plan.shards == 32
    assert plan.shard_concurrency == 625


def _metrics():
    return {"webhook_ack_p95_ms": 100, "webhook_ack_p99_ms": 250,
            "notification_queue_age_p99_seconds": 10, "projection_coverage_min": 0.9995,
            "duplicate_user_visible_deliveries": 0, "duplicate_live_orders": 0}


@pytest.mark.parametrize("defect", ["duration", "errors", "throttle", "empty", "nan", "counter_mismatch"])
def test_load_cannot_certify_failed_short_or_malformed_traffic(tmp_path, defect):
    merged = merge_shard_reports([_shard(0, p95=100, p99=200), _shard(1, p95=100, p99=200)])
    if defect == "duration": merged["duration_seconds"] = 10
    if defect == "errors": merged["errors"] = 1
    if defect == "throttle": merged["status_counts"] = {"429": 200}
    if defect == "empty": merged["requests"] = 0
    if defect == "nan": merged["duration_seconds"] = float("nan")
    if defect == "counter_mismatch": merged["status_counts"] = {"200": 1}
    result = evaluate_certification(merged, _metrics(), profiles_path=_profiles(tmp_path))
    assert result["status"] == "BLOCKED"
    assert result["claim_allowed"] is False


@pytest.mark.parametrize("value", [-1, float("nan"), float("inf"), True, "100", None])
def test_invalid_slo_measurement_never_passes(tmp_path, value):
    merged = merge_shard_reports([_shard(0, p95=100, p99=200), _shard(1, p95=100, p99=200)])
    metrics = _metrics(); metrics["webhook_ack_p95_ms"] = value
    assert not evaluate_certification(merged, metrics, profiles_path=_profiles(tmp_path))["claim_allowed"]


@pytest.mark.parametrize("defect", ["concurrency", "share", "duration", "requests", "status", "latency"])
def test_incompatible_or_invalid_shards_are_rejected(defect):
    reports = [_shard(0, p95=100, p99=200), _shard(1, p95=100, p99=200)]
    if defect == "concurrency": reports[1]["configured_total_concurrency"] = 10000
    if defect == "share": reports[1]["shard_concurrency"] = 1
    if defect == "duration": reports[1]["duration_seconds"] = float("inf")
    if defect == "requests": reports[1]["requests"] = -1
    if defect == "status": reports[1]["status_counts"] = {"200": -100}
    if defect == "latency": reports[1]["latency_ms"]["p95"] = float("nan")
    with pytest.raises(ValueError): merge_shard_reports(reports)


def test_default_plan_converts_profile_soak_hours_to_seconds(tmp_path):
    plan = build_plan(profile="test", base_url="https://owned.example.test", paths=["/healthz"],
                      shards=1, shard_index=0, profiles_path=_profiles(tmp_path))
    assert plan.duration_seconds == 3600


@pytest.mark.asyncio
async def test_rate_limited_http_response_is_a_load_error():
    import time
    import httpx
    from scripts.load_certification import _worker
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(429))) as client:
        result = await _worker(client, base_url="https://owned.example.test", paths=("/healthz",),
                               stop_at=time.monotonic()+0.01, worker_id=0, timeout_seconds=1)
    assert result["requests"] > 0
    assert result["errors"] == result["requests"]
