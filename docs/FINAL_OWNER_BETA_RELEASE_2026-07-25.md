# SignalRankAI Final Owner-Beta Release — 2026-07-25

## Release status

This build is ready for a controlled owner-only Railway soak after deployment verification. It is not permission to enable public paid access, real-money execution, copy trading, payouts, or production ML learning. Those stages require live delivery and outcome evidence from the deployed environment.

## Production failures corrected

1. **False portfolio exposure lock:** the exposure query now binds naïve UTC to the database's `TIMESTAMP WITHOUT TIME ZONE` column. A SQL telemetry failure can no longer starve advisory/manual signals; Redis is used as fallback truth, while automated execution remains fail-closed.
2. **Rejected-signal DB contention:** rejection evidence is queued in a bounded in-process spool and committed in batches through the background database lane. Deferred batches are restored rather than discarded.
3. **WebSocket restart thrashing:** cancellation is handled correctly, feeder failures cause immediate provider failover, and CryptoCompare ticker/trade events now build candles. The initial owner-beta profile remains REST-first with WebSocket ingestion disabled.
4. **Background work misreported as failure:** expected database admission deferrals no longer inflate error metrics or appear as free-distribution failures.
5. **Waitlist scheduler import ambiguity:** Railway explicitly imports the `web.app` module, and waitlist jobs use the background database lane.
6. **Monolith analytics contention:** ML archive backfill, model training, drift monitoring, shadow outcomes, and asset learning stay off in the live monolith and belong to a separate analytics service.
7. **Import-time network and ML work:** asset-universe background refresh is opt-in, and the `ml` package lazily imports training modules.
8. **Package shadowing:** the obsolete local `telegram/` package was moved to `legacy_telegram/`, so it cannot mask the required `python-telegram-bot` dependency.
9. **XGBoost CPU pressure:** the production model loader now applies the configured native thread cap.
10. **Operational noise:** market-closure and cache-staleness logs are classified more accurately; macro Yahoo aliases are mapped explicitly.

## Fast owner-beta configuration

Deploy with `deploy/railway_roles/monolith_safe.env`. It intentionally starts with:

- crypto only;
- 18-asset universe;
- REST providers Coinbase and OKX;
- WebSocket ingestion disabled;
- owner-only delivery;
- two PgBouncer connections with no overflow;
- ML, shadow learning, drift monitoring, and archive backfill disabled;
- real execution, copy trading, payouts, public payments, and free random distribution disabled.

Do not increase the monolith database pool to compensate for contention. Keep foreground delivery fast by batching telemetry and moving analytics into its own Railway service.

## One-command verification

Run from the repository root:

```bash
python scripts/verify_owner_beta_release.py
```

When the local machine lacks optional test dependencies:

```bash
python scripts/verify_owner_beta_release.py --skip-tests
```

The second command verifies source, schema, session API, architecture, governance, secrets, readiness, and all environment profiles, but it does not replace the regression tests.

## Railway deployment sequence

1. Preserve secret variables already stored in Railway.
2. Replace conflicting non-secret values with `deploy/railway_roles/monolith_safe.env`.
3. Use `bash start.sh` as the start command.
4. Set `AUTO_MIGRATE=1` for the first deployment only if migration `0021_runtime_truth_hardening` has not already been applied. After the migration succeeds, return it to `0` and redeploy.
5. Verify `/healthz` returns HTTP 200 and the Telegram webhook reports `pending=0` with no last error.
6. Run `python scripts/post_deploy_smoke.py --base-url <RAILWAY_URL> --skip-webhook`.
7. Send one owner-only signal and trace the same signal ID through the lifecycle gate below.
8. Run `python scripts/live_production_evidence.py --days 7 --provider-smoke` from an environment with the production database variables.
9. Keep the service in owner-only advisory mode for at least a full 24-hour soak.

## Required same-signal lifecycle evidence

For one signal ID, collect proof of every step:

1. signal stored;
2. delivery reservation created;
3. Telegram send succeeded;
4. `signal_deliveries.sent_ok=true`;
5. Telegram chat ID and message ID persisted;
6. active message persisted;
7. lifecycle changed to `WATCHING_FOR_ENTRY`;
8. entry touch detected from valid market data;
9. terminal outcome persisted;
10. outcome notification sent.

A generated score or database signal row alone is not a successful production signal.

## Expansion order after the clean soak

1. Increase the crypto universe from 18 to 30 only if cycle duration, database admission, and delivery latency remain stable.
2. Enable WebSocket ingestion only after confirming provider traffic is continuous and restart-free.
3. Add FX and commodities next.
4. Add stocks and indices during their real market sessions.
5. Create a separate Railway analytics service using `deploy/railway_roles/analytics.env`.
6. Enable model training only after at least 100 delivery-proof-backed live outcomes exist.
7. Enable public tiers only after delivery and outcome reconciliation remain correct under load.
8. Treat real-money execution and copy trading as a separate security and risk release, not a normal feature toggle.

## Logs that block release

Any recurrence of these patterns blocks expansion:

- `can't subtract offset-naive and offset-aware datetimes`;
- exposure-limit rejection immediately after an exposure-query exception;
- `stored=0` for every viable candidate over multiple complete cycles;
- `Rejection log dropped because DB gate is busy`;
- free distribution deferral logged as an error;
- WebSocket supervisor restart loops;
- synthetic/bootstrap data used for production model training;
- missing Telegram message IDs after a claimed successful delivery.

## Validation completed in the isolated workspace

- focused production regression suite: passed;
- dependency-independent test sweep: 274 passed, 1 skipped;
- Python compilation: passed;
- schema audit: 21 revisions, one head (`0021_runtime_truth_hardening`);
- database-session API audit: no legacy call sites;
- architecture smoke test: passed;
- governance validation: passed;
- secret scan: passed;
- production-readiness checks: passed;
- environment-contract validation: all release profiles valid.

The isolated workspace could not install the production `python-telegram-bot`, APScheduler, asyncpg, Redis, and Google GenAI dependencies, so a complete connector/integration suite was not claimed here. Railway must still supply the final live evidence.
