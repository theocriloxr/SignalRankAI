# SignalRankAI v1.5.1 staging migration hotfix R2

This hotfix corrects two staging-deployment issues discovered from the 2026-08-07 Railway migration attempt:

1. Raw `psycopg2.connect()` was incorrectly given a SQLAlchemy driver URL (`postgresql+psycopg2://...`). Raw psycopg2 now receives a canonical `postgresql://...` DSN while Alembic/SQLAlchemy retains its driver-qualified URL.
2. `railway run` executes locally and therefore cannot reliably connect to `*.railway.internal`. The PowerShell staging workflow now reads the Postgres service `DATABASE_PUBLIC_URL` for the local one-owner migration only. Deployed application services continue using the private `${{Postgres-R8Lr.DATABASE_URL}}` reference.

Run from the repository root in PowerShell:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass -Force
.\scripts\railway_finish_staging.ps1 -DatabaseService "Postgres-R8Lr" -AcknowledgeStagingMigration -SkipCodeUpload
```

The expected migration target is `0038_account_security_product`.
