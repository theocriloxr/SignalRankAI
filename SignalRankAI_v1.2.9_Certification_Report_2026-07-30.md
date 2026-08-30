# SignalRankAI v1.2.9 Certification Report

Date: 2026-07-30
Scope: lifecycle persistence, profile command DB ownership, auxiliary-loop database observability and retained v1.2.5-v1.2.8 controls.

## Status

**Locally code-certified for controlled Railway staging deployment. Runtime certification is still required.**

This release does not certify unrestricted live broker execution, copy trading, automatic payouts or public onboarding.

## Verified fixes

- `record_lifecycle_event()` imports SQLAlchemy `func` in its own scope.
- `/profile` does not hold a DB session across Telegram network I/O.
- `/profile` does not open a nested interactive session for timezone checks.
- Profile operations use explicit labels and a bounded foreground timeout.
- `/system` can report the main pooled engine from an auxiliary loop.
- Database health reads have a realistic interactive admission timeout.
- v1.2.8 outcome-performance and direct Prometheus fixes are retained.
- Owner ready notifications use an atomic cross-instance dedupe key during rolling deploy overlap.

## Verification results

- Tracked Python files: `751`
- Python compilation failures: `0`
- Focused v1.2.9 and retained-release suite: `46 passed`
- Broad dependency-independent suite: `210 passed, 3 deselected`
- Deselect reasons: local image lacks `python-telegram-bot` and APScheduler; the affected assertions import those packages directly.
- Production readiness: `9/9 PASS`
- Architecture smoke: `PASS`
- Legacy DB session call sites: `0`
- Schema audit: `PASS`
- Alembic revisions: `27`
- Sole migration head: `0027_launch_paper_trading`
- Secret scan: `0 findings`
- Governance validation: `24 documents PASS`
- v1.2.5 compatibility verifier: `PASS`
- v1.2.6 compatibility verifier: `PASS`
- v1.2.7 compatibility verifier: `PASS`
- v1.2.8 compatibility verifier: `PASS`
- v1.2.9 verifier: `PASS`

## Required Railway proof

1. Exact v1.2.9 boot identity and release fingerprint.
2. No `NameError: name 'func' is not defined` from either `realtime_outcome_tracker.py` or `signal_lifecycle.py`.
3. `active_scan fetched=...` followed by successful lifecycle event logs and persisted outcomes.
4. `/system` shows a pool capacity and PostgreSQL `max_connections`, or an explicit health error rather than a false auxiliary-loop absence.
5. `/profile` returns once with no `TimeoutError` for a new and existing user.
6. `/profile day` persists and is visible on the next `/profile` read.
7. `/healthz`, `/livez`, `/readyz` and `/metrics/prometheus` return HTTP 200.
8. Portfolio exposure falls as old signals receive terminal outcomes.
9. Paystack remains disabled unless a matching live key pair and the guarded staging acknowledgement are configured.

## Decision

Deploy v1.2.9 to the existing Railway staging service as a complete replacement archive. Do not overlay individual files on v1.2.8. Keep live account execution and public payout expansion blocked until the runtime proof above is captured.
