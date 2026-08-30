"""Bounded resource-pressure governor for the Railway monolith.

The governor is deliberately independent from the application entrypoint.  A
runtime owner can feed it measured DB, Redis, delivery, provider and Telegram
pressure without importing those subsystems here.  Process memory/CPU,
event-loop lag and pending-task count can be sampled directly.

Escalation is immediate.  Recovery is intentionally slower: pressure must stay
below a hysteresis boundary for a configurable number of observations, and the
state then recovers by at most one level per observation window.
"""

from __future__ import annotations

import asyncio
import ctypes
import os
import sys
import threading
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Mapping, Sequence

try:  # Prometheus is optional for local scripts and minimal test images.
    from prometheus_client import Counter, Gauge

    _RESOURCE_STATE_GAUGE = Gauge(
        "signalrank_resource_state",
        "Current resource-governor state (one label is 1, the others are 0)",
        ("state",),
    )
    _RESOURCE_PRESSURE_GAUGE = Gauge(
        "signalrank_resource_pressure_value",
        "Latest normalized or native resource-pressure value",
        ("metric",),
    )
    _RESOURCE_TRANSITIONS = Counter(
        "signalrank_resource_transitions_total",
        "Resource-governor state transitions",
        ("from_state", "to_state"),
    )
except (ImportError, ValueError):  # duplicate registry on reload is harmless
    _RESOURCE_STATE_GAUGE = None
    _RESOURCE_PRESSURE_GAUGE = None
    _RESOURCE_TRANSITIONS = None


MiB = 1024 * 1024


class ResourceState(str, Enum):
    OPTIMAL = "OPTIMAL"
    CONSERVATIVE = "CONSERVATIVE"
    MINIMAL = "MINIMAL"
    CRITICAL = "CRITICAL"


_STATE_LEVEL = {
    ResourceState.OPTIMAL: 0,
    ResourceState.CONSERVATIVE: 1,
    ResourceState.MINIMAL: 2,
    ResourceState.CRITICAL: 3,
}
_LEVEL_STATE = {value: key for key, value in _STATE_LEVEL.items()}


def _float_env(
    environ: Mapping[str, str],
    name: str,
    default: float,
    *,
    minimum: float = 0.0,
    maximum: float | None = None,
) -> float:
    try:
        value = float(environ.get(name, str(default)))
    except (TypeError, ValueError):
        value = float(default)
    value = max(float(minimum), value)
    if maximum is not None:
        value = min(float(maximum), value)
    return value


def _int_env(
    environ: Mapping[str, str],
    name: str,
    default: int,
    *,
    minimum: int = 0,
    maximum: int | None = None,
) -> int:
    try:
        value = int(float(environ.get(name, str(default))))
    except (TypeError, ValueError):
        value = int(default)
    value = max(int(minimum), value)
    if maximum is not None:
        value = min(int(maximum), value)
    return value


def _ordered_triplet(
    soft: float,
    hard: float,
    critical: float,
    defaults: tuple[float, float, float],
) -> tuple[float, float, float]:
    if soft < hard < critical:
        return soft, hard, critical
    return defaults


