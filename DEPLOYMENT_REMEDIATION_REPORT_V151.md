# SignalRankAI v1.5.1 Deployment Remediation Report — Final R4

## Trigger and live progression

The first Railway v1.5.1 deployment correctly exposed a schema mismatch: all
application services expected `0038_account_security_product` while the real
staging PostgreSQL database was still at `0034_production_integrity`.

Repository fail-fast admission was added so services stopped instead of running
against a partial schema. The owner then ran the controlled staging migration.
The supplied terminal evidence proves the real staging database successfully
executed `0034 -> 0035 -> 0036 -> 0037 -> 0038`, followed by a schema admission
`PASS` with no missing required objects.

The next real staging blocker was therefore isolated to post-migration ecosystem
bootstrap: asyncpg could not infer one reused subscription-price parameter as
both PostgreSQL `text` and `varchar`.

## Final R4 repository remediation

1. **Typed, rerunnable subscription catalogue**
   - Subscription-price product IDs use explicit `VARCHAR(64)` bind types.
   - Prices use explicit `BIGINT` bind types.
   - A history-preserving two-step update/upsert keeps one active release price.

2. **Complete entitlement persistence**
   - All canonical tier features are persisted as `feature.<name>` entitlement
     rows in addition to operational control entitlements.
   - PostgreSQL read-back verification prevents a partial catalogue from being
     reported as bootstrapped.

3. **Transactional bootstrap boundaries**
   - Deterministic products, entitlements, strategy and ML governance state is
     verified and committed before network discovery.
   - Provider/network failure therefore cannot roll deterministic catalogue
     state back.

4. **Instrument hardening**
   - Self-pairs such as `USDT/USDT` are rejected.
   - Explicit non-tradable provider rows cannot become tradable instruments.
   - Runtime profile aliases `fx` and `stock` map to registry classes `forex`
     and `equity`.

5. **Database-backed staging proof**
   - `scripts/staging_runtime_proof.py` verifies Alembic head, required tables,
     unified-user column, products, prices, feature/control entitlements,
     feature definitions, strategies, instruments, provider mappings and
     duplicate groups.
   - Strict mode additionally requires a recent signal, confirmed Telegram
     delivery and paper position, with optional receipt/email requirements.

6. **Railway completion and runtime certification**
   - `scripts/railway_finish_staging.ps1` performs shared DB configuration,
     idempotent migration/bootstrap, structural proof, ordered code upload and
     post-deploy log validation.
   - Every application service must prove
     `alembic_current=0038_account_security_product` and
     `patch=deployment-final-r4`.
   - `scripts/railway_certify_staging_runtime.ps1` captures strict runtime
     evidence and Railway metrics/logs.
   - `scripts/railway_certify_staging_soak.ps1` automates the 24-hour lookback
     log/status/metrics blocker scan.

## External completion boundary

No source archive can fabricate fresh market conditions, Telegram deliveries,
Paystack transactions, SMTP delivery, mobile push/store credentials, provider
contracts, elapsed 24-hour runtime, restore/failover drills, penetration-test
results, legal approval or statistically defensible trading performance.
Those are now explicit evidence gates rather than unimplemented source tasks.

Live execution, copy trading, real payouts and public payments remain disabled
through staging certification.
