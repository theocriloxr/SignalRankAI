from __future__ import annotations

from unittest.mock import patch

import pytest

from core.resource_governor import (
    MemoryLimit,
    ResourceGovernor,
    ResourceInputs,
    ResourceState,
    ResourceThresholds,
    detect_memory_limit,
    policy_for_state,
)


def _memory_input(ratio: float) -> ResourceInputs:
    limit = 100 * 1024 * 1024
    return ResourceInputs(
        rss_bytes=int(limit * ratio),
        memory_limit_bytes=limit,
    )


def test_cgroup_memory_limit_detection_and_unlimited_fallback() -> None:
    with patch(
        "core.resource_governor._read_positive_int",
        side_effect=(384 * 1024 * 1024, 512 * 1024 * 1024),
    ):
        detected = detect_memory_limit(
            cgroup_paths=("memory.max", "memory.limit_in_bytes"),
            physical_memory_bytes=8 * 1024 * 1024 * 1024,
        )
    assert detected.bytes == 384 * 1024 * 1024
    assert detected.source == "cgroup_v2"

    with patch(
        "core.resource_governor._read_positive_int",
        side_effect=(None, None),
    ):
        fallback = detect_memory_limit(
            cgroup_paths=("memory.max", "memory.limit_in_bytes"),
            physical_memory_bytes=2 * 1024 * 1024 * 1024,
        )
    assert fallback.bytes == 2 * 1024 * 1024 * 1024
    assert fallback.source == "physical"


def test_explicit_memory_limit_wins_over_cgroup() -> None:
    detected = detect_memory_limit(
        explicit_mb=640,
        cgroup_paths=("memory.max",),
        physical_memory_bytes=8 * 1024 * 1024 * 1024,
    )
    assert detected == MemoryLimit(640 * 1024 * 1024, "explicit")


def test_invalid_environment_threshold_order_falls_back_safely() -> None:
    thresholds = ResourceThresholds.from_env(
        {
            "APP_MEMORY_SOFT_RATIO": "0.90",
            "APP_MEMORY_HARD_RATIO": "0.80",
            "APP_MEMORY_CRITICAL_RATIO": "0.70",
            "RESOURCE_DB_QUEUE_SOFT": "20",
            "RESOURCE_DB_QUEUE_HARD": "10",
            "RESOURCE_DB_QUEUE_CRITICAL": "5",
        }
    )
    assert (
        thresholds.memory_soft_ratio,
        thresholds.memory_hard_ratio,
        thresholds.memory_critical_ratio,
    ) == (0.72, 0.88, 0.96)
    assert (
        thresholds.db_queue_soft,
        thresholds.db_queue_hard,
        thresholds.db_queue_critical,
    ) == (2, 6, 12)


def test_state_escalation_is_immediate_and_recovery_is_hysteretic() -> None:
    thresholds = ResourceThresholds(recovery_samples=2, memory_recovery_margin_mb=1)
    governor = ResourceGovernor(
        thresholds,
        memory_limit=MemoryLimit(100 * 1024 * 1024, "test"),
    )

    assert governor.evaluate(_memory_input(0.20)).state is ResourceState.OPTIMAL
    assert governor.evaluate(_memory_input(0.75)).state is ResourceState.CONSERVATIVE
    assert governor.evaluate(_memory_input(0.90)).state is ResourceState.MINIMAL
    assert governor.evaluate(_memory_input(0.98)).state is ResourceState.CRITICAL

    assert governor.evaluate(_memory_input(0.20)).state is ResourceState.CRITICAL
    assert governor.evaluate(_memory_input(0.20)).state is ResourceState.MINIMAL
    assert governor.evaluate(_memory_input(0.20)).state is ResourceState.MINIMAL
    assert governor.evaluate(_memory_input(0.20)).state is ResourceState.CONSERVATIVE
    assert governor.evaluate(_memory_input(0.20)).state is ResourceState.CONSERVATIVE
    assert governor.evaluate(_memory_input(0.20)).state is ResourceState.OPTIMAL


