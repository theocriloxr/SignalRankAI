# SignalRankAI v1.5.1 Staging Terminal Completion

This deployment patch addresses the August 6, 2026 staging failure where all
three application services ran release `v1.5.1`, while PostgreSQL remained at
Alembic revision `0034_production_integrity` instead of
`0038_account_security_product`.

## What the patch adds

- A read-only startup schema admission gate for every database-backed runtime.
- A staging-only, advisory-locked migration and ecosystem bootstrap command.
- A non-secret database identity fingerprint command.
- A PowerShell Railway orchestrator that:
  - sets one PostgreSQL reference on all three services;
  - keeps execution, copy trading, transfers and public payments disabled;
  - applies migrations through one owner;
  - verifies all services resolve to the same PostgreSQL database;
  - uploads the patched source in worker → engine → front-door order;
  - rejects logs containing stale-schema errors;
  - stores local deployment evidence.
- A correction to production migration locking so the advisory lock and
  Alembic always target the same direct migration database.

## Required command

Run from the extracted repository root in PowerShell after installing and
logging into Railway CLI:

```powershell
.\scripts\railway_finish_staging.ps1 -AcknowledgeStagingMigration
```

When the PostgreSQL service is not named `Postgres`, pass its exact name:

```powershell
.\scripts\railway_finish_staging.ps1 `
  -DatabaseService "YOUR_POSTGRES_SERVICE_NAME" `
  -AcknowledgeStagingMigration
```

The script auto-detects PostgreSQL when its Railway service name contains
`postgres` or `postgresql`.

## Alternate service names

```powershell
.\scripts\railway_finish_staging.ps1 `
  -WorkerService "SignalRankAI" `
  -EngineService "striking-optimism" `
  -FrontdoorService "bountiful-miracle" `
  -DatabaseService "Postgres" `
  -Environment "staging" `
  -AcknowledgeStagingMigration
```

## Existing source already uploaded

Use `-SkipCodeUpload` only when the deployment already contains this patch. It
redeploys the latest image instead of uploading the local source:

```powershell
.\scripts\railway_finish_staging.ps1 `
  -DatabaseService "Postgres" `
  -AcknowledgeStagingMigration `
  -SkipCodeUpload
```

## Evidence

The command creates:

```text
deployment_evidence/<timestamp>/
```

with:

- migration evidence;
- database fingerprints;
- logs for all three services;
- staging certification output;
- a deployment summary.

The infrastructure/schema stage is successful only when:

- all services report `0038_account_security_product`;
- database fingerprints match;
- no `UndefinedTableError` or `UndefinedColumnError` remains;
- no missing `subscription_products`, `instruments`, `webhook_deliveries`, or
  `users.public_user_id` errors remain.

Fresh-signal delivery, a newly opened paper position, Paystack staging payment,
email delivery and the 24-hour soak are runtime evidence and cannot be produced
by repository code alone.

## Production warning

The PowerShell command refuses production. Production migrations must use:

```bash
python scripts/controlled_migrate.py
```

with verified backup evidence, approved exact commit and the production
migration URL.
