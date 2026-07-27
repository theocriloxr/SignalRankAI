# Railway clean-database migration hotfix

**Release:** SignalRankAI 1.0.3  
**Incident date:** 2026-07-27

## Symptom

A clean Railway PostgreSQL database upgraded successfully through revision 0014,
then revision `0015_active_signal_guard` failed with:

```text
psycopg2.errors.UndefinedColumn: column s.status does not exist
```

## Root cause

Revision 0001 created `signals` without the lifecycle `status` column. Legacy
databases often already contained that column, so the omission was hidden until a
true clean-database migration. Revision 0015 was the first migration that queried
and indexed `signals.status`.

## Resolution

Revision 0015 now establishes `signals.status VARCHAR(16) NOT NULL DEFAULT
'issued'` idempotently before reconciliation and index creation. Existing status
values are preserved; only unexpected NULL values are repaired to `issued`. The
change supports PostgreSQL online migrations and Alembic offline SQL generation.

The provider-certification script also adds the repository root to `sys.path` so
it can be executed directly by deployment diagnostics.

## Retry safety

PostgreSQL transactional DDL rolled back the failed migration. Redeploying the
corrected release should restart the clean chain safely; do not stamp the Alembic
revision or manually create the index.