@dataclass(frozen=True, slots=True)
class ResourceThresholds:
    """All thresholds are configurable and have conservative Hobby defaults."""

    explicit_memory_limit_mb: int = 0
    memory_soft_ratio: float = 0.72
    memory_hard_ratio: float = 0.88
    memory_critical_ratio: float = 0.96
    memory_recovery_margin_mb: int = 32

    cpu_soft_percent: float = 75.0
    cpu_hard_percent: float = 90.0
    cpu_critical_percent: float = 98.0
    event_loop_soft_ms: float = 100.0
    event_loop_hard_ms: float = 500.0
    event_loop_critical_ms: float = 2_000.0

    db_queue_soft: int = 2
    db_queue_hard: int = 6
    db_queue_critical: int = 12
    db_wait_soft_ms: float = 250.0
    db_wait_hard_ms: float = 1_000.0
    db_wait_critical_ms: float = 5_000.0

    redis_soft_ms: float = 50.0
    redis_hard_ms: float = 200.0
    redis_critical_ms: float = 1_000.0
    delivery_queue_soft_ratio: float = 0.60
    delivery_queue_hard_ratio: float = 0.80
    delivery_queue_critical_ratio: float = 0.95
    delivery_queue_soft_depth: int = 1_000
    delivery_queue_hard_depth: int = 3_000
    delivery_queue_critical_depth: int = 4_500

    provider_error_soft_ratio: float = 0.10
    provider_error_hard_ratio: float = 0.30
    provider_error_critical_ratio: float = 0.60
    retry_after_soft_ratio: float = 0.02
    retry_after_hard_ratio: float = 0.10
    retry_after_critical_ratio: float = 0.25
    pending_tasks_soft: int = 100
    pending_tasks_hard: int = 300
    pending_tasks_critical: int = 1_000

    recovery_samples: int = 3
    recovery_hysteresis_ratio: float = 0.10
    soft_breaches_for_minimal: int = 3
    hard_breaches_for_critical: int = 3

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> "ResourceThresholds":
        env = os.environ if environ is None else environ

        memory = _ordered_triplet(
            _float_env(env, "APP_MEMORY_SOFT_RATIO", 0.72, maximum=0.99),
            _float_env(env, "APP_MEMORY_HARD_RATIO", 0.88, maximum=0.995),
            _float_env(env, "APP_MEMORY_CRITICAL_RATIO", 0.96, maximum=1.0),
            (0.72, 0.88, 0.96),
        )
        cpu = _ordered_triplet(
            _float_env(env, "RESOURCE_CPU_SOFT_PERCENT", 75.0, maximum=100.0),
            _float_env(env, "RESOURCE_CPU_HARD_PERCENT", 90.0, maximum=100.0),
            _float_env(env, "RESOURCE_CPU_CRITICAL_PERCENT", 98.0, maximum=100.0),
            (75.0, 90.0, 98.0),
        )
        loop_lag = _ordered_triplet(
            _float_env(env, "RESOURCE_EVENT_LOOP_SOFT_MS", 100.0),
            _float_env(env, "RESOURCE_EVENT_LOOP_HARD_MS", 500.0),
            _float_env(env, "RESOURCE_EVENT_LOOP_CRITICAL_MS", 2_000.0),
            (100.0, 500.0, 2_000.0),
        )
        db_wait = _ordered_triplet(
            _float_env(env, "RESOURCE_DB_WAIT_SOFT_MS", 250.0),
            _float_env(env, "RESOURCE_DB_WAIT_HARD_MS", 1_000.0),
            _float_env(env, "RESOURCE_DB_WAIT_CRITICAL_MS", 5_000.0),
            (250.0, 1_000.0, 5_000.0),
        )
        redis = _ordered_triplet(
            _float_env(env, "RESOURCE_REDIS_SOFT_MS", 50.0),
            _float_env(env, "RESOURCE_REDIS_HARD_MS", 200.0),
            _float_env(env, "RESOURCE_REDIS_CRITICAL_MS", 1_000.0),
            (50.0, 200.0, 1_000.0),
        )
        queue_ratio = _ordered_triplet(
            _float_env(env, "RESOURCE_DELIVERY_QUEUE_SOFT_RATIO", 0.60, maximum=1.0),
            _float_env(env, "RESOURCE_DELIVERY_QUEUE_HARD_RATIO", 0.80, maximum=1.0),
            _float_env(env, "RESOURCE_DELIVERY_QUEUE_CRITICAL_RATIO", 0.95, maximum=1.0),
            (0.60, 0.80, 0.95),
        )
        provider = _ordered_triplet(
            _float_env(env, "RESOURCE_PROVIDER_ERROR_SOFT_RATIO", 0.10, maximum=1.0),
            _float_env(env, "RESOURCE_PROVIDER_ERROR_HARD_RATIO", 0.30, maximum=1.0),
            _float_env(env, "RESOURCE_PROVIDER_ERROR_CRITICAL_RATIO", 0.60, maximum=1.0),
            (0.10, 0.30, 0.60),
        )
        retry_after = _ordered_triplet(
            _float_env(env, "RESOURCE_RETRY_AFTER_SOFT_RATIO", 0.02, maximum=1.0),
            _float_env(env, "RESOURCE_RETRY_AFTER_HARD_RATIO", 0.10, maximum=1.0),
            _float_env(env, "RESOURCE_RETRY_AFTER_CRITICAL_RATIO", 0.25, maximum=1.0),
            (0.02, 0.10, 0.25),
        )
        db_queue = _ordered_triplet(
            float(_int_env(env, "RESOURCE_DB_QUEUE_SOFT", 2)),
            float(_int_env(env, "RESOURCE_DB_QUEUE_HARD", 6)),
            float(_int_env(env, "RESOURCE_DB_QUEUE_CRITICAL", 12)),
            (2.0, 6.0, 12.0),
        )
        delivery_depth = _ordered_triplet(
            float(_int_env(env, "RESOURCE_DELIVERY_QUEUE_SOFT_DEPTH", 1_000)),
            float(_int_env(env, "RESOURCE_DELIVERY_QUEUE_HARD_DEPTH", 3_000)),
            float(_int_env(env, "RESOURCE_DELIVERY_QUEUE_CRITICAL_DEPTH", 4_500)),
            (1_000.0, 3_000.0, 4_500.0),
        )
        pending_tasks = _ordered_triplet(
            float(_int_env(env, "RESOURCE_PENDING_TASKS_SOFT", 100)),
            float(_int_env(env, "RESOURCE_PENDING_TASKS_HARD", 300)),
            float(_int_env(env, "RESOURCE_PENDING_TASKS_CRITICAL", 1_000)),
            (100.0, 300.0, 1_000.0),
        )

        return cls(
            explicit_memory_limit_mb=_int_env(env, "APP_MEMORY_LIMIT_MB", 0),
            memory_soft_ratio=memory[0],
            memory_hard_ratio=memory[1],
            memory_critical_ratio=memory[2],
            memory_recovery_margin_mb=_int_env(env, "APP_MEMORY_RECOVERY_MARGIN_MB", 32),
            cpu_soft_percent=cpu[0],
            cpu_hard_percent=cpu[1],
            cpu_critical_percent=cpu[2],
            event_loop_soft_ms=loop_lag[0],
            event_loop_hard_ms=loop_lag[1],
            event_loop_critical_ms=loop_lag[2],
            db_queue_soft=int(db_queue[0]),
            db_queue_hard=int(db_queue[1]),
            db_queue_critical=int(db_queue[2]),
            db_wait_soft_ms=db_wait[0],
            db_wait_hard_ms=db_wait[1],
            db_wait_critical_ms=db_wait[2],
            redis_soft_ms=redis[0],
            redis_hard_ms=redis[1],
            redis_critical_ms=redis[2],
            delivery_queue_soft_ratio=queue_ratio[0],
            delivery_queue_hard_ratio=queue_ratio[1],
            delivery_queue_critical_ratio=queue_ratio[2],
            delivery_queue_soft_depth=int(delivery_depth[0]),
            delivery_queue_hard_depth=int(delivery_depth[1]),
            delivery_queue_critical_depth=int(delivery_depth[2]),
            provider_error_soft_ratio=provider[0],
            provider_error_hard_ratio=provider[1],
            provider_error_critical_ratio=provider[2],
            retry_after_soft_ratio=retry_after[0],
            retry_after_hard_ratio=retry_after[1],
            retry_after_critical_ratio=retry_after[2],
            pending_tasks_soft=int(pending_tasks[0]),
            pending_tasks_hard=int(pending_tasks[1]),
            pending_tasks_critical=int(pending_tasks[2]),
            recovery_samples=_int_env(env, "RESOURCE_RECOVERY_SAMPLES", 3, minimum=1, maximum=100),
            recovery_hysteresis_ratio=_float_env(
                env,
                "RESOURCE_RECOVERY_HYSTERESIS_RATIO",
                0.10,
                maximum=0.50,
            ),
            soft_breaches_for_minimal=_int_env(
                env,
                "RESOURCE_SOFT_BREACHES_FOR_MINIMAL",
                3,
                minimum=1,
                maximum=20,
            ),
            hard_breaches_for_critical=_int_env(
                env,
                "RESOURCE_HARD_BREACHES_FOR_CRITICAL",
                3,
                minimum=1,
                maximum=20,
            ),
        )


