# SignalRankAI Capabilities and Operations Reference

## 1. Executive Summary

SignalRankAI is a tiered signal platform with three major planes:
- Signal intelligence plane: data ingestion, indicators, strategy execution, filtering, ranking, ML scoring.
- Delivery and product plane: Telegram command UX, tier gating, scheduled sends, execution integrations, referrals and subscriptions.
- Operations plane: FastAPI health and webhook endpoints, database migrations, observability metrics, and runtime safety controls.

The codebase supports monolith-style Railway deployment where web, bot, engine, and worker responsibilities can be composed under one runtime.

## 2. End-to-End Product Flow

1. Market data is fetched/normalized from provider adapters.
2. Strategy modules generate candidates.
3. Engine filters/ranks candidates and applies quality/risk governance.
4. Tier logic determines who can see what and when.
5. Signals are delivered by Telegram and recorded in delivery tables.
6. Outcome tracking resolves TP/SL/time-stop and writes analytics-ready outcomes.
7. Reports, dashboards, referrals, subscriptions, and admin tools consume these records.

## 3. Folder-by-Folder Capability Map

### 3.1 Root-Level Runtime and Ops Files
- `main.py`: startup router by `RUN_MODE` and handoff behavior.
- `railway_main.py`: Railway monolith orchestration (FastAPI + Telegram webhook runtime, lifecycle hooks, queue health).
- `web/app.py`: API/webhook endpoints, health probes, metrics emission, payment processing, broker permission checks.
- `config.py`: centralized environment loading and feature toggle defaults.
- `alembic.ini`: migration runtime configuration.
- `Dockerfile`, `Dockerfile.prod`, `Procfile`, `nixpacks.toml`, `railway.json`, `start.sh`, `deploy.sh`, `deploy.bat`: deployment and process boot contracts.
- SQL/manual migration files: emergency/manual schema operations for controlled rollout.

### 3.2 `admin/`
- Operator control tools, including kill-switch style emergency controls.

### 3.3 `alembic/` and `db/migrations/`
- Versioned schema evolution for signals, outcomes, payment, API tokens, and reliability features.

### 3.4 `core/`
- Cross-cutting policy and state:
- Tier constants and freshness tolerances.
- Runtime settings abstraction.
- Redis/Postgres-backed transient state helpers.
- Shared performance and safety governance primitives.

### 3.5 `data/`
- Data intake and transformation:
- Connector registry and provider adapters.
- Market fetch and indicator preparation.
- Pair discovery and market hours logic.
- News/sentiment intake paths.
- WebSocket ingestion components.

### 3.6 `db/`
- Persistence plane:
- ORM models for users, signals, outcomes, subscriptions, deliveries, webhook records, API tokens.
- Session lifecycle and database compatibility helpers.
- Repository and feature-layer write/read utilities.

### 3.7 `docs/`
- Product, implementation status, rollout decisions, environment and deployment docs.

### 3.8 `engine/`
- Core intelligence and lifecycle logic:
- Signal generation core and filtering layers.
- Consensus/confluence scoring.
- Risk, regime, ranking, and MTF logic.
- Outcome tracker and stale/time-stop resolution.
- Realtime/queue and operational loop behavior.

### 3.9 `ml/`
- Model persistence and inference/training support.

### 3.10 `payments/` and `paystack/`
- Subscription/payment workflows, webhook verification, and activation flows.

### 3.11 `scripts/`
- Utility automation, migrations/helpers, and operational patch scripts.

### 3.12 `services/`
- Service clients and infrastructure integration modules (for example, broker/MT5 related integrations).

### 3.13 `signalrank_telegram/`
- Telegram product surface:
- Command handlers and help UX.
- Tier access governance.
- Dispatch/resend logic.
- Message formatting and user interaction flows.

### 3.14 `storage/`
- Storage helpers and persistence-facing utility modules.

### 3.15 `strategies/`
- Strategy adapters and execution units (including TradingView integration patterns).

### 3.16 `telegram/`
- Telegram integration glue and related support modules.

### 3.17 `tests/`
- Unit/integration/regression coverage for command behavior, engine logic, webhooks, and safety defaults.

### 3.18 `utils/`
- Shared utilities, logging helpers, and supporting functions.

### 3.19 `worker/`
- Worker-side recurring jobs and market monitor/background responsibilities.

## 4. Command and Tier Capability Surface

Canonical command gating is controlled via `signalrank_telegram/command_access.py`.

### 4.1 Free Tier
`/start`, `/help`, `/about`, `/faq`, `/disclaimer`, `/pricing`, `/upgrade`, `/signals`, `/signal`, `/proof`, `/outcome`, `/invite`, `/policy`, `/refunds`, `/recap`, `/buy_extra_signals`, `/language`, `/referral_leaderboard`, `/referral_rewards`, `/support`, `/status`, `/liveprice`, `/market`, `/myid`, `/account`, `/leaderboard`, `/tiers`

### 4.2 Premium Tier Additions
`/performance`, `/stats`, `/history`, `/risk`, `/alerts`, `/analyze`, `/dashboard`, `/feedback`, `/apikey`, `/filter`, `/reports`, `/notify`, `/portfolio`, `/quality`, `/execution`, `/drawdown`, `/setlot`, `/mystats`, `/referral`, `/mt5`, `/mt5link`, `/mt5_link`, `/mt5_status`, `/connect_broker`, `/cancel`

