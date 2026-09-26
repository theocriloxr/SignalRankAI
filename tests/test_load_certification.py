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
        "requests": requests,
        "errors": 0,
        "duration_seconds": 10.0,
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
    assert merged["throughput_rps"] == 20.0


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