@dataclass(frozen=True, slots=True)
class MemoryLimit:
    bytes: int | None
    source: str

    @property
    def mb(self) -> float | None:
        return None if self.bytes is None else round(self.bytes / MiB, 3)


def _read_positive_int(path: Path) -> int | None:
    try:
        raw = path.read_text(encoding="ascii", errors="ignore").strip().lower()
        if not raw or raw == "max":
            return None
        value = int(raw)
        # cgroup v1 can expose a near-int64 sentinel for "unlimited".
        if value <= 0 or value >= (1 << 60):
            return None
        return value
    except (OSError, TypeError, ValueError):
        return None


def _physical_memory_bytes() -> int | None:
    if sys.platform == "win32":
        class _MemoryStatus(ctypes.Structure):
            _fields_ = [
                ("dwLength", ctypes.c_ulong),
                ("dwMemoryLoad", ctypes.c_ulong),
                ("ullTotalPhys", ctypes.c_ulonglong),
                ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong),
                ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong),
                ("ullAvailVirtual", ctypes.c_ulonglong),
                ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
            ]

        try:
            status = _MemoryStatus()
            status.dwLength = ctypes.sizeof(_MemoryStatus)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):  # type: ignore[attr-defined]
                return int(status.ullTotalPhys)
        except (AttributeError, OSError, ValueError):
            return None
    try:
        page_size = int(os.sysconf("SC_PAGE_SIZE"))
        pages = int(os.sysconf("SC_PHYS_PAGES"))
        value = page_size * pages
        return value if value > 0 else None
    except (AttributeError, OSError, TypeError, ValueError):
        return None


