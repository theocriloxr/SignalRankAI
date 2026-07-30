# SignalRankAI v1.2.9 Lifecycle, Profile and Observability Hotfix

Date: 2026-07-30

## Runtime evidence addressed

The v1.2.8 Railway deployment booted with the expected release fingerprint and successfully started the signal engine, outcome worker, Telegram webhook dispatcher, scheduler, adaptive candle capture and paper-trading worker. The supplied logs then exposed two independent regressions:

1. Every lifecycle transition failed in `engine/signal_lifecycle.py` because `record_lifecycle_event()` used SQLAlchemy `func` without importing it in that function's scope.
2. `/profile` displayed the user's profile and then returned `TimeoutError`. The command held the only interactive DB lane while calling `maybe_prompt_timezone()`, which attempted to open a second interactive session. This was a deterministic self-deadlock.

The logs also showed `/system` reporting unavailable pool metrics from an auxiliary webhook event loop even though the main Railway pool and PostgreSQL capacity were healthy.

## Fixes

- Imports `func` and `select` inside `record_lifecycle_event()`.
- Restores lifecycle event persistence, terminal outcome projection and notification queueing.
- Allows reconciliation backfill to close already delivered TP/SL/expired signals after deployment.
- Refactors `/profile` so all Telegram I/O occurs after the DB session is released.
- Reuses the already loaded user row for timezone prompting, preventing nested interactive sessions.
- Uses explicit `profile.read` and `profile.write` DB labels with a five-second operation timeout.
- Gives database health inspection a three-second foreground admission timeout.
- Makes `/system` select the main non-NullPool engine from the process inventory when invoked on an auxiliary webhook loop.
- Raises the documented Railway interactive DB gate timeout to three seconds.
- Suppresses duplicate owner-ready notifications across overlapping Railway rolling-deploy containers with an atomic Redis TTL claim.
- Adds v1.2.9 regression tests, verifier, deployment profiles and release fingerprint.

## Expected runtime effect

After deployment, the eight proof-backed delivered signals should be reconciled normally. Any signal already beyond its stop loss, TP level or expiry boundary should receive a durable lifecycle/outcome update during backfill. As terminal rows are created, stale open-signal exposure should leave the five-trade portfolio count and new eligible signals can progress again.

`/profile` must return exactly one profile response without a trailing timeout error. Profile update forms such as `/profile day`, `/profile risk conservative` and `/profile assets forex crypto index` must persist successfully.

## Not code defects

- `Dataset versions: 0` and `Walk-forward runs: 0` are expected while there are no proof-backed terminal outcomes and insufficient approved training evidence. Adaptive candle capture is active, but candle storage alone does not create a promoted dataset version.
- Paystack remained disabled because the Railway environment did not contain a valid matching `PAYSTACK_SECRET_KEY` and `PAYSTACK_PUBLIC_KEY`. The safety gate correctly prevented public payments and real payouts.
- `broker_account_not_ready` means no verified execution account was available; no broker order was placed. Real execution remains fail-closed.

## Database and migration status

No migration is required. The sole Alembic head remains:

`0027_launch_paper_trading`

## Deployment identity

Expected boot markers:

- `SignalRankAI v1.2.9`
- `release=v1.2.9-lifecycle-profile-observability-hotfix-20260730`
