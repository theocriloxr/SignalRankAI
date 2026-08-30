# Railway Alembic URL Hotfix

**Date:** 2026-07-27  
**Release:** SignalRankAI 1.0.1  
**Incident:** Railway pre-deploy migration failed with
`sqlalchemy.exc.NoSuchModuleError: Can't load plugin: sqlalchemy.dialects:postgres`.

## Root cause

Railway supplied a legacy PostgreSQL connection string beginning with
`postgres://`. SQLAlchemy 2 no longer recognises `postgres` as a dialect plugin
name; it expects the canonical `postgresql` dialect. The runtime database layer
already normalised Railway URLs, but the synchronous Alembic environment did
not normalise this legacy form.

## Fix

`db/migrations/env.py` now passes every configured migration URL through the
pure helper `db.database_urls.normalize_sync_postgres_url`. The helper converts:

- `postgres://` → `postgresql+psycopg2://`
- `postgresql://` → `postgresql+psycopg2://`
- `postgresql+asyncpg://` → `postgresql+psycopg2://`
- `postgresql+psycopg://` → `postgresql+psycopg2://`

Alembic is synchronous and the repository declares `psycopg2-binary`, so the
explicit `psycopg2` driver is used for migration connections. Query parameters,
credentials, host, port, and database name are preserved.

## Verification

- Railway-style URL regression tests: pass.
- Migration revision and idempotency tests: pass.
- Alembic offline upgrade generated the complete SQL chain through
  `0022_active_guard_reconcile` using a `postgres://` input URL.
- One Alembic head confirmed: `0022_active_guard_reconcile`.

## Railway configuration

Keep:

```env
DATABASE_URL=${{PgBouncer.DATABASE_URL}}
DATABASE_MIGRATION_URL=${{Postgres.DATABASE_URL}}
```

No manual URL rewriting or plaintext database credential duplication is
required after this hotfix.

## Pre-deploy diagnostics hardening

The same pass also corrected `scripts/compile_tracked_python.py`. It now prefers
`git ls-files` when Git metadata exists, but deterministically scans project
Python files when Railway or a release ZIP has no `.git` directory. Virtual
environments, caches, logs, evidence directories, and generated runtime state
remain excluded. This prevents the strict pre-deploy diagnostic from failing
immediately after a successful migration.