def detect_memory_limit(
    *,
    explicit_mb: int | float | None = None,
    cgroup_paths: Sequence[str | Path] | None = None,
    physical_memory_bytes: int | None = None,
) -> MemoryLimit:
    """Resolve the effective memory ceiling without assuming a 512 MB plan.

    Resolution order is explicit override, finite cgroup v2/v1 limit, then host
    physical memory.  When both a cgroup and host value exist, the smaller
    finite value is used.
    """

    try:
        explicit_bytes = int(float(explicit_mb or 0) * MiB)
    except (TypeError, ValueError):
        explicit_bytes = 0
    if explicit_bytes > 0:
        return MemoryLimit(explicit_bytes, "explicit")

    paths = tuple(cgroup_paths or (
        Path("/sys/fs/cgroup/memory.max"),
        Path("/sys/fs/cgroup/memory/memory.limit_in_bytes"),
    ))
    physical = physical_memory_bytes if physical_memory_bytes is not None else _physical_memory_bytes()
    candidates: list[tuple[int, str]] = []
    for index, raw_path in enumerate(paths):
        value = _read_positive_int(Path(raw_path))
        if value is not None:
            source = "cgroup_v2" if index == 0 else "cgroup_v1"
            candidates.append((value, source))

    if candidates:
        limit, source = min(candidates, key=lambda item: item[0])
        if physical and physical > 0 and physical < limit:
            return MemoryLimit(int(physical), "physical")
        return MemoryLimit(int(limit), source)
    if physical and physical > 0:
        return MemoryLimit(int(physical), "physical")
    return MemoryLimit(None, "unknown")


def detect_memory_limit_bytes(
    explicit_mb: int | float | None = None,
    *,
    cgroup_paths: Sequence[str | Path] | None = None,
    physical_memory_bytes: int | None = None,
) -> int | None:
    return detect_memory_limit(
        explicit_mb=explicit_mb,
        cgroup_paths=cgroup_paths,
        physical_memory_bytes=physical_memory_bytes,
    ).bytes


def read_process_rss_bytes() -> int | None:
    """Best-effort current resident set size using only the standard library."""

    if sys.platform.startswith("linux"):
        try:
            for line in Path("/proc/self/status").read_text(
                encoding="ascii",
                errors="ignore",
            ).splitlines():
                if line.startswith("VmRSS:"):
                    return int(line.split()[1]) * 1024
        except (OSError, IndexError, TypeError, ValueError):
            pass
    if sys.platform == "win32":
        class _ProcessMemoryCounters(ctypes.Structure):
            _fields_ = [
                ("cb", ctypes.c_ulong),
                ("PageFaultCount", ctypes.c_ulong),
                ("PeakWorkingSetSize", ctypes.c_size_t),
                ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t),
                ("PeakPagefileUsage", ctypes.c_size_t),
            ]

        try:
            counters = _ProcessMemoryCounters()
            counters.cb = ctypes.sizeof(counters)
            handle = ctypes.windll.kernel32.GetCurrentProcess()  # type: ignore[attr-defined]
            ok = ctypes.windll.psapi.GetProcessMemoryInfo(  # type: ignore[attr-defined]
                handle,
                ctypes.byref(counters),
                counters.cb,
            )
            if ok:
                return int(counters.WorkingSetSize)
        except (AttributeError, OSError, ValueError):
            pass
    try:
        import resource

        rss = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
        return rss if sys.platform == "darwin" else rss * 1024
    except (ImportError, OSError, TypeError, ValueError):
        return None


async def measure_event_loop_lag_ms(delay_seconds: float = 0.05) -> float:
    delay = min(1.0, max(0.001, float(delay_seconds)))
    loop = asyncio.get_running_loop()
    started = loop.time()
    await asyncio.sleep(delay)
    return max(0.0, (loop.time() - started - delay) * 1_000.0)


