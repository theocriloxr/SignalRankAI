# SignalRankAI Railway Migration Recovery Report

## Incident

Railway stopped the pre-deploy phase while upgrading `0014_add_outcome_pnl_pct` to `0015_active_signal_guard`. PostgreSQL rejected creation of `ix_signals_active_thesis` because legacy rows contained duplicate active theses. The reported duplicate key was `(BNBUSDT, short, 1h)`.

## Root cause

Revision 0015 attempted to enforce uniqueness before reconciling legacy data. It also attempted to create an index containing `signal_deliveries.sent_ok` before that column existed in the canonical Alembic chain. Startup repair code had masked this schema-order problem in some environments.

## Fix

1. Revision 0015 now reconciles duplicate active rows before creating the unique index.
2. Reconciliation is deterministic and evidence-aware.
3. Only duplicate `status` values change to `superseded`; no row is deleted or archived.
4. Every reconciliation is recorded in `admin_events`.
5. Revision 0017 now adds the delivery proof/attempt columns before later indexes use them.
6. Revision 0022 rechecks the invariant and is now the sole migration head.
7. Deployment diagnostics verify zero active duplicate groups and a valid unique partial index.
8. `scripts/repair_active_signal_duplicates.py` provides a dry-run-first operational fallback.

## Verification

- Pytest: 737 passed, 1 skipped, 0 failed.
- Python compilation: passed.
- Production readiness: passed.
- Schema audit: 22 revisions, one head (`0022_active_guard_reconcile`).
- Core complete-system orchestrator: passed.
- Repository proof manifest regenerated.

## Deployment expectation

The next Railway pre-deploy should proceed from revision 0014 through revision 0022. The migration will retain one canonical active row for each duplicate thesis and preserve all historical evidence.
