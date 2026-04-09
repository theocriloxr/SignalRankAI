# Railway Variable Matrix

This matrix maps production variables to runtime usage and rollout criticality.

Source of truth used for this matrix:

- Runtime readiness checks in [railway_main.py](railway_main.py#L242)
- Active deployment template in [.env.production.template](.env.production.template)
- Current Alembic config in [alembic.ini](alembic.ini#L1)

## A. Mandatory Before Go-Live

| Variable | Why Required | Code Path | Recommended Value/Rule | Service Scope |
|---|---|---|---|---|
| TELEGRAM_BOT_TOKEN | Bot cannot start webhook/polling without token | [railway_main.py](railway_main.py#L251) | Telegram BotFather token | All runtime services |
| OWNER_IDS (or OWNER_TELEGRAM_ID / TELEGRAM_OWNER_ID) | Required for owner/admin command control | [railway_main.py](railway_main.py#L250) | Comma-separated Telegram IDs | Bot/Web/All |
| GEMINI_API_KEY | Required by AI analysis/runtime readiness policy | [railway_main.py](railway_main.py#L247) | Valid Gemini API key | Engine/Bot/All |
| META_API_TOKEN | Required for execution integrations/runtime readiness policy | [railway_main.py](railway_main.py#L248) | Valid Meta API token | Engine/Bot/All |
| ENCRYPTION_KEY | Required for encrypted secrets and secure state | [railway_main.py](railway_main.py#L249) | 32+ char random secret | All runtime services |
| DATABASE_PUBLIC_URL or DATABASE_URL | DB sessions, migrations, repositories | [db/session.py](db/session.py#L60) | Prefer DATABASE_PUBLIC_URL on Railway | All runtime services |
| REDIS_URL | Queue/cache/state backend for production behavior | [core/redis_state.py](core/redis_state.py#L42) | Railway Redis URL | Web/Bot/Worker/All |
| APP_BASE_URL or WEBHOOK_URL or RAILWAY_PUBLIC_DOMAIN | Required to derive Telegram webhook URL | [railway_main.py](railway_main.py#L217) | Public HTTPS base URL | Web/All |
| BYPASS_KEY | Protects admin unlock path and guardrails | [core/redis_state.py](core/redis_state.py#L305) | Long random secret | Bot/All |

## B. Strongly Recommended Baseline

| Variable | Why It Matters | Code Path | Recommended Value |
|---|---|---|---|
| RUN_MODE | Explicit process behavior per service | [main.py](main.py#L12) | all (single service) or web/bot/engine/worker |
| TELEGRAM_USE_WEBHOOK | Enforces webhook mode in Railway | [railway_main.py](railway_main.py#L667) | 1 |
| WEBHOOK_QUEUE_USE_REDIS | Enables Redis-backed webhook queue | [railway_main.py](railway_main.py#L1075) | 1 |
| DB_POOL_SIZE | Prevents DB starvation under load | [db/session.py](db/session.py#L101) | 15 |
| DB_MAX_OVERFLOW | Controls burst connection headroom | [db/session.py](db/session.py#L102) | 5 |
| DB_POOL_TIMEOUT_SECONDS | Backpressure behavior on saturation | [db/session.py](db/session.py#L103) | 30 |
| DB_POOL_RECYCLE_SECONDS | Avoid stale pooled connections | [db/session.py](db/session.py#L104) | 1800 |
| REDIS_MAX_CONNECTIONS | Redis pool protection | [core/redis_state.py](core/redis_state.py#L34) | 60 |
| REDIS_WEBHOOK_QUEUE_MAX_DEPTH | Protect webhook queue memory and latency | [core/redis_state.py](core/redis_state.py#L769) | 2000 |
| REDIS_SIGNAL_QUEUE_MAX_DEPTH | Protect signal dispatch queue | [core/redis_state.py](core/redis_state.py#L811) | 5000 |
| USER_TIER_CACHE_TTL_SECONDS | Reduces tier lookup DB pressure | [signalrank_telegram/access.py](signalrank_telegram/access.py#L21) | 60 |
| HELP_MENU_CACHE_TTL_SECONDS | Reduces help rendering overhead | [signalrank_telegram/command_access.py](signalrank_telegram/command_access.py#L482) | 300 |
| AUTO_MIGRATE | Controls startup migration behavior | [db/auto_ops.py](db/auto_ops.py#L66) | false in production |

## C. Feature-Conditional Variables

| Variable | Required When | Code Path | Notes |
|---|---|---|---|
| PAYSTACK_SECRET_KEY | PAYMENTS_ENABLED=true | [config.py](config.py#L48) | Mandatory for Paystack charge flow |
| PAYSTACK_WEBHOOK_SECRET | Paystack webhook enabled | [config.py](config.py#L49) | Must match Paystack dashboard webhook secret |
| PAYSTACK_CALLBACK_URL | Hosted callback UX flow used | [paystack/paystack.py](paystack/paystack.py#L183) | Falls back to PUBLIC_BASE_URL if absent |
| ML_MODEL_RUNTIME_STATE_KEY | ML fallback durability desired | [ml/inference.py](ml/inference.py#L48) | Keep default unless multi-model routing |
| ML_MODEL_PATH / XGBOOST_MODEL_PATH | File model load path used | [ml/inference.py](ml/inference.py#L23) | Runtime-state fallback now supported |
| X_BEARER_TOKEN | X sentiment integration enabled | [data/news.py](data/news.py#L76) | Can fallback to TWITTER_BEARER_TOKEN |
| CRYPTOCOMPARE_API_KEY | CryptoCompare provider path used | [data/fetcher.py](data/fetcher.py#L736) | Optional with Binance primary |
| OANDA_API_KEY / OANDA_ACCOUNT_ID | OANDA FX data path used | [data/providers.py](data/providers.py#L322) | Keep OANDA_PRACTICE=true for demo |
| BYBIT_API_KEY / BYBIT_API_SECRET | Bybit execution enabled | [config.py](config.py#L53) | Must remain trade-only permissions |

## D. Railway Fill Status Template

Use this as the exact checklist during deploy. Replace status with Yes/No.

| Variable | Status | Service(s) | Last Verified |
|---|---|---|---|
| TELEGRAM_BOT_TOKEN | No | all | - |
| OWNER_IDS | No | all | - |
| GEMINI_API_KEY | No | all | - |
| META_API_TOKEN | No | all | - |
| ENCRYPTION_KEY | No | all | - |
| DATABASE_PUBLIC_URL or DATABASE_URL | No | all | - |
| REDIS_URL | No | all | - |
| APP_BASE_URL or WEBHOOK_URL or RAILWAY_PUBLIC_DOMAIN | No | web/all | - |
| BYPASS_KEY | No | all | - |

## E. Verification Commands

1. Show current DB revision:
   - python -m alembic current
2. Confirm single migration head:
   - python -m alembic heads
3. Run post-deploy smoke checks:
   - python scripts/post_deploy_smoke.py
