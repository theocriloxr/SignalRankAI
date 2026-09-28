# Staging PostgreSQL Backup/Restore Drill — 2026-09-27

Status: **PASS**

Railway deployment: `59a52067-b83f-46bb-83f6-67080b818c7d`  
Source commit: `25ac2b0660ce912a8c2143417002d5653f0ff646`

## Safety boundary

- Source environment: staging only.
- Production mutation: false.
- Source database mutation: false.
- Live execution during drill: false.
- Restore target: isolated temporary database.
- Restore target cleanup: PASS.

## Dump evidence

- Source database logical name: `railway`.
- Dump size: **199,493,675 bytes**.
- Dump duration: **68.845 seconds**.
- Dump SHA-256:
  `38abd7db4f76c88f5f36ec678457741d02e97c9bac00c193742cf2e3b48ac20f`.

## Restore evidence

- Temporary target:
  `signalrank_restore_drill_20260927_141749_1`.
- Restore duration: **297.755 seconds**.
- Total drill duration: **388.782 seconds**.
- Restored Alembic head:
  `0045_mt5_credential_retirement`.
- Expected Alembic head:
  `0045_mt5_credential_retirement`.
- Ledger immutability trigger restored: **true**.

## Critical data checks

All nine critical tables checked by the drill were readable after restore.
Representative restored row counts:

- `signals`: **48,132**
- `users`: **6**
- `broker_connections`: **0**
- `broker_executions`: **0**
- `mt5_executions`: **0**
- `broker_reconciliation_state`: **0**
- `broker_execution_decisions`: **0**
- `trading_account_ledger_entries`: **0**
- `trading_account_policies`: **0**

Zero account/trading rows reflect the staging snapshot at drill time; they are
not synthesized success values.

## Cleanup

After verification, the target database was dropped outside the verification
transaction and cleanup was independently confirmed. Final runtime marker:

`STAGING_BACKUP_RESTORE_DRILL_PASS`

This proves the staging backup/restore mechanism. It does not authorize
production rollout or real-money execution.