@dataclass(frozen=True, slots=True)
class ResourceInputs:
    rss_bytes: int | None = None
    memory_limit_bytes: int | None = None
    cpu_percent: float | None = None
    event_loop_lag_ms: float | None = None
    db_admission_queue_depth: int | None = None
    db_admission_wait_ms: float | None = None
    redis_latency_ms: float | None = None
    delivery_queue_depth: int | None = None
    delivery_queue_capacity: int | None = None
    provider_error_rate: float | None = None
    telegram_retry_after_rate: float | None = None
    pending_task_count: int | None = None


@dataclass(frozen=True, slots=True)
class DegradationPolicy:
    state: ResourceState
    provider_concurrency_factor: float
    universe_batch_factor: float
    optional_timeframes_enabled: bool
    gemini_explanations_enabled: bool
    asset_discovery_refresh_enabled: bool
    optional_ml_inference_enabled: bool
    heavy_jobs_enabled: bool
    new_scans_enabled: bool
    # "allowed" is an upper bound only; it never enables execution by itself.
    # The configured feature flag, consent and all broker/risk gates still apply.
    real_execution_allowed: bool
    track_existing_positions: bool = True
    webhook_ack_enabled: bool = True
    telegram_commands_enabled: bool = True
    delivery_proof_enabled: bool = True
    lifecycle_tracking_enabled: bool = True
    kill_switch_enabled: bool = True
    payment_verification_enabled: bool = True
    health_endpoints_enabled: bool = True
    paused_jobs: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["state"] = self.state.value
        return payload


_HEAVY_JOBS = (
    "ml_training",
    "drift_monitoring",
    "shadow_backfill",
    "historical_replay",
    "bulk_reports",
    "bulk_exports",
)

_POLICIES = {
    ResourceState.OPTIMAL: DegradationPolicy(
        state=ResourceState.OPTIMAL,
        provider_concurrency_factor=1.0,
        universe_batch_factor=1.0,
        optional_timeframes_enabled=True,
        gemini_explanations_enabled=True,
        asset_discovery_refresh_enabled=True,
        optional_ml_inference_enabled=True,
        heavy_jobs_enabled=True,
        new_scans_enabled=True,
        real_execution_allowed=True,
    ),
    ResourceState.CONSERVATIVE: DegradationPolicy(
        state=ResourceState.CONSERVATIVE,
        provider_concurrency_factor=0.75,
        universe_batch_factor=0.75,
        optional_timeframes_enabled=False,
        gemini_explanations_enabled=False,
        asset_discovery_refresh_enabled=False,
        optional_ml_inference_enabled=True,
        heavy_jobs_enabled=False,
        new_scans_enabled=True,
        real_execution_allowed=True,
        paused_jobs=_HEAVY_JOBS,
    ),
    ResourceState.MINIMAL: DegradationPolicy(
        state=ResourceState.MINIMAL,
        provider_concurrency_factor=0.50,
        universe_batch_factor=0.50,
        optional_timeframes_enabled=False,
        gemini_explanations_enabled=False,
        asset_discovery_refresh_enabled=False,
        optional_ml_inference_enabled=False,
        heavy_jobs_enabled=False,
        new_scans_enabled=True,
        real_execution_allowed=True,
        paused_jobs=_HEAVY_JOBS,
    ),
    ResourceState.CRITICAL: DegradationPolicy(
        state=ResourceState.CRITICAL,
        provider_concurrency_factor=0.25,
        universe_batch_factor=0.0,
        optional_timeframes_enabled=False,
        gemini_explanations_enabled=False,
        asset_discovery_refresh_enabled=False,
        optional_ml_inference_enabled=False,
        heavy_jobs_enabled=False,
        new_scans_enabled=False,
        real_execution_allowed=False,
        paused_jobs=_HEAVY_JOBS + ("new_market_scans", "real_execution"),
    ),
}


def policy_for_state(state: ResourceState | str) -> DegradationPolicy:
    value = state if isinstance(state, ResourceState) else ResourceState(str(state).upper())
    return _POLICIES[value]


@dataclass(frozen=True, slots=True)
class ResourceSnapshot:
    observed_at: str
    state: ResourceState
    previous_state: ResourceState
    transitioned: bool
    recovery_streak: int
    memory_limit_source: str
    inputs: ResourceInputs
    pressure_values: Mapping[str, float]
    pressure_levels: Mapping[str, int]
    breaches: tuple[str, ...]
    policy: DegradationPolicy

    def as_dict(self) -> dict[str, Any]:
        return {
            "observed_at": self.observed_at,
            "state": self.state.value,
            "previous_state": self.previous_state.value,
            "transitioned": self.transitioned,
            "recovery_streak": self.recovery_streak,
            "memory_limit_source": self.memory_limit_source,
            "inputs": asdict(self.inputs),
            "pressure_values": dict(self.pressure_values),
            "pressure_levels": dict(self.pressure_levels),
            "breaches": list(self.breaches),
            "policy": self.policy.as_dict(),
        }


