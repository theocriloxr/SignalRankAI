# Resource governor and production health

## Resource pressure contract

`core/resource_governor.py` provides the process-level pressure state machine.
It can sample process RSS, cgroup/host memory limit, process CPU, event-loop lag
and pending asyncio tasks. Runtime owners provide current DB admission depth and
wait, Redis latency, delivery queue depth/capacity, provider error rate and
Telegram `RetryAfter` rate.

States and policy:

| State | New scans | Optional/heavy work | Real execution ceiling | Critical paths |
|---|---:|---:|---:|---|
| `OPTIMAL` | allowed | allowed when separately configured | allowed when separately configured | preserved |
| `CONSERVATIVE` | reduced | heavy work paused | allowed when separately configured | preserved |
| `MINIMAL` | reduced further | optional inference and heavy work paused | allowed when separately configured | preserved |
| `CRITICAL` | paused | paused | blocked | health, webhooks, commands, delivery proof, lifecycle, kill switch, payment verification and existing-position tracking preserved |

Escalation is immediate. Recovery requires
`RESOURCE_RECOVERY_SAMPLES` consecutive observations below hysteresis boundaries
and moves down no more than one state at a time. `APP_MEMORY_LIMIT_MB=0` uses a
finite cgroup v2/v1 limit when available and otherwise falls back to host
physical memory. An explicit positive value overrides detection.

The runtime API is:

```python
from core.resource_governor import get_resource_governor

governor = get_resource_governor()
snapshot = await governor.sample(
    db_admission_queue_depth=db_queue_depth,
    db_admission_wait_ms=db_wait_ms,
    redis_latency_ms=redis_latency_ms,
    delivery_queue_depth=delivery_depth,
    delivery_queue_capacity=delivery_capacity,
    provider_error_rate=provider_error_ratio,
    telegram_retry_after_rate=retry_after_ratio,
)
policy = snapshot.policy
```

Every snapshot is JSON-serializable through `snapshot.as_dict()`. The governor
also publishes bounded Prometheus gauges/counters when `prometheus-client` is
installed. A policy is an upper bound only; it never enables a feature that is
disabled by its own configuration or bypasses consent, broker, risk or
kill-switch controls.

## Railway Hobby profiles

Use one profile as the non-secret source of truth:

- `configs/env/railway-hobby-owner-beta.env.example`
- `configs/env/railway-hobby-full-advisory.env.example`
- `configs/env/railway-hobby-paper-demo.env.example`
- `configs/env/railway-hobby-real-execution-gated.env.example`

Each profile uses one Uvicorn worker, a Postgres pool of two with zero overflow,
bounded webhook/provider work, cgroup-aware memory thresholds, and separate
`RedisState` and `RedisDelivery` references. The real-execution-gated template
still has all real-order flags off; it is not an activation instruction.

Validate before deployment:

```text
python scripts/validate_env_contract.py configs/env/railway-hobby-owner-beta.env.example
```

## Production health probe

`scripts/production_health.py` performs read-only checks for:

- `/livez`
- `/healthz`
- `/readyz`
- `SELECT 1` through the canonical async DB admission API
- state Redis `PING`
- delivery Redis `PING`
- distinct state/delivery Redis topology

It never prints URLs, credentials, response bodies or exception messages.

```text
python scripts/production_health.py --base-url https://your-service.example
```

Exit code `0` means every selected check passed. Exit code `1` blocks promotion.
Use `--json` for machine-readable output. `--skip-http` and
`--skip-dependencies` are diagnostic-only and do not constitute full production
health evidence.
