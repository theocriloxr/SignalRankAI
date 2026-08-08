# SignalRankAI v1.5.1 — Deployment Final R4

Date: 2026-08-07
Patch level: `deployment-final-r4`
Alembic head: `0038_account_security_product`

## Live staging facts already proven

The owner-provided Railway terminal evidence on 2026-08-07 proves that the staging PostgreSQL database successfully executed the complete remaining migration chain:

`0034_production_integrity -> 0035_staging_certification -> 0036_unified_platform_identity -> 0037_unified_product_workspaces -> 0038_account_security_product`

The post-migration schema admission check also returned `PASS` with no missing required tables or columns. R4 therefore treats the staging schema migration itself as complete and idempotent.

## R4 closes the remaining repository-side deployment gaps

- Fixes the asyncpg subscription-price seed ambiguity using explicitly typed SQLAlchemy bind parameters.
- Preserves one active release price per product while retaining price history.
- Persists every canonical tier feature into `subscription_entitlements`, keeping the database catalogue aligned with the source policy.
- Verifies the seeded catalogue by reading it back from PostgreSQL before proceeding.
- Commits deterministic catalogue state before optional network discovery so provider outages cannot roll it back.
- Rejects invalid self-pair instruments and explicit non-tradable discovery records.
- Normalizes profile asset-class aliases (`fx`/`stock`) to registry classes (`forex`/`equity`).
- Adds a DB-backed structural/runtime proof command covering products, prices, entitlements, instruments, mappings, canonical identities, confirmed Telegram deliveries, paper positions, receipts, email outbox state, and duplicate groups.
- Requires every Railway application service to prove both Alembic `0038` and patch marker `deployment-final-r4` after upload.
- Adds a separate runtime certification command for fresh signal -> confirmed Telegram delivery -> paper-position evidence.
- Adds a 24-hour soak certification command using Railway logs, service status and metrics.

## One-command staging completion

From the extracted project root in PowerShell:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass -Force
railway login
railway link
railway environment staging

.\scripts\railway_finish_staging.ps1 `
  -DatabaseService "Postgres-R8Lr" `
  -AcknowledgeStagingMigration
```

Do not pass `-SkipCodeUpload` for R4 because R4 changes application and bootstrap code. The migration step is safe to rerun because staging is already at Alembic head.

## Runtime certification

After fresh staging runtime activity exists:

```powershell
.\scripts\railway_certify_staging_runtime.ps1 `
  -DatabaseService "Postgres-R8Lr" `
  -WindowHours 6
```

Add `-RequirePayment` and/or `-RequireEmail` only when those smoke tests have deliberately been exercised during the selected window.

## Soak certification

After at least 24 hours of uninterrupted R4 staging runtime:

```powershell
.\scripts\railway_certify_staging_soak.ps1 `
  -Hours 24
```

The soak command fails on schema/admission errors, missing-table/column errors, asyncpg ambiguity, fatal/task-crash patterns, unhealthy service status, or missing R4/head proof.

## Completion boundary

Repository implementation and deterministic local validation can be completed inside this archive. Real external events cannot be fabricated by source code. Production promotion still requires real runtime evidence, payment/email/provider credentials as applicable, elapsed soak time, backup/restore and failover drills, security review, and legal/compliance approval. No fixed trading win rate is claimed.