@dataclass(slots=True)
class _GovernorMetrics:
    evaluations_total: int = 0
    transitions_total: int = 0
    state_observations: dict[str, int] = field(
        default_factory=lambda: {state.value: 0 for state in ResourceState}
    )
    transition_counts: dict[str, int] = field(default_factory=dict)

    def as_dict(self, current_state: ResourceState) -> dict[str, Any]:
        return {
            "evaluations_total": self.evaluations_total,
            "transitions_total": self.transitions_total,
            "current_state": current_state.value,
            "state_observations": dict(self.state_observations),
            "transition_counts": dict(self.transition_counts),
        }


class _ProcessCpuSampler:
    def __init__(self) -> None:
        self._wall = time.monotonic()
        self._cpu = time.process_time()

    def sample_percent(self) -> float | None:
        wall_now = time.monotonic()
        cpu_now = time.process_time()
        wall_delta = wall_now - self._wall
        cpu_delta = cpu_now - self._cpu
        self._wall = wall_now
        self._cpu = cpu_now
        if wall_delta <= 0:
            return None
        cpu_count = max(1, int(os.cpu_count() or 1))
        return max(0.0, min(100.0, (cpu_delta / wall_delta) * 100.0 / cpu_count))


def _severity(value: float | None, soft: float, hard: float, critical: float) -> int:
    if value is None:
        return 0
    numeric = max(0.0, float(value))
    if numeric >= critical:
        return 3
    if numeric >= hard:
        return 2
    if numeric >= soft:
        return 1
    return 0


