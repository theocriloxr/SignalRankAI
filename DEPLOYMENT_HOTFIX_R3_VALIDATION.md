# SignalRankAI v1.5.1 Deployment Hotfix R3 Validation

Date: 2026-08-07

## Staging evidence addressed

- Alembic migration successfully advanced from `0034_production_integrity` to `0038_account_security_product`.
- Schema admission passed with all required unified-platform tables and columns present.
- Ecosystem bootstrap then failed in `seed_subscription_catalogue()` with asyncpg `AmbiguousParameterError` because `:product_id` was inferred as both `text` and `varchar` in the same raw SQL statement.

## R3 remediation

- Explicitly casts `:product_id` as `VARCHAR(64)` in both the insert projection and predicate.
- Explicitly casts `:price_kobo` as `BIGINT`.
- Explicitly casts the NGN currency literal as `VARCHAR(8)`.
- Adds a regression test preventing the ambiguous SQL form from returning.

## Local validation

- Deployment/migration/unified-platform regression suite: 104 passed.
- Python compileall: PASS.
- Alembic heads: exactly one, `0038_account_security_product`.
- Secret scan: PASS, findings=0.

## Required staging action

Rerun `scripts/railway_finish_staging.ps1` from this R3 source **without** `-SkipCodeUpload` so all three Railway application services receive the corrected bootstrap query. The database is already at head, so the Alembic upgrade is idempotent/no-op before bootstrap resumes.
