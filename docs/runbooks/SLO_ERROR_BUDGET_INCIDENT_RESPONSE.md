# SignalRank SLO Error-Budget Incident Response

This runbook is the operational response contract for the canonical SLOs in
`core/slo_registry.py` and the alert policies in
`observability/slo_operations.py`.

## Alert thresholds

- **Warning:** at least 50 observations, remaining error budget below 50% but
  above 0%, sustained for 5 minutes.
- **Critical:** at least 100 observations and either remaining budget is 0% or
  the SLO is in its canonical degraded state, sustained for 2 minutes.
- **Service down:** `signalrank_service_up == 0` for 1 minute.
- **Provider unhealthy:** `signalrank_exchange_api_health == 0` for 2 minutes.

Never enable real execution, loosen a hard risk ceiling, disable account
reconciliation, weaken quote freshness, bypass object authorization, or turn
off schema/release admission as an incident workaround.

## Ownership and automatic safety action

| SLO | Owner | Automatic degradation / safety action |
| --- | --- | --- |
| `webhook_ack_p95` | frontdoor | `degrade_telegram_webhook_to_queue_only` |
| `webhook_ack_p99` | frontdoor | `degrade_telegram_webhook_to_queue_only` |
| `signal_persistence_p99` | engine | `pause_engine_scan_cycles` |
| `qualified_signal_delivery_p95` | delivery | `disable_public_one_minute_delivery` |
| `outcome_detection_p95` | worker | `increase_tracker_interval_and_alert` |
| `notification_queue_age_p99` | notifications | `throttle_fanout_and_backoff` |
| `performance_projection_coverage` | ledger | `pause_reconciliation_rebuilds` |
| `outcome_projection_coverage` | outcomes | `queue_outcome_outbox_repair` |

The owner is responsible for first response, diagnosis, mitigation, and the
post-incident evidence record. Platform/engineering owns cross-service
coordination.

## First five minutes

1. Confirm the alert is based on enough samples; do not react to a cold-start
   metric with fewer than the alert rule's minimum observations.
2. Open the **SignalRank SLO & Error Budget Overview** Grafana dashboard.
3. Identify the affected SLO, owning service, current release SHA, Railway
   deployment, and whether the error budget is warning or exhausted.
4. Check `/healthz`, `/metrics/prometheus`, provider health, DB pressure,
   queue age, and the owning service logs using safe correlation IDs.
5. Verify the global execution kill switch and all real-money gates remain in
   their intended state. Incident response must never auto-enable money flow.
6. Apply or verify the canonical degradation action above.
7. If the latest deployment correlates with the regression, roll back to the
   latest release that passed release-source, schema, and clean-room gates.

## Diagnosis by SLO

### Webhook acknowledgement

Inspect Telegram ingress rate, request latency, webhook worker backlog, Redis
availability, DB priority pressure, and Telegram Bot API status. Keep ingress
acknowledgement fast; defer noncritical work to queues instead of making the
webhook wait.

### Signal persistence

Inspect database priority/admission, PgBouncer saturation, slow statements,
unique-bucket contention, and engine-cycle concurrency. Pause new scan cycles
before allowing persistence pressure to corrupt or duplicate state.

### Qualified delivery

Inspect delivery queue age, Telegram API response codes, quote freshness,
delivery idempotency, and rate-limit/backoff state. Never send a stale signal to
"catch up" after an outage.

### Outcome detection

Inspect canonical outcome-writer ownership, tracker lag, provider quote health,
and lifecycle projection. Do not start a second live outcome writer.

### Notification queue age

Inspect fanout size, rate limits, retries, queue/DLQ growth, Redis, and
foreground DB admission. Throttle lower-priority fanout before interactive
traffic.

### Projection coverage

Inspect outbox/projector health, reconciliation jobs, duplicate/idempotency
guards, and ledger/lifecycle source evidence. Rebuild from canonical persisted
evidence only; do not fabricate missing financial or outcome data.

## Service down

Confirm Railway deployment state, release/source gate, Alembic admission,
database/Redis dependencies, and the process ownership mode. If the service
cannot pass readiness after rollback, keep it out of traffic and escalate to
platform engineering.

## Provider unhealthy

Confirm whether the fault is venue-wide, credential/entitlement-specific,
rate-limit related, or instrument-specific. Disable or quarantine the affected
provider/capability and use an independently trusted fallback only where the
canonical provider policy allows it.

## Recovery criteria

An incident can be resolved only when:

- the owning service is healthy;
- the SLO is no longer degraded;
- the error budget is stable or recovering for at least 15 minutes;
- queue/backlog metrics are draining rather than merely hidden;
- no safety gate was weakened during mitigation;
- live execution/account reconciliation state is consistent;
- the release SHA and schema head are recorded in the incident evidence.

After resolution, add or update a regression test for any code/config defect
that caused the incident.