@pytest.mark.parametrize(
    ("inputs", "expected"),
    (
        (ResourceInputs(cpu_percent=99.0), ResourceState.CRITICAL),
        (ResourceInputs(event_loop_lag_ms=600.0), ResourceState.MINIMAL),
        (ResourceInputs(db_admission_queue_depth=2), ResourceState.CONSERVATIVE),
        (ResourceInputs(db_admission_wait_ms=1_200.0), ResourceState.MINIMAL),
        (ResourceInputs(redis_latency_ms=1_200.0), ResourceState.CRITICAL),
        (
            ResourceInputs(delivery_queue_depth=850, delivery_queue_capacity=1_000),
            ResourceState.MINIMAL,
        ),
        (ResourceInputs(provider_error_rate=0.35), ResourceState.MINIMAL),
        (ResourceInputs(telegram_retry_after_rate=0.30), ResourceState.CRITICAL),
        (ResourceInputs(pending_task_count=350), ResourceState.MINIMAL),
    ),
)
def test_each_pressure_input_can_drive_state(
    inputs: ResourceInputs,
    expected: ResourceState,
) -> None:
    governor = ResourceGovernor(memory_limit=MemoryLimit(None, "unknown"))
    assert governor.evaluate(inputs).state is expected


def test_multiple_soft_breaches_escalate_to_minimal() -> None:
    governor = ResourceGovernor(memory_limit=MemoryLimit(None, "unknown"))
    snapshot = governor.evaluate(
        ResourceInputs(
            cpu_percent=80,
            event_loop_lag_ms=150,
            provider_error_rate=0.15,
        )
    )
    assert snapshot.state is ResourceState.MINIMAL
    assert len(snapshot.breaches) == 3


def test_critical_policy_fails_closed_but_preserves_truth_paths() -> None:
    policy = policy_for_state(ResourceState.CRITICAL)
    assert policy.real_execution_allowed is False
    assert policy.new_scans_enabled is False
    assert policy.heavy_jobs_enabled is False
    assert policy.track_existing_positions is True
    assert policy.telegram_commands_enabled is True
    assert policy.delivery_proof_enabled is True
    assert policy.lifecycle_tracking_enabled is True
    assert policy.kill_switch_enabled is True
    assert policy.payment_verification_enabled is True
    assert policy.health_endpoints_enabled is True


def test_snapshot_and_metrics_apis_are_serializable() -> None:
    governor = ResourceGovernor(memory_limit=MemoryLimit(None, "unknown"))
    snapshot = governor.evaluate(ResourceInputs(redis_latency_ms=75.0))
    payload = snapshot.as_dict()
    metrics = governor.metrics_snapshot()

    assert payload["state"] == "CONSERVATIVE"
    assert payload["pressure_values"]["redis_latency_ms"] == 75.0
    assert payload["policy"]["provider_concurrency_factor"] == 0.75
    assert metrics["evaluations_total"] == 1
    assert metrics["transitions_total"] == 1
    assert metrics["current_state"] == "CONSERVATIVE"


@pytest.mark.asyncio
async def test_async_sample_accepts_external_runtime_pressure() -> None:
    governor = ResourceGovernor(memory_limit=MemoryLimit(None, "unknown"))
    snapshot = await governor.sample(
        measure_loop_lag=False,
        event_loop_lag_ms=0.0,
        db_admission_queue_depth=0,
        redis_latency_ms=0.0,
        delivery_queue_depth=0,
        delivery_queue_capacity=100,
        provider_error_rate=0.0,
        telegram_retry_after_rate=0.0,
        pending_task_count=1,
        rss_bytes=1,
        memory_limit_bytes=100,
        cpu_percent=0.0,
    )
    assert snapshot.state is ResourceState.OPTIMAL
