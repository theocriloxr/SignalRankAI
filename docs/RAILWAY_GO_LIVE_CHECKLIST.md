# Railway Go-Live Checklist (Zero-Downtime)

This checklist is for rolling out SignalRankAI safely on Railway with Redis-backed webhook queueing and DB migration controls.

## 1. Pre-Deploy Gate (must pass)

1. Confirm branch state is clean and tests are green.
2. Run migration dry-check locally:
   - python -m alembic current
   - python -m alembic heads
3. Ensure .env.production.template values are mapped in Railway variables.
4. Verify these mandatory variables are set:
   - TELEGRAM_BOT_TOKEN
   - OWNER_IDS (or OWNER_TELEGRAM_ID / TELEGRAM_OWNER_ID)
   - GEMINI_API_KEY
   - META_API_TOKEN
   - ENCRYPTION_KEY
   - DATABASE_URL (or DATABASE_PRIVATE_URL / DATABASE_PUBLIC_URL)
   - REDIS_URL
   - One public base URL source: APP_BASE_URL or WEBHOOK_URL or RAILWAY_PUBLIC_DOMAIN

## 2. Deployment Strategy

Use a two-step rollout to avoid downtime from migration and webhook restarts.

1. Keep AUTO_MIGRATE=false.
2. Deploy code first with existing schema compatibility.
3. Run migrations as a controlled one-off command:
   - python -m alembic upgrade head
4. Validate schema and app health endpoints.
5. Shift traffic to new deployment (Railway does this during successful deploy readiness).

## 3. Railway Variables Baseline

Mandatory for production:

- RUN_MODE=all
- TELEGRAM_USE_WEBHOOK=1
- WEBHOOK_QUEUE_USE_REDIS=1
- DB_POOL_SIZE=5
- DB_MAX_OVERFLOW=3
- REDIS_MAX_CONNECTIONS=60
- REDIS_WEBHOOK_QUEUE_MAX_DEPTH=2000
- REDIS_SIGNAL_QUEUE_MAX_DEPTH=5000

Recommended:

- DB_POOL_TIMEOUT_SECONDS=30
- DB_POOL_RECYCLE_SECONDS=1800
- DB_CONNECT_MAX_ATTEMPTS=12
- DB_CONNECT_BACKOFF_SECONDS=2
- USER_TIER_CACHE_TTL_SECONDS=60
- HELP_MENU_CACHE_TTL_SECONDS=300
- ML_MODEL_RUNTIME_STATE_KEY=ml:model:primary

## 4. Smoke Tests (immediately after deploy)

Run one command first:

- python scripts/post_deploy_smoke.py

1. Health checks:
   - GET /health
   - GET /ready
2. Telegram webhook:
   - Ensure webhook is set and updates are flowing.
   - Verify queue depth remains below 80% of REDIS_WEBHOOK_QUEUE_MAX_DEPTH.
3. Command access:
   - /help renders tier-appropriate command list.
   - Owner/admin commands are blocked for non-privileged users.
4. Broker key validation endpoint:
   - Confirm trade-only keys pass.
   - Confirm withdraw/transfer-enabled keys are rejected.
5. Outcome tracking:
   - Validate canonical_outcome / vip_fill_outcome / sentiment_outcome persistence for a recent signal.

## 5. Observability Gate

During first 30-60 minutes:

1. Watch logs for:
   - missing env vars warning from railway runtime readiness log
   - Redis queue enqueue/dequeue failures
   - DB pool timeout spikes
2. Watch metrics:
   - webhook queue depth
   - webhook queue utilization
   - error rate and p95 webhook handling duration

## 6. Rollback Plan

If any critical gate fails:

1. Disable ingress pressure quickly:
   - Temporarily set WEBHOOK_QUEUE_USE_REDIS=0 only if Redis path is unstable.
2. Revert deployment to previous known-good Railway release.
3. If migration caused incompatibility:
   - Stop traffic to failing revision.
   - Apply rollback migration only if explicitly tested; otherwise restore previous app revision and keep upgraded schema if backward compatible.
4. Re-run smoke tests on rolled-back revision.

## 7. Post-Go-Live Hardening

1. Rotate BYPASS_KEY and other high-risk secrets after successful cutover.
2. Enable SENTRY_DSN if still disabled.
3. Schedule weekly check:
   - queue depth headroom
   - DB pool saturation
   - outcome-tracker lag and ML retrain cadence