class ResourceGovernor:
    """Thread-safe pressure evaluator with immediate escalation and slow recovery."""

    def __init__(
        self,
        thresholds: ResourceThresholds | None = None,
        *,
        memory_limit: MemoryLimit | None = None,
    ) -> None:
        self.thresholds = thresholds or ResourceThresholds.from_env()
        self.memory_limit = memory_limit or detect_memory_limit(
            explicit_mb=self.thresholds.explicit_memory_limit_mb
        )
        self._state = ResourceState.OPTIMAL
        self._recovery_streak = 0
        self._lock = threading.Lock()
        self._cpu_sampler = _ProcessCpuSampler()
        self._metrics = _GovernorMetrics()
        self._snapshot: ResourceSnapshot | None = None

    @property
    def state(self) -> ResourceState:
        with self._lock:
            return self._state

    @property
    def policy(self) -> DegradationPolicy:
        return policy_for_state(self.state)

    @property
    def snapshot(self) -> ResourceSnapshot | None:
        with self._lock:
            return self._snapshot

    def metrics_snapshot(self) -> dict[str, Any]:
        with self._lock:
            return self._metrics.as_dict(self._state)

    def collect_inputs(
        self,
        *,
        rss_bytes: int | None = None,
        memory_limit_bytes: int | None = None,
        cpu_percent: float | None = None,
        event_loop_lag_ms: float | None = None,
        db_admission_queue_depth: int | None = None,
        db_admission_wait_ms: float | None = None,
        redis_latency_ms: float | None = None,
        delivery_queue_depth: int | None = None,
        delivery_queue_capacity: int | None = None,
        provider_error_rate: float | None = None,
        telegram_retry_after_rate: float | None = None,
        pending_task_count: int | None = None,
    ) -> ResourceInputs:
        if rss_bytes is None:
            rss_bytes = read_process_rss_bytes()
        if memory_limit_bytes is None:
            memory_limit_bytes = self.memory_limit.bytes
        if cpu_percent is None:
            cpu_percent = self._cpu_sampler.sample_percent()
        if pending_task_count is None:
            try:
                pending_task_count = len(asyncio.all_tasks())
            except RuntimeError:
                pending_task_count = None
        return ResourceInputs(
            rss_bytes=rss_bytes,
            memory_limit_bytes=memory_limit_bytes,
            cpu_percent=cpu_percent,
            event_loop_lag_ms=event_loop_lag_ms,
            db_admission_queue_depth=db_admission_queue_depth,
            db_admission_wait_ms=db_admission_wait_ms,
            redis_latency_ms=redis_latency_ms,
            delivery_queue_depth=delivery_queue_depth,
            delivery_queue_capacity=delivery_queue_capacity,
            provider_error_rate=provider_error_rate,
            telegram_retry_after_rate=telegram_retry_after_rate,
            pending_task_count=pending_task_count,
        )

    async def sample(
        self,
        *,
        measure_loop_lag: bool = True,
        loop_probe_seconds: float = 0.05,
        **external_inputs: Any,
    ) -> ResourceSnapshot:
        if measure_loop_lag and external_inputs.get("event_loop_lag_ms") is None:
            external_inputs["event_loop_lag_ms"] = await measure_event_loop_lag_ms(
                loop_probe_seconds
            )
        inputs = self.collect_inputs(**external_inputs)
        return self.evaluate(inputs)

    def _pressure(
        self,
        inputs: ResourceInputs,
        *,
        recovery: bool = False,
    ) -> tuple[dict[str, float], dict[str, int]]:
        t = self.thresholds
        factor = 1.0 - t.recovery_hysteresis_ratio if recovery else 1.0
        values: dict[str, float] = {}
        levels: dict[str, int] = {}

        def add(
            name: str,
            raw_value: float | int | None,
            soft: float,
            hard: float,
            critical: float,
        ) -> None:
            if raw_value is None:
                return
            value = max(0.0, float(raw_value))
            values[name] = value
            levels[name] = _severity(
                value,
                soft * factor,
                hard * factor,
                critical * factor,
            )

        memory_limit = int(inputs.memory_limit_bytes or 0)
        if inputs.rss_bytes is not None and memory_limit > 0:
            memory_ratio = max(0.0, float(inputs.rss_bytes) / float(memory_limit))
            values["memory_ratio"] = memory_ratio
            if recovery:
                margin_ratio = max(
                    t.recovery_hysteresis_ratio,
                    (t.memory_recovery_margin_mb * MiB) / float(memory_limit),
                )
                memory_thresholds = (
                    max(0.0, t.memory_soft_ratio - margin_ratio),
                    max(0.0, t.memory_hard_ratio - margin_ratio),
                    max(0.0, t.memory_critical_ratio - margin_ratio),
                )
            else:
                memory_thresholds = (
                    t.memory_soft_ratio,
                    t.memory_hard_ratio,
                    t.memory_critical_ratio,
                )
            levels["memory_ratio"] = _severity(memory_ratio, *memory_thresholds)

        add(
            "cpu_percent",
            inputs.cpu_percent,
            t.cpu_soft_percent,
            t.cpu_hard_percent,
            t.cpu_critical_percent,
        )
        add(
            "event_loop_lag_ms",
            inputs.event_loop_lag_ms,
            t.event_loop_soft_ms,
            t.event_loop_hard_ms,
            t.event_loop_critical_ms,
        )
        add(
            "db_admission_queue_depth",
            inputs.db_admission_queue_depth,
            t.db_queue_soft,
            t.db_queue_hard,
            t.db_queue_critical,
        )
        add(
            "db_admission_wait_ms",
            inputs.db_admission_wait_ms,
            t.db_wait_soft_ms,
            t.db_wait_hard_ms,
            t.db_wait_critical_ms,
        )
        add(
            "redis_latency_ms",
            inputs.redis_latency_ms,
            t.redis_soft_ms,
            t.redis_hard_ms,
            t.redis_critical_ms,
        )
        if inputs.delivery_queue_depth is not None:
            if inputs.delivery_queue_capacity and inputs.delivery_queue_capacity > 0:
                add(
                    "delivery_queue_ratio",
                    float(inputs.delivery_queue_depth) / float(inputs.delivery_queue_capacity),
                    t.delivery_queue_soft_ratio,
                    t.delivery_queue_hard_ratio,
                    t.delivery_queue_critical_ratio,
                )
            else:
                add(
                    "delivery_queue_depth",
                    inputs.delivery_queue_depth,
                    t.delivery_queue_soft_depth,
                    t.delivery_queue_hard_depth,
                    t.delivery_queue_critical_depth,
                )
        add(
            "provider_error_rate",
            inputs.provider_error_rate,
            t.provider_error_soft_ratio,
            t.provider_error_hard_ratio,
            t.provider_error_critical_ratio,
        )
        add(
            "telegram_retry_after_rate",
            inputs.telegram_retry_after_rate,
            t.retry_after_soft_ratio,
            t.retry_after_hard_ratio,
            t.retry_after_critical_ratio,
        )
        add(
            "pending_task_count",
            inputs.pending_task_count,
            t.pending_tasks_soft,
            t.pending_tasks_hard,
            t.pending_tasks_critical,
        )
        return values, levels

    def _candidate_level(self, levels: Mapping[str, int]) -> int:
        candidate = max(levels.values(), default=0)
        soft_count = sum(1 for value in levels.values() if value >= 1)
        hard_count = sum(1 for value in levels.values() if value >= 2)
        if candidate < 2 and soft_count >= self.thresholds.soft_breaches_for_minimal:
            candidate = 2
        if candidate < 3 and hard_count >= self.thresholds.hard_breaches_for_critical:
            candidate = 3
        return candidate

    def evaluate(self, inputs: ResourceInputs | None = None) -> ResourceSnapshot:
        current_inputs = inputs or self.collect_inputs()
        values, levels = self._pressure(current_inputs)
        raw_level = self._candidate_level(levels)

        with self._lock:
            previous = self._state
            current_level = _STATE_LEVEL[previous]
            if raw_level > current_level:
                next_level = raw_level
                self._recovery_streak = 0
            elif raw_level == current_level:
                next_level = current_level
                self._recovery_streak = 0
            else:
                _, recovery_levels = self._pressure(current_inputs, recovery=True)
                recovery_level = self._candidate_level(recovery_levels)
                if recovery_level < current_level:
                    self._recovery_streak += 1
                else:
                    self._recovery_streak = 0
                if self._recovery_streak >= self.thresholds.recovery_samples:
                    next_level = max(raw_level, current_level - 1)
                    self._recovery_streak = 0
                else:
                    next_level = current_level

            self._state = _LEVEL_STATE[next_level]
            transitioned = self._state is not previous
            self._metrics.evaluations_total += 1
            self._metrics.state_observations[self._state.value] += 1
            if transitioned:
                self._metrics.transitions_total += 1
                transition_key = f"{previous.value}->{self._state.value}"
                self._metrics.transition_counts[transition_key] = (
                    self._metrics.transition_counts.get(transition_key, 0) + 1
                )

            breaches = tuple(
                f"{name}:{_LEVEL_STATE[level].value}"
                for name, level in sorted(levels.items())
                if level > 0
            )
            snapshot = ResourceSnapshot(
                observed_at=datetime.now(timezone.utc).isoformat(),
                state=self._state,
                previous_state=previous,
                transitioned=transitioned,
                recovery_streak=self._recovery_streak,
                memory_limit_source=self.memory_limit.source,
                inputs=current_inputs,
                pressure_values=dict(values),
                pressure_levels=dict(levels),
                breaches=breaches,
                policy=policy_for_state(self._state),
            )
            self._snapshot = snapshot

        self._publish_metrics(snapshot)
        return snapshot

    @staticmethod
    def _publish_metrics(snapshot: ResourceSnapshot) -> None:
        try:
            if _RESOURCE_STATE_GAUGE is not None:
                for state in ResourceState:
                    _RESOURCE_STATE_GAUGE.labels(state=state.value).set(
                        1 if state is snapshot.state else 0
                    )
            if _RESOURCE_PRESSURE_GAUGE is not None:
                for name, value in snapshot.pressure_values.items():
                    _RESOURCE_PRESSURE_GAUGE.labels(metric=name).set(float(value))
            if snapshot.transitioned and _RESOURCE_TRANSITIONS is not None:
                _RESOURCE_TRANSITIONS.labels(
                    from_state=snapshot.previous_state.value,
                    to_state=snapshot.state.value,
                ).inc()
        except Exception:
            # Metrics must never break health, delivery, or lifecycle work.
            return


_DEFAULT_GOVERNOR: ResourceGovernor | None = None
_DEFAULT_GOVERNOR_LOCK = threading.Lock()


def get_resource_governor() -> ResourceGovernor:
    global _DEFAULT_GOVERNOR
    if _DEFAULT_GOVERNOR is None:
        with _DEFAULT_GOVERNOR_LOCK:
            if _DEFAULT_GOVERNOR is None:
                _DEFAULT_GOVERNOR = ResourceGovernor()
    return _DEFAULT_GOVERNOR


def resource_snapshot() -> dict[str, Any]:
    governor = get_resource_governor()
    snapshot = governor.snapshot or governor.evaluate()
    payload = snapshot.as_dict()
    payload["metrics"] = governor.metrics_snapshot()
    return payload


__all__ = [
    "DegradationPolicy",
    "MemoryLimit",
    "ResourceGovernor",
    "ResourceInputs",
    "ResourceSnapshot",
    "ResourceState",
    "ResourceThresholds",
    "detect_memory_limit",
    "detect_memory_limit_bytes",
    "get_resource_governor",
    "measure_event_loop_lag_ms",
    "policy_for_state",
    "read_process_rss_bytes",
    "resource_snapshot",
]
