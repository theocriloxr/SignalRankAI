# Railway Variable Status (Prefilled)

Generated from the current .env.production.template and local process environment.

- Generated at: 2026-05-02T21:17:21.078502+00:00
- Template source: .env.production.template

## Core Matrix

| Variable | Required | Status | Source | Value Preview | Note |
|---|---|---|---|---|---|
| TELEGRAM_BOT_TOKEN | yes | MISSING | missing | - | Telegram bot auth token |
| OWNER_IDS | yes | MISSING | missing | - | Owner/admin routing and privileged commands |
| GEMINI_API_KEY | yes | MISSING | missing | - | AI runtime readiness gate |
| META_API_TOKEN | yes | MISSING | missing | - | Execution integration readiness gate |
| ENCRYPTION_KEY | yes | MISSING | missing | - | Encrypted secret/state protection |
| DATABASE_URL | no | MISSING | missing | - | Primary DB connection URL (private/internal preferred) |
| DATABASE_PRIVATE_URL | no | MISSING | missing | - | Explicit private DB connection URL override |
| DATABASE_PUBLIC_URL | no | MISSING | missing | - | Public DB proxy fallback URL |
| REDIS_URL | yes | MISSING | missing | - | Queue/cache backend |
| APP_BASE_URL | no | MISSING | missing | - | Webhook base URL fallback |
| WEBHOOK_URL | no | MISSING | missing | - | Webhook base URL source |
| RAILWAY_PUBLIC_DOMAIN | no | MISSING | missing | - | Railway domain webhook source |
| BYPASS_KEY | yes | MISSING | missing | - | Admin bypass and unlock guardrail key |
| RUN_MODE | no | MISSING | missing | - | Service mode (recommended: all/web/bot/engine/worker) |
| TELEGRAM_USE_WEBHOOK | no | MISSING | missing | - | Webhook mode toggle |
| WEBHOOK_QUEUE_USE_REDIS | no | MISSING | missing | - | Redis queue backend toggle |
| DB_POOL_SIZE | no | MISSING | missing | - | DB pooled connections |
| DB_MAX_OVERFLOW | no | MISSING | missing | - | DB overflow connections |
| REDIS_MAX_CONNECTIONS | no | MISSING | missing | - | Redis connection pool cap |
| REDIS_WEBHOOK_QUEUE_MAX_DEPTH | no | MISSING | missing | - | Webhook queue max depth |
| REDIS_SIGNAL_QUEUE_MAX_DEPTH | no | MISSING | missing | - | Signal queue max depth |
| PAYMENTS_ENABLED | no | MISSING | missing | - | Payment flow switch |
| PAYSTACK_SECRET_KEY | no | MISSING | missing | - | Paystack integration key |
| PAYSTACK_WEBHOOK_SECRET | no | MISSING | missing | - | Paystack webhook verification |
| ML_MODEL_RUNTIME_STATE_KEY | no | MISSING | missing | - | DB key for model payload durability |
| X_BEARER_TOKEN | no | MISSING | missing | - | X sentiment provider token |

## Group Checks

- Owner identity set: no
- Public webhook domain source set: no
- Database URL source set: no
- Missing required keys: 7

## Next Step

1. Fill any MISSING required keys in Railway variables.
2. Re-run: python scripts/generate_railway_prefill_sheet.py
3. Run smoke checks: python scripts/post_deploy_smoke.py
