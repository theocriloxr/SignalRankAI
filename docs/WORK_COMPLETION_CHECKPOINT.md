# Work Completion Checkpoint

Generated: 2026-07-26

Status: **CODE_FIXED_AND_HERMETICALLY_VERIFIED — LIVE RAILWAY PROOF PENDING**

- Latest incident addressed: Railway migration 0015 failed because legacy duplicate active signals prevented creation of `ix_signals_active_thesis`.
- Migration 0015 now preserves every row and all related delivery/outcome history, deterministically retains one canonical active thesis, and changes only duplicate statuses to `superseded`.
- Forward migration head: `0022_active_guard_reconcile`.
- Deployment diagnostics now verify zero duplicate active thesis groups and the presence of the unique partial index.
- A dry-run-first operational fallback exists at `scripts/repair_active_signal_duplicates.py`.
- No signal rows are deleted by the migration or fallback repair.

## Next executable tasks

1. Run the full hermetic test suite and complete-system orchestrator on the final source.
2. Package the final source ZIP, patch, evidence report, and SHA-256 checksums.
3. Deploy the exact release to isolated Railway staging.
4. Confirm Alembic upgrades from the current database revision to `0022_active_guard_reconcile`.
5. Retrieve `/readyz` and the protected deployment diagnostics report.
6. Prove Telegram webhook ingestion, one same-signal lifecycle, restart recovery, Redis recovery, and the 24–72-hour soak.

## Resume commands

```bash
PYTHONPATH=/mnt/data/sra_test_stubs:. SIGNALRANK_DISABLE_BACKGROUND_THREADS=1 pytest -q
python -m compileall -q .
python scripts/production_readiness_check.py
python scripts/run_complete_system_test.py --full --output-dir artifacts/complete-system-test
```

For a manual database-only inspection before redeployment:

```bash
python scripts/repair_active_signal_duplicates.py
```

Apply only when explicitly needed after reviewing the dry-run output:

```bash
python scripts/repair_active_signal_duplicates.py --apply
```
