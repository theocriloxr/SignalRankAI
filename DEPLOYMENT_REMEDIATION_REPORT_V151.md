# SignalRankAI v1.5.1 Deployment Remediation Report

## Trigger

Railway logs showed one consistent release and commit across the worker,
engine and front door, but each reported database revision
`0034_production_integrity` while the repository expected
`0038_account_security_product`.

## Cascading failures observed

- Missing `subscription_products` blocked ecosystem bootstrap.
- Missing `instruments` blocked dynamic universe discovery.
- Missing `webhook_deliveries` broke Professional webhook dispatch.
- Missing `users.public_user_id` broke paper trading, resends, free-user
  distribution and performance reconciliation.
- Engine fell back to the legacy provider universe.
- No new paper position opened.

## Repository changes

1. `scripts/assert_database_schema.py`
   - Read-only schema gate.
   - Verifies one repository head, deployed revision, required unified tables
     and `users.public_user_id`.

2. `start.sh`
   - Runs the schema gate before any database-backed process starts.
   - Dedicated engine and worker roles now fail closed instead of looping
     against missing tables.

3. `scripts/staging_migrate_and_bootstrap.py`
   - Staging-only.
   - Requires explicit acknowledgement.
   - Uses one PostgreSQL advisory lock.
   - Migrates, verifies, bootstraps and optionally certifies.

4. `scripts/controlled_migrate.py`
   - Advisory lock now prioritizes the exact same
     `DATABASE_MIGRATION_URL`/`DATABASE_DIRECT_URL` used by Alembic.

5. `scripts/database_identity.py`
   - Emits a non-secret database fingerprint and current Alembic revision.

6. `scripts/railway_finish_staging.ps1`
   - One-command Railway remediation, code upload, ordered deployment and
     evidence collection.

## Remaining external evidence

After the command succeeds, the following still require real external systems
and elapsed runtime:

- a fresh qualifying signal;
- confirmed Telegram delivery proof;
- a newly opened paper position;
- app/Telegram account-linking smoke tests;
- Paystack staging transaction and receipt;
- SMTP delivery;
- mobile push delivery;
- provider credentials for stocks, indices, FX and metals;
- load, recovery and 24-hour soak evidence.

## Local validation of this patch

- 110 deployment, migration, Railway, readiness, staging and unified-platform
  regression tests passed.
- Python compilation passed.
- Shell syntax checks passed.
- Governance validation passed for 24 documents.
- Secret scan passed with zero findings.
- Alembic reported exactly one head: `0038_account_security_product`.
- The original v1.5.1 full-suite evidence bundle is preserved unchanged.

The complete base-release validator was also attempted after the patch, but its
existing multi-batch runner did not terminate within the execution window after
printing passing batch summaries. It is not counted as new patch evidence; only
the deterministic 110-test patch suite above is claimed here.
