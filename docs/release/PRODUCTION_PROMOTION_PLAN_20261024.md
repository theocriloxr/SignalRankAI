# Production promotion plan — 24 October 2026

**Status: prepared, not executed.** Promotion needs the owner's exact phrase `PROMOTE_TO_PRODUCTION` (AGENTS.md, CX-AUTH-01). Live trading, automatic execution, copy trading, payouts and live payments stay disabled whatever happens here; this plan does not change any financial permission.

## What would change

| Item | Today (production) | After promotion |
| --- | --- | --- |
| Code on `fix/provider-discovery-readiness-20260923` | `9865a3d1` | Fast-forward to the feature branch head (no divergence; more than 450 commits as of 28 Oct — recount at promotion time) |
| Database revision | `0053_research_market_inputs` | `0056_ai_usage_ledger` (was `0055` until 28 Oct) |
| Services that redeploy on push | `SignalRankAI`, `signalrankai-analytics-prod`, `striking-optimism`, `bountiful-miracle` | same, all at once (watch pattern `**`) |
| Public web (`SignalRankAI-Public-Web`) | tracks `fix/release-recovery-20261008` | **unchanged** — the rebuilt frontend is not served until this service is pointed at the promoted branch (Railway setting, owner action) |

### Migrations

- `0054_shadow_pending_index` — `CREATE INDEX CONCURRENTLY` on `decision_log`; no locks on writes, no data change. Downgrade drops the index.
- `0055_user_renewal_default` — changes the **default** of `users.auto_renew` from `TRUE` to `FALSE`. Existing users are untouched; **new sign-ups will no longer auto-renew unless they opt in** (Stage 1 recurring-consent requirement). This is a billing behavior change for new accounts — confirm it is wanted.
- `0056_ai_usage_ledger` (added 28 Oct) — creates `ai_usage_ledger` and `ai_budget_alerts`, append-only by trigger; touches no existing table, so no locks on live data. Its downgrade refuses once the ledger holds rows (spend history is evidence). Every `EXPECTED_ALEMBIC_HEAD` must be `0056_ai_usage_ledger`.

### Behavior the owner asked to keep

Cooldowns, duplicate detection and XAUTUSDT handling are unchanged and locked by `tests/test_owner_decisions_20261024.py`. The focused universe is opt-in and refuses to enable in production. Region-blocked Binance calls back off instead of retrying.

## Why a plain push is unsafe

Every database-backed service runs `scripts/assert_database_schema.py` at boot and **refuses to start unless the database is exactly at the code's Alembic head**. Pushing code at `0055` while the database is at `0053` would make the new deployments fail at boot: a service with a Railway healthcheck keeps its old deployment, but roles without one (engine, worker) crash-loop and stop working. Migrations must therefore be applied by the guarded migration role in the same release window.

Separately, `start.sh` runs `scripts/assert_release_source.py` on every Railway service: a process exits with code 79 unless `EXPECTED_RELEASE_BRANCH` matches `RAILWAY_GIT_BRANCH` and `EXPECTED_RELEASE_COMMIT` matches `RAILWAY_GIT_COMMIT_SHA`. Each service's `EXPECTED_RELEASE_COMMIT` must be set to the new full SHA before the push, or the new deployments will refuse to start.

## Steps (owner-authorized window)

1. **Backup.** Take a Railway PostgreSQL backup and confirm a restore of it into a scratch database. Record `PRODUCTION_DB_BACKUP_ID`, `PRODUCTION_DB_BACKUP_CREATED_AT` (ISO-8601, under 24 h old) and `PRODUCTION_DB_BACKUP_VERIFIED=1` on the migration-role service. `scripts/controlled_migrate.py` refuses to migrate without them. *(Added 27 Oct after a local rehearsal:)* it also refuses without `PRODUCTION_DB_VOLUME_SIZE_MB` (the Railway volume capacity) and `PRODUCTION_DB_VOLUME_OBSERVED_AT` (ISO-8601, under **one hour** old, so set it at the start of the window), and it reads `pg_ls_waldir()`, which needs a superuser or `pg_monitor` connection. Rehearsal evidence: `evidence/continuation-20261027/migration_rehearsal_0053_0055.json`.
2. **Engine diagnosis first.** *(Done 28 Oct, read-only: the engine loop hung at 2026-10-22 08:08:30 UTC when Postgres was redeployed and the process stayed Online; restarting `striking-optimism` is the immediate remedy, and the promoted code adds a stall watchdog that exits a dedicated engine so it restarts itself.)* Production readiness is 503 because the engine heartbeat is absent (engine not cycling). Read the engine service logs before the release so the cause is known; a deploy may not fix it.
3. **Approve the source.** Set `EXPECTED_RELEASE_COMMIT` to the full SHA being promoted on all four services (and the migration role). Leave `EXPECTED_RELEASE_BRANCH` as `fix/provider-discovery-readiness-20260923`. Never disable `RELEASE_SOURCE_GATE_ENABLED`.
4. **Push** the feature branch head to `fix/provider-discovery-readiness-20260923` as a fast-forward (no force).
5. **Migrate** with the migration-owner role (`SERVICE_ROLE=migration`), which holds the advisory lock and writes migration evidence. Do not set `RUN_DB_MIGRATIONS_AT_BOOT` on several services at once.
6. **Verify** read-only: `/version` shows the new SHA and `0055`; `/readyz` passes or names only the engine heartbeat; Engine Pulse records a cycle; a test account can sign in, open Settings, export data; Telegram `/start` replies.
7. **Point the public web service** at the promoted branch if the rebuilt frontend should go live; verify `/login`, `/app`, theme switching and checkout availability.

## Rollback

- **Code:** redeploy the previous Railway deployment (`9865a3d1`). This only works while the database is still at `0053`; after step 5 the old code's schema gate will refuse `0055`.
- **Schema:** `alembic downgrade 0053_research_market_inputs` reverses both migrations (drops the index, restores the `TRUE` default). Accounts created during the window keep `auto_renew=FALSE`; that is the consent-safe value and is not reverted.
- **Data:** restore the step-1 backup only if data loss is proven, with explicit authorization.

## Changes added on 27–28 October that a promotion would also deploy

- Nixpacks gains a `[phases.build]` step writing `.build-timestamp` (`|| true`, cannot fail a build).
- Dependency upgrades: Next.js 16.4.2 (public web only after repointing), aiohttp 3.14.5, certifi 2026.10.19, OpenTelemetry 1.45.1, Pillow 13.0.0.
- New owner-only endpoints: scoped kill switches and reviewed account merges. HSTS (`max-age=31536000`, no subdomains) on HTTPS responses; `SECURITY_HSTS_ENABLED=0` turns it off on the API.
- No new migration: the head is still `0055`.

## Known limits at promotion time

- Evidence is local only: GitHub Actions is billing-locked, there is no staging environment, and no live provider, broker or Paystack test keys were exercised.
- Requirement status: 8 verified locally, 248 partially verified, 20 blocked, 7 awaiting approval, 5 not implemented (`evidence/continuation-20261024/cx_assessment.json`).
- Production `/version` reports unknown build metadata (CX-OBS-03); set it in the build so the deployed SHA can be proven. From `bd257421` the promoted code reports its own Alembic head as `schema_head` without configuration.
- 27 Oct local rehearsal (PostgreSQL 17, synthetic production-shaped data): `0053 → 0055 → 0053 → 0055` with plain Alembic and `0053 → 0055` through `controlled_migrate.py` all passed; existing `auto_renew` values unchanged. Not a measurement of production size or live write load.
