# SignalRankAI v1.3.6.4 Runtime Stability and Provider Coverage Hotfix

**Application version:** 1.3.6
**Hotfix/tooling revision:** 1.3.6.4
**Base release:** v1.3.6 Railway Performance Decomposition
**Target:** decomposed Railway front door, engine, and worker services

## Purpose

This hotfix addresses the remaining staging findings after the v1.3.6 Railway split:

1. `/performance` duplicate-ledger traceback.
2. Intermittent resend ownership and stale production lock scope in staging.
3. Front-door scheduler jobs exceeding their own intervals.
4. Incomplete FX and metals live-price provider routing.
5. Production readiness being reported without complete trusted provider coverage.

## Changes

### 1. Idempotent performance-ledger reconciliation

`services/performance_ledger.py` now uses one PostgreSQL `INSERT ... ON CONFLICT DO UPDATE` operation against `uq_performance_ledger_scope`.

- Concurrent `/performance` reconciliation no longer races through a read-then-insert sequence.
- Finalized rows remain immutable.
- Mutable rows update only when the snapshot changes.
- Duplicate source rows are collapsed to one row per canonical signal before the statement is issued.
- Railway environment metadata takes precedence over a copied `APP_ENV` value, preventing staging records from being written with `environment=production`.

### 2. Cluster-wide scheduler ownership

New module: `core/job_leases.py`.

- Redis `SET NX EX` is the preferred cross-replica lease.
- PostgreSQL advisory locking is the fallback.
- Production fails closed when no distributed lock backend is available.
- Lock scope is `project:environment:job`; it deliberately excludes service and deployment IDs.
- Redis lease release is token-safe.
- PostgreSQL locks are explicitly released and job-body exceptions are never swallowed by lock fallback logic.

Both jobs now use the lease:

- `resend_unsent_signals_job`
- `send_outcome_notifications`

A standby log is expected when another healthy replica owns a lease. Repeated old logs containing `another instance holds advisory lock ... :production` should disappear after every old deployment is stopped.

### 3. Bounded front-door background work

Defaults are deliberately below their scheduling intervals:

| Job | Interval | Work budget | Lease |
|---|---:|---:|---:|
| Resend recovery | 60 s | 20 s | 45 s |
| Outcome notifications | 90 s | 20 s | 45 s |
| Monitor refresh | 120 s | existing bounded implementation | n/a |

Additional controls:

- Resend candidates: 50 maximum queried.
- Resend users per run: 6.
- Resend signals per run: 3.
- Outcome records per run: 5.
- Remaining work is deferred to the next run when the monotonic budget expires.
- Outcome market data is fetched once per outcome, not once per recipient.
- Background jobs defer by default while critical/interactive DB work is active.
- Scheduler jobs use coalescing and bounded misfire grace.
- Resend can be disabled with `RESEND_UNSENT_JOB_ENABLED=0` during emergency diagnosis.

### 4. Trusted FX and metals live-price routing

`data/get_live_price.py` now builds routes from providers that are actually configured, so missing API keys do not consume the quote deadline.

FX and commodity order:

1. MetaApi broker-native bid/ask
2. OANDA
3. Twelve Data
4. FCS API v4
5. Yahoo public fallback

The FCS implementation uses `/forex/latest`, supports the v4 response contract, includes `type=commodity` for metals, maps `XAGUSD` to `SILVER`, and requires a provider timestamp.

MetaApi requires a token and an account. For production readiness, configure a dedicated explicit account ID rather than relying on owner-account lookup.

### 5. Fail-closed production provider readiness

`/readyz` now includes `checks.provider_coverage`.

- Staging remains reachable while reporting partial coverage.
- Production readiness fails when an enabled FX or commodity class has no configured trusted provider.
- Yahoo-only FX or commodity routing is not accepted as production-complete.
- The readiness check is configuration-only and does not make external price requests, avoiding rate-limit pressure on health probes.

## Required Railway settings

Apply the accompanying `SignalRankAI_v1.3.6.4_Railway.env.example` values to the front-door service. Keep engine and worker role variables unchanged.

For production FX/metals coverage, configure at least one trusted path:

- MetaApi: `META_API_TOKEN` plus `META_API_MARKET_DATA_ACCOUNT_ID`
- OANDA: `OANDA_API_KEY`/`OANDA_TOKEN` plus `OANDA_ACCOUNT_ID`
- Twelve Data: `TWELVEDATA_API_KEY`
- FCS API: `FCS_API_KEY`

MetaApi or OANDA is preferred for broker-native bid/ask data.

## Deployment order

1. Back up the current project or create a Git branch.
2. Apply the overlay or replace the project with the full hotfix release.
3. Deploy the same commit to front door, engine, and worker.
4. Ensure old deployments and extra front-door replicas are stopped.
5. Confirm the public domain remains attached only to the front door.
6. Run `/readyz` and inspect `checks.provider_coverage`.
7. Run `/performance` twice in quick succession.
8. Click inline buttons and send normal commands.
9. Observe at least three resend and outcome scheduler intervals.

## Runtime certification targets

The deployment is not certified until all conditions hold:

- No `UniqueViolationError` or `uq_performance_ledger_scope` traceback.
- `/performance` succeeds repeatedly.
- No stale `:production` lock scope in staging.
- No repeated `maximum number of running instances reached` warnings for resend or outcome notifications.
- Webhook pending count returns to zero.
- Callback acknowledgements remain immediate.
- Production `/readyz` reports provider coverage complete.
- `XAGUSD` and at least one FX pair receive fresh timestamped quotes from a configured trusted provider.

## Local validation performed

- Focused regression suite: 78 passed.
- Expanded relevant suite: 110 passed, 3 deselected because the offline validation container did not contain APScheduler and could not download packages.
- Hotfix-specific tests: 10 passed.
- Full Python compilation: passed.
- Cross-replica lease local smoke test: passed, including exception propagation and reacquisition.

These validations prove source-level correctness in the supplied v1.3.6 archive. Production certification still requires the runtime checks above after Railway deployment.
