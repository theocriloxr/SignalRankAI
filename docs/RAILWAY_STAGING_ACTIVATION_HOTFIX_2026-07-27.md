# Railway staging activation hotfix — 2026-07-27

**Release:** SignalRankAI 1.0.2

This hotfix addresses the staging deployment that reached Alembic head but remained
unavailable behind Railway because `/readyz` returned 503.

## Changes

- Railway's generated `RAILWAY_PUBLIC_DOMAIN` is now authoritative for webhook
  registration and runtime probes, preventing copied production URLs from being
  used by staging.
- Production/Railway Telegram webhook registration is fail-closed until
  `DATABASE_URL`, state Redis, a distinct delivery Redis, and
  `TELEGRAM_WEBHOOK_SECRET` are configured. The existing webhook is left
  unchanged when the deployment cannot durably accept updates.
- `httpx` and `httpcore` INFO request logs are suppressed because Telegram bot
  tokens are embedded in Bot API request URLs.
- Post-deploy diagnostics and smoke tools use the current Railway domain before
  any explicit fallback URL.

## Required Railway variables

```env
DATABASE_URL=${{PgBouncer.DATABASE_URL}}
DATABASE_MIGRATION_URL=${{Postgres.DATABASE_URL}}
REDIS_URL=${{RedisState.REDIS_URL}}
STATE_REDIS_URL=${{RedisState.REDIS_URL}}
DELIVERY_REDIS_URL=${{RedisDelivery.REDIS_URL}}
REQUIRE_DISTINCT_DELIVERY_REDIS=1
TELEGRAM_WEBHOOK_SECRET=<new-random-secret>
API_TOKEN_PEPPER=<new-random-pepper>
```

Remove or correct copied production values for `APP_BASE_URL`, `WEBHOOK_URL`, and
`WEBHOOK_DOMAIN` in staging.
