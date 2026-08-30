# SignalRankAI v1.2.8 Outcome Performance and Railway Readiness Hotfix

Date: 2026-07-30  
Release fingerprint: `v1.2.8-outcome-perf-readiness-hotfix-20260730`  
Migration head: `0027_launch_paper_trading` (unchanged)

## Why this release exists

The first v1.2.7 Railway staging run proved that the new outcome reconciliation, adaptive candle persistence and live-price paths were active. It also exposed one code regression and one observability-contract ambiguity:

- outcome scans reached delivered signals, but the user-performance recipient query repeatedly failed with `name 'func' is not defined`;
- deployment diagnostics could report `/metrics/prometheus` as missing even though the compatibility web application defined it, because Railway's main application did not own an explicit direct route.

The misleading outcome warning wrapped both canonical lifecycle processing and the optional analytics lookup in one exception boundary. That made a recipient-query failure sound like the signal outcome itself had failed.

## Changes

### 1. Deterministic SQLAlchemy imports

`engine/realtime_outcome_tracker.py` now imports SQLAlchemy `func` and `select` at module scope. Every delivery-proof query therefore resolves the same symbols in background scans, reconciliation and stale-overlay deployments.

### 2. Outcome lifecycle and analytics failure isolation

The per-signal worker now has separate error boundaries:

- `signal_check_failed` is emitted only when the canonical lifecycle/outcome transition fails;
- `recipient_lookup_failed` is emitted only when the optional user-performance recipient lookup fails.

A user-performance lookup issue can no longer mask a successfully persisted lifecycle transition.

### 3. Proof-backed performance recipients

User-performance updates are now derived only from durable Telegram delivery proofs with:

- `sent_ok=true`;
- non-null Telegram chat and message identifiers;
- a case-normalised state in `sent`, `delivered`, `confirmed` or `reconciled`.

Null Telegram user identifiers are ignored safely.

### 4. Direct Railway Prometheus route

`railway_main.py` now owns `/metrics/prometheus` directly and renders metrics through `core.telemetry`. The compatibility web application remains mounted, but the Railway scrape/readiness route no longer depends on that mount.

### 5. Stronger production-readiness contract

The readiness checker now includes a ninth named gate, `railway_direct_observability_routes`, requiring Railway's main application to own both `/healthz` and `/metrics/prometheus`.

### 6. Versioned deployment profiles and regression guards

The release includes refreshed v1.2.8 Railway staging and phased-production profiles, a v1.2.8 verifier and regression tests. Compatibility verifiers for v1.2.5, v1.2.6 and v1.2.7 remain active.

## Verification

- Tracked Python compilation: PASS (`749` files, `0` failures)
- Schema audit: PASS
- Alembic revisions: `27`
- Sole migration head: `0027_launch_paper_trading`
- Production readiness: `9/9` PASS
- Architecture smoke: PASS
- Legacy DB session call sites: `0`
- Secret scan: `0` findings
- v1.2.5 compatibility verifier: PASS
- v1.2.6 compatibility verifier: PASS
- v1.2.7 compatibility verifier: PASS
- v1.2.8 verifier: PASS
- Focused hotfix suite: `22` passed
- Broader outcome/adaptive/readiness suite: `92` passed, `2` dependency-bound tests deselected

## Local certification limitation

The certification container does not include `python-telegram-bot` or APScheduler. Tests that import the Telegram runtime or Railway scheduler cannot collect locally. These packages are declared by the project and were present in the supplied Railway runtime logs, but the affected endpoint/callback paths still require post-deployment proof.

## Required Railway evidence

1. Boot reports `SignalRankAI v1.2.8` and the exact release fingerprint.
2. No `name 'func' is not defined` warning appears.
3. No legacy `Error updating user performance for signal` warning appears.
4. Outcome scans process proof-backed active signals and lifecycle transitions persist.
5. Recipient lookup either succeeds or emits the distinct `recipient_lookup_failed` event without cancelling lifecycle work.
6. `/metrics/prometheus` returns HTTP 200 from the Railway service and exposes SignalRank metrics.
7. `/healthz` remains HTTP 200.
8. Deployment diagnostics report `railway_direct_observability_routes` as PASS.
9. Telegram callback, monitor and outcome buttons are exercised in the deployed dependency-complete environment.
10. Live Paystack testing remains allowlisted, capped and signed; unrestricted execution and automatic payouts remain disabled.

## Safety boundary

This hotfix does not enable unrestricted real broker execution, automatic live trading, copy trading or automatic payouts. The existing staged-production boundary remains unchanged.
