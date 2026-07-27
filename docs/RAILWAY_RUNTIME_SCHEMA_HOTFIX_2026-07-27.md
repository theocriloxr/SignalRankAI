# SignalRankAI 1.0.4 Railway Runtime Schema Hotfix

This release adds Alembic revision `0023_signal_runtime_schema` after Railway
proved that the clean migration chain reached revision 0022 while omitting the
`signals.mfe_pct` and `signals.mae_pct` columns required by the canonical ORM.
The revision is idempotent, preserves data, repairs `performance_version`,
reconciles duplicate active theses, and recreates the partial unique guard.

Readiness and deployment diagnostics now validate the runtime columns and use
PostgreSQL catalog semantics for the partial unique index instead of matching a
fragile textual `pg_indexes.indexdef` representation.
