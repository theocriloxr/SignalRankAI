# SignalRankAI v1.3.6.9 Deployment and Certification

## Pre-deployment

1. Back up PostgreSQL and record the current migration head.
2. Deploy the same Git commit to front door, engine and worker.
3. Confirm all three report version `1.3.6.9`, the same full commit SHA and migration `0034_production_integrity`.
4. Keep these fail-closed:

```text
REAL_EXECUTION_ENABLED=0
AUTO_EXECUTION_ENABLED=0
AUTO_TRADE_ENABLED=0
COPY_TRADE_ENABLED=0
BYBIT_EXECUTION_ENABLED=0
REAL_PAYOUTS_ENABLED=0
PAYMENTS_PUBLIC_ENABLED=0
PUBLIC_WIN_RATE_MARKETING_ENABLED=0
GLOBAL_EXECUTION_KILL_SWITCH=1
```

## First owner commands

Run in this order:

```text
/outcome_rebuild dry_run
/outcome_rebuild apply
/outcome_rebuild status
/outcome_audit 30
/performance_rebuild dry_run
/performance_rebuild apply
/performance_audit 30
```

The apply command may generate delayed historical-reconciliation messages for terminal outcomes whose outbox rows were missing. That is expected; each message must identify itself as historical when delayed beyond the configured threshold.

## Required positive evidence

Worker:

```text
[outcome_tracker] Outcome persisted: <signal> -> <status>
[outcome_reconciliation] completed outcome={... failed: 0} outbox={... failed_outcomes: 0}
```

Front door:

```text
[outcome_notify_cycle] pending=<n> recipients=<n> sent=<n> failed=0 quiet_deferred=<n> elapsed_ms=<n>
```

Owner audit:

- outcome projection coverage >= 99%;
- missing outcome projection = 0 or explained active/pending records;
- failed outbox rows = 0 after retry;
- no stale `sending` rows;
- performance `failed_users=0`;
- performance outcome-to-ledger mismatch = 0;
- malformed terminal rows = 0.

## Automatic rejection conditions

Do not approve production if any of these appear:

- `name '_env_bool' is not defined`;
- repeated `persist_outcome error`;
- outbox queue failures that are not repaired on the next reconciliation pass;
- duplicate terminal messages for the same user/signal/stage;
- a terminal Outcome disappears after a notification failure;
- TP1/TP2 progress becomes a full `-1R` loss;
- quiet-hour messages are lost rather than deferred;
- front-door webhook p99 remains above 1 second;
- repeated resend budget exhaustion without the configured backoff;
- terminal coverage remains below the certification threshold;
- service commit or migration drift;
- any real execution or public performance claim becomes enabled.

## Soak duration

Run at least 24 hours and long enough to observe fresh entry, TP progression, terminal outcomes, an expiry/missed entry, paper closure, notification retry and service restart. Production approval requires observed evidence, not only absence of errors.

## Logs to return for the next verdict

- Complete startup sections for all three services.
- Every `outcome_tracker`, `outcome_reconciliation`, `outcome_notify_cycle` and outbox error line.
- All four outcome/performance command outputs.
- Telegram screenshots/messages for at least one TP, one stop/protected exit, and one expiry/missed-entry outcome.
- Webhook p50/p95/p99, queue age and resend summaries.