### 4.3 VIP Tier Additions
`/elite`, `/early`, `/report`, `/simulate`, `/setrisk`, `/setwebhook`

### 4.4 Admin Tier
`/admin`, `/admin_dashboard`, `/admin_broadcast`, `/force_market_scan`, `/force_signal`, `/gemini`, `/gemini_review`, `/admin_top_assets`, `/admin_top_strategies`, `/admin_user_engagement`, `/selfcheck`, `/ops_health`, `/blast_terms`, `/assets`

### 4.5 Owner Tier
`/dev_pause`, `/dev_resume`, `/dev_force_signal`, `/dev_invalidate`, `/owner_users`, `/owner_revenue`, `/version`, `/correct_signal`, `/provider_status`, `/broadcast` and owner-only hidden control surfaces.

## 5. Outcome and Delivery Architecture (Current)

### 5.1 Outcome Truth Split
Outcome persistence now supports three truth channels:
- `canonical_outcome`: objective market truth for analytics and model training.
- `vip_fill_outcome`: execution-aware fill perspective for VIP fill realism.
- `sentiment_outcome`: sentiment-attribution/overlay outcome stream.

### 5.2 Terminal Resolution Modes
Outcome status supports explicit terminal semantics including:
- TP/SL style terminals.
- `time_stop` for SLA-driven staleness expiry.
- `invalid` where business logic requires invalidation.

### 5.3 Delivery Attempt State
Signal delivery records track reliability state for dispatch operations:
- `sent_ok` boolean status.
- `attempt_count`.
- `last_attempt_at`.
- `last_error`.

This enables at-least-once retry flows with idempotent state inspection.

## 6. API and Webhook Capability Surface

### 6.1 API
- Health/readiness/metrics endpoints for operations.
- Paystack webhook endpoint with signature verification and idempotent event persistence.
- Broker API permission validation endpoint to enforce trade-only key safety.

### 6.2 Telegram Webhook Runtime
- Webhook setup and periodic health checks.
- Queue-based dispatch workers with Redis-backed queue support and in-process fallback.
- Self-heal behavior when webhook is unexpectedly unset.

## 7. Deployment URL Configuration (`APP_BASE_URL` and `WEBHOOK_URL`)

### 7.1 What the runtime actually uses
Current Telegram webhook registration logic in `railway_main.py` derives the public base URL from:
1. `RAILWAY_PUBLIC_DOMAIN` (preferred)
2. `WEBHOOK_DOMAIN`
3. `WEBHOOK_URL`
4. `APP_BASE_URL`

Then it registers: `<base>/telegram/webhook` with Telegram.

### 7.2 How to set values on Railway
1. Open your Railway service.
2. Go to Settings -> Networking.
3. Ensure a public domain is assigned.
4. Copy that domain and set env vars:
   - `RAILWAY_PUBLIC_DOMAIN=<your-domain>` (no path)
   - `WEBHOOK_URL=https://<your-domain>` (optional explicit fallback)
   - `APP_BASE_URL=https://<your-domain>` (recommended canonical app base for links/docs)

### 7.3 Practical recommendation
- Keep `APP_BASE_URL` and `WEBHOOK_URL` aligned to the same HTTPS origin.
- Let webhook setup use `RAILWAY_PUBLIC_DOMAIN` as primary source.

## 8. Post-`X_BEARER_TOKEN` Activation Checklist

The codebase now consumes `X_BEARER_TOKEN` (and `TWITTER_BEARER_TOKEN` as a compatibility alias) in `data/news.py` via the X recent search endpoint, with fallback to CryptoCompare where needed.

### 8.1 Safe immediate steps
1. Add `X_BEARER_TOKEN` in Railway environment variables.
2. Redeploy and confirm startup is healthy.
3. Validate no regressions in signal generation and command handling.
4. Confirm sentiment path by checking that headline fetches for configured assets include X-derived entries when token and API quota are valid.

### 8.2 Current behavior and fallback
1. Source order is NewsAPI, then X recent search, then CryptoCompare fallback.
2. If X token is missing or X request fails, ingestion continues via existing fallback providers.
3. Existing sentiment scoring contract is preserved (headline text scored by `simple_sentiment_score`).

## 9. Operational Runbook (Condensed)

1. Set required env vars (DB, Telegram token, owner IDs, payment/webhook secrets, public domain).
2. Run migrations before rollout.
3. Deploy with webhook-enabled mode.
4. Verify `/health` and metrics endpoint.
5. Confirm Telegram webhook registration and command responsiveness.
6. Validate payment webhook signature path.
7. Monitor webhook latency, queue depth, and outcome freshness metrics.

## 10. Definition-of-Done Validation Pointers

- Command access map and help output stay in sync.
- Tier-gated delivery behavior is deterministic under retries.
- Outcome tracker writes canonical + split outcomes consistently.
- Time-stop closure appears in ops health and analytics.
- Trade-only broker permission endpoint blocks withdraw/transfer-enabled API keys.
- Test suite remains green after any migration/runtime change.
