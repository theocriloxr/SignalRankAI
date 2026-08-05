# RELEASE NOTES — SignalRankAI V2.0 architecture layer

**Date:** 2026-08-05 · **Branch:** `fix/railway-alembic-url` (commit to follow)

## Summary

Adds the V2.0 event, provider, risk, SLO and ledger foundations on top of the
certified v1.3.6.9 + parity work. This layer is additive and feature-flagged;
existing behaviour is preserved (full suite green before and after).

## New modules

* `core/event_catalogue.py` — canonical event registry and validation.
* `core/transactional_outbox.py` — transactional outbox, idempotent inbox,
  bounded relay with exponential backoff and dead-letter routing.
* `core/durable_event_stream.py` (extended) — `EventEnvelope` gains the full
  §6.1 identity set (aggregate, organization, strategy, provider, venue,
  trace, deployment, producer service) and a tamper-evident `payload_hash`.
* `data/provider_failures.py` — typed failure taxonomy with HTTP
  classification and permanent/retryable policy.
* `data/canonical_instruments.py` — rich canonical instrument model, symbol
  normalization, alias registry, split adjustment.
* `core/risk_authority.py` — portfolio risk authority: exposure limits,
  daily-loss / consecutive-loss / drawdown / spread / slippage / volatility
  breakers, kill-switch gate, decimal-safe.
* `core/slo_registry.py` — SLO table, error budgets, degradation decisions.
* `core/financial_ledger.py` — append-only decimal ledger, compensating
  corrections, double-entry pairs, imbalance/orphan detection, daily
  snapshots, deterministic replay.

## Behaviour changes

* `EventEnvelope` validates payload tampering via `payload_hash`.
* Relay/queue retries re-claim failed entries with backoff instead of
  hot-looping; dead-lettered entries are terminal.
* Risk admission is fully fail-closed on kill switch and breakers.

## Maintenance fixes in this pass

* `scripts/build_v7_governance.py` now excludes `.freebuff` (local agent/app
  state) from repo-wide hashing, making governance generation deterministic
  and `test_v7_governance_contract` reproducible in this workspace.
* Implemented the missing `_resend_advisory_lock()` (resend lock identity
  scoped by project + environment) and wired its identity into the resend job
  log. `core/job_leases.lock_id_for_scope` is now public; the scope reuses
  the canonical `scheduler_job_scope`, and `runtime_environment_name` honours
  `RAILWAY_ENVIRONMENT_ID`.
* `test_v1364_runtime_stability_hotfix` made deterministic (patched discovery
  snapshot in both phases instead of depending on local DB state).
* Seven release-pinned tests updated from the stale v1.3.6.7 fingerprint to
  the actual v1.3.6.9 release identity.

## Safety

No provider, venue or real-money capability was enabled. Execution and payout
flags remain off (`GLOBAL_EXECUTION_KILL_SWITCH` etc.). External dependencies
are tracked in `BLOCKED_EXTERNAL_REQUIREMENTS.md`.

## Tests

5 new test modules (`tests/test_v20_*.py`, 55 tests) covering envelope,
catalogue, outbox/inbox/relay, failure taxonomy, instruments, risk authority,
SLO budgets and financial ledger.
