# SignalRankAI v1.2.7 Certification Report

Date: 2026-07-30  
Scope: delivered-signal outcome discovery, missed milestone reconciliation, Telegram lifecycle notifications, monitor price freshness and venue attribution, adaptive status/candle persistence, Redis health reporting, simulation evidence, PostgreSQL capacity and phased public-production boundaries.

## Certification status

**Locally code-certified as a production launch candidate. Railway runtime certification is still required before public onboarding.**

This report does not certify unrestricted live broker auto-execution, copy trading or automatic payouts.

## Evidence from the v1.2.6 Railway log

- The correct v1.2.6 release booted in staging.
- The callback acknowledgement guard registered and 171 handlers were ready.
- XAUTUSDT callback updates were acknowledged successfully.
- The outcome worker repeatedly returned zero active signals while the engine retained five proof-backed open signals.
- The XAUTUSDT signal therefore remained active after entry, TP1 and TP2 were crossed.
- Monitor refreshes timed out or could not persist during DB admission contention.
- Adaptive candle persistence repeatedly failed with asyncpg parameter-type ambiguity.
- `/adaptive_status` failed because PostgreSQL could not infer a nullable parameter type; this was incorrectly surfaced as connection pressure.
- State Redis, delivery Redis and delivery queue diagnostics passed even though `/system` showed a Redis `TypeError`.
- Redis webhook enqueue timed out twice; one indeterminate timeout allowed both the Redis and in-process copies of the same update to run, explaining the duplicate `/adaptive_status` response.
- PostgreSQL schema and admission diagnostics passed.
- The staging process was deliberately constrained to a pool of two connections with zero overflow.

## Implemented v1.2.7 controls

- Case-insensitive delivery-state proof queries.
- Immediate per-signal lifecycle reconciliation for Monitor and Check Outcome.
- Restart/backfill discovery of proof-backed delivered signals with no terminal outcome.
- Notification recipients normalised across sent/confirmed/delivered/reconciled states.
- Outcome DB work on a bounded critical lane.
- Typed, source-aged live quotes for Monitor.
- Provider-symbol attribution for venue comparison.
- Rejection of stale Redis tick projections.
- Typed nullable adaptive-status query parameters.
- Command error classification that separates query defects from real DB pressure.
- Chunked PostgreSQL candle upserts and changed-suffix capture.
- Valid Redis health-client arguments and event-loop-safe checks.
- Retryable 503 handling for indeterminate Redis enqueue timeouts, preventing dual Redis/local processing.
- Proof-backed `/system` backlog metrics.
- Terminal-only Monte Carlo evidence with transparent pending/partial counts.
- PostgreSQL capacity-headroom launch gate.
- Separate validated staging and phased-production profiles.
- No new migration; sole Alembic head remains `0027_launch_paper_trading`.

## Verification results

- Python compilation: PASS
- Schema audit: PASS
- Alembic revisions: 27
- Sole migration head: `0027_launch_paper_trading`
- Production readiness: 8/8 PASS
- Architecture smoke: PASS
- Secret scan: zero findings
- v1.2.5 compatibility verifier: PASS
- v1.2.6 compatibility verifier: PASS
- v1.2.7 verifier: PASS
- Selected launch/outcome/adaptive/paper/production regression tests: 119 passed

## Local dependency limitation

The local certification image does not contain APScheduler, so `tests/test_outcome_integration_multi_tp.py` cannot collect because importing the Telegram bot imports APScheduler. Railway logs prove the deployed environment contains APScheduler and `python-telegram-bot`, and v1.2.6 registered 171 handlers. The multi-TP runtime path must still be demonstrated after v1.2.7 deployment.

## Database decision

A second writable database is not approved for this release. Current evidence supports one primary with measured connection headroom, controlled pools, reduced adaptive writes and Redis separation. PgBouncer, a primary upgrade or an analytics read replica may be introduced later based on measured load. Payments, subscriptions, delivery proofs and outcomes must remain on one authoritative primary.

## Public-launch decision

The currently deployed v1.2.6 runtime is **not production-ready** because outcome discovery returns zero and adaptive persistence is failing.

v1.2.7 may become the initial public release only after Railway runtime proof confirms the fixes. The first public phase may enable subscriptions, signal delivery, callbacks, outcome notifications, paper trading and demo/manual execution. Real broker execution, automatic trading, copy trading and automatic payouts remain disabled.

## Required Railway proof

1. `[boot] SignalRankAI v1.2.7` with fingerprint `v1.2.7-outcome-price-production-gate-20260730`.
2. Handler readiness `ready=True` with at least 60 handlers.
3. `active_scan fetched=>0` while proof-backed active deliveries exist.
4. Reconciliation processes `b15e7d94-9bf5-4cf6-8eaa-da842ccd9d7d`.
5. `entry_touched`, `tp1_hit` and `tp2_hit` are persisted and notification rows are sent.
6. `/monitor` reports a trusted provider, provider symbol and acceptable source age.
7. `/adaptive_status` succeeds without a query error.
8. No adaptive candle `AmbiguousParameterError` or repeated full-history write amplification.
9. `/system` reports state Redis connected and reasonable proof-backed backlog values.
10. `/simulate` reports completed, pending and partial evidence accurately.
11. `postgresql_capacity_headroom` passes.
12. Live Paystack key pairing and a signed webhook test pass.
13. Runtime diagnostics contain no critical/high failures; live-provider and isolated full-suite checks are executed rather than skipped.
