# SignalRankAI v1.5.1 Deployment Completion Hotfix R3

Observed staging evidence on 2026-08-07 proved that Alembic successfully advanced
from `0034_production_integrity` through `0038_account_security_product` and the
schema admission check passed. The remaining blocker was the ecosystem bootstrap:
asyncpg rejected the `subscription_prices` seed statement because the same bind
parameter was inferred as both PostgreSQL `text` and `varchar`.

R3 explicitly casts the reused `product_id` bind to `VARCHAR(64)`, the price to
`BIGINT`, and the currency literal to `VARCHAR(8)`. This removes the ambiguous
parameter inference without changing the subscription catalogue semantics.

Because the database is already at Alembic head, rerunning the staging completion
workflow is safe: migration is a no-op and bootstrap resumes against the completed
schema. R3 should be uploaded to all three application services (do not use
`-SkipCodeUpload`) so the worker's recurring bootstrap uses the corrected query.
