# SignalRankAI — Comprehensive Project Documentation

Last updated: 2026-03-13

## 1. Executive Summary

SignalRankAI is a multi-component trading signal platform that:

- Ingests market data (crypto, FX, stocks, commodities)
- Generates and filters signals using rule-based confluence + ML validation
- Stores signals/outcomes in PostgreSQL
- Delivers tiered Telegram notifications (Free/Premium/VIP/Admin/Owner)
- Tracks outcomes, user engagement, subscriptions, and analytics
- Supports Railway deployment in both monolith and split-service modes

This project is production-oriented, fault-tolerant, and designed for deterministic behavior with configurable ML enhancement.

---

## 2. System Architecture

### 2.1 Core Runtime Components

- `main.py`
  - Unified process entrypoint
  - Selects run mode (`engine`, `bot`, `web`, `worker`, or `all`)
- `engine/core.py`
  - Main signal generation pipeline
  - Risk, confluence, ML gating, scoring, storage, dispatch trigger
- `signalrank_telegram/bot.py`
  - Telegram app bootstrap
  - Scheduler jobs for resend, free queue delivery, outcomes, recap, retraining
  - Dispatch + update logic
- `signalrank_telegram/commands.py`
  - User/admin/owner command handlers
- `web/app.py`
  - FastAPI endpoints (`/health`, `/metrics`, `/webhooks/paystack`, admin kill-switch)
- `worker/worker.py`
  - Background worker loop (integration and async maintenance work)
- `db/*`
  - SQLAlchemy models, sessions, repository, Postgres feature functions

### 2.2 Railway Monolith Entry

- `railway_main.py`
  - Lifespan-managed startup
  - Runs migrations/startup ops
  - Starts engine + worker background tasks
  - Starts web-layer scheduler
  - Boots Telegram in webhook mode and wires `/telegram/webhook`

### 2.3 Data & Control Planes

- **Data plane**: providers → indicators → strategies → confluence/ML/risk → signal store
- **Delivery plane**: dispatch rules + dedupe + tier formatting + Telegram send/update
- **Outcome plane**: TP/SL/expiry tracking, notifications, engagement and analytics updates
- **Monetization plane**: subscriptions, Paystack webhook verification, referrals, seat management

---

## 3. Repository Structure (Functional)

- `engine/`: signal generation, confluence, scoring, risk, outcome monitoring, ML integration
- `signalrank_telegram/`: bot runtime, command handlers, formatting, access control, owner/admin tools
- `db/`: models, migrations, PG query helpers, session management
- `data/`: provider connectors, market fetchers, indicators
- `ml/`: feature extraction, inference filter, model training
- `web/`: FastAPI app and webhook handlers
- `worker/`: background worker process
- `docs/`: specifications and implementation documentation
- `tests/`: pytest suite

---

## 4. Signal Lifecycle

## 4.1 Generation Pipeline

1. Asset universe is selected and market-open filtered
2. Market data and indicators are fetched per timeframe
3. Strategy candidates are generated
4. Validation gates run:
   - structural validity
   - risk gate
   - confluence gate
   - ML filter gate
5. Signal is scored and enriched
6. TP/SL sanity checks and expiry tagging are applied
7. Signal is deduplicated and stored
8. Dispatch logic routes by tier and delivery constraints

## 4.2 Key Quality Gates

- Confluence threshold checks
- ML advisory filter + hard-threshold kill switch (`ML_HARD_FILTER_MIN`)
- TP structure validation (directionally valid TP ladder)
- Duplicate suppression by user and by signal fingerprint
- Asset lock per-user (same asset suppression until resolved or lock timeout)

## 4.3 Message Update Policy

Active signal message edits are allowed only when materially improved:

- Better ROI and/or RR
- Better ML confidence
- More favorable news context
- Non-degrading checks must pass (no backward quality move)

Users receive explicit update reason text when update is accepted.

---

## 5. Tier Model & Delivery Rules

## 5.1 Tiers

- FREE
- PREMIUM
- VIP
- ADMIN
- OWNER

## 5.2 Important Behavioral Rules

- Owner/admin are normalized to VIP-equivalent routing for signal stream consistency
- Free tier uses delayed queued delivery and random timing, capped daily (default max 3)
- Delivery dedupe is DB-backed (works even with no Redis)
- Resend job quality-caps and coalescing reduce burst spam behavior

## 5.3 Free-Tier Daily Policy

Implemented behavior (default):

- Maximum: 3 signals/day per user
- Delivery style: delayed, randomized queue windows
- Non-immediate path is default (`FREE_DIRECT_DISPATCH` disabled unless explicitly enabled)

---

## 6. Outcome Tracking Model

## 6.1 Outcome States

Common statuses include: `tp1`, `tp2`, `tp3`/`tp`, `sl`, `expired/timeout`, `invalid`.

## 6.2 Progression Handling

Outcome progression is preserved and notification state can be reset on advancement (e.g., TP1→TP2→TP3), enabling stage-by-stage updates.

## 6.3 Recipient-Scoped Delivery

Outcome notifications are tied to users who received the specific signal via `SignalDelivery`, preserving recipient scope.

---

## 7. ML System (Hybrid Intelligence)

## 7.1 Role in Decisioning

The system is hybrid:

- Rule engine generates candidate setups
- ML validates and adjusts confidence/risk behavior

## 7.2 Online Features (Inference)

Expanded inference feature support includes:

- Price velocity (3/5/10 candles)
- Price acceleration
- ATR-relative volatility and ATR regime
- Relative volume
- MTF trend context (4H and 1D)
- Confluence-derived context
- Optional alpha features (funding rate, open interest change, DXY/SPX trend, BTC correlation)

## 7.3 Training Data & Labeling

Training is based on stored signals + outcomes + candle history with:

- Triple-barrier-aware labeling semantics (upper/lower/time)
- Partial TP progression as learning signal
- False-breakout / volatility stop-out down-weighting
- RR-aware sample weighting
- Recency bias weighting (configurable half-life)
- Time-series split for validation (past→future, avoids random split leakage)

## 7.4 Dynamic Risk & Volatility Adaptation

Engine applies ML-driven risk hints and volatility-aware level adaptation:

- Higher confidence can imply higher suggested risk band
- High ATR regime can widen SL/TP (configurable multipliers)

---

## 8. Schedulers and Background Jobs

Primary bot scheduler jobs include:

- ML market analysis
- Free delayed summary delivery
- Outcome computation and notification fanout
- Monitor snapshot refresh
- VIP scarcity and engagement broadcasts
- Weekly recap
- Auto ML retraining
- Resend unsent signals (coalesced)
- Random free-signal queueing
- Expiry cleanup and subscription downgrade jobs

The bot scheduler can persist jobs in SQLAlchemy jobstore when configured; non-picklable closure jobs remain memory-based.

---

## 9. API Surfaces

## 9.1 FastAPI (`web/app.py`)

- `GET /health`
- `GET /healthz`
- `GET /metrics`
- `GET /admin/killswitch`
- `POST /admin/killswitch`
- `POST /webhooks/paystack` and alias `/paystack/webhook`
- `POST /upgrade`

## 9.2 Telegram Bot Surface

Command access is tier-controlled via command matrix in `signalrank_telegram/command_access.py`.

High-level command categories:

- Public: start/help/pricing/upgrade/signals/signal/outcome/status/support
- Premium: analytics, filters, reports, notify, portfolio, broker linking
- VIP: elite/early/report variants
- Admin/Owner: governance, broadcast, force actions, revenue/user diagnostics

---

## 10. Data Model (Key Tables)

From `db/models.py`, key entities include:

- `User`
- `Subscription`
- `PaymentEvent`
- `Signal`
- `Outcome`
- `SignalDelivery`
- `SignalEngagement`
- `ActiveSignalMessage`
- `FreeSignalQueue`
- `MT5Credentials`
- `MT5Execution`
- `DecisionLog`
- `MLRejectedSignal`
- `ManagedAsset`
- Referral entities (`ReferralCode`, `ReferralAttribution`, `ReferralReward`)

---

## 11. Deployment

## 11.1 Recommended Railway Mode

Current `railway.json` starts monolith webhook mode:

- `RUN_MODE=all uvicorn railway_main:app --host 0.0.0.0 --port $PORT`

This runs web + engine + worker + Telegram webhook integration in one deploy target.

## 11.2 Alternative Split-Services

Supported by `main.py` run modes:

- `RUN_MODE=web`
- `RUN_MODE=engine`
- `RUN_MODE=worker`
- `RUN_MODE=bot`
- `RUN_MODE=all`

## 11.3 Startup Sequence

1. Startup ops / migrations
2. Data self-check
3. Mode-specific runtime bootstrap
4. Scheduler/job initialization

---

## 12. Redis vs No-Redis Operation

This codebase supports degraded/no-Redis operation for core flows:

- Critical signal delivery dedupe and history are DB-backed
- Resend and queue behavior rely on PostgreSQL-backed records

Redis remains optional for convenience/caching/rate counters and kill-switch state acceleration.

For Railway deployments with no Redis:

- Ensure PostgreSQL is healthy
- Keep DB URLs configured correctly
- Prefer default queued free-delivery path

---

## 13. Configuration Guide (High-Impact Variables)

## 13.1 Core Runtime

- `RUN_MODE`
- `DRY_RUN`
- `DATABASE_URL`
- `TELEGRAM_BOT_TOKEN`

## 13.2 Ownership / Access

- `OWNER_TELEGRAM_ID`
- `OWNER_IDS`
- `ADMIN_IDS`
- `BYPASS_KEY`

## 13.3 Delivery / Anti-Spam / Free Queue

- `RESEND_MIN_SCORE`
- `RESEND_MAX_SIGNALS`
- `FREE_DAILY_LIMIT`
- `FREE_DIRECT_DISPATCH`
- `FREE_MIN_DELAY_MINUTES`
- `FREE_MAX_DELAY_MINUTES`
- `ASSET_REPEAT_LOCK_HOURS`

## 13.4 ML & Risk

- `ML_ENABLED`
- `ML_HARD_FILTER_MIN`
- `ML_PROB_THRESHOLD`
- `ML_RECENCY_HALF_LIFE_DAYS`
- `ML_HIGH_CONFIDENCE`
- `ML_MEDIUM_CONFIDENCE`
- `ML_RISK_HIGH_PCT`
- `ML_RISK_MEDIUM_PCT`
- `ML_RISK_LOW_PCT`
- `VOLATILITY_WIDEN_ATR_MULT`
- `VOLATILITY_WIDEN_SL_MULT`
- `VOLATILITY_WIDEN_TP_MULT`

## 13.5 Webhook / Railway

- `RAILWAY_PUBLIC_DOMAIN` or `WEBHOOK_URL`
- `PORT`

## 13.6 Payments

- `PAYSTACK_SECRET_KEY`
- `PAYSTACK_WEBHOOK_SECRET`
- Plan code variables for premium/vip plans

---

## 14. Testing Strategy

## 14.1 What to Run

- Outcome progression tests (multi-TP)
- Dispatch/update behavior smoke tests
- Integration tests around commands and signal rendering

## 14.2 Current Smoke Validation Examples

- Focused dispatch/update smoke script passed
- `tests/test_outcome_integration_multi_tp.py` passed

---

## 15. Observability & Operations

- Structured logs supported via `LOG_JSON`
- Startup logs include service/deploy metadata
- Health endpoints for platform checks
- Scheduler warns on startup and job registration issues

Operational recommendations:

- Alert on repeated restart loops
- Alert on migration failures
- Track resend volume and free queue send rates
- Track outcome lag (signal create → first outcome event)

---

## 16. Security & Compliance Notes

- No profit guarantees in product language
- Payment verification via signed webhook
- Principle of least privilege for admin/owner commands
- Secrets must come from environment, never committed

---

## 17. Known Caveats / Technical Debt

- Some docs and constants may be out-of-sync across modules as features evolve
- `.env.example` may not list every runtime variable currently used in code
- Redis-optional paths exist, but some optional counters still attempt Redis best-effort

---

## 18. Recommended Next Steps

1. Publish and maintain a generated env var index from code scanning
2. Consolidate tier limits into one canonical constants module
3. Add dedicated end-to-end tests for no-Redis Railway mode
4. Add explicit model registry/versioning for ML artifacts
5. Add changelog automation and docs version stamp on deploy

---

## 19. Cross-Reference Files

- Main entrypoint: `main.py`
- Railway monolith entrypoint: `railway_main.py`
- Bot runtime and jobs: `signalrank_telegram/bot.py`
- Bot commands: `signalrank_telegram/commands.py`
- Command/tier matrix: `signalrank_telegram/command_access.py`
- Engine pipeline: `engine/core.py`
- Training pipeline: `ml/train_model.py`
- Inference features: `ml/features.py`
- Runtime scorer: `engine/ml.py`
- Data model: `db/models.py`
- Existing spec: `docs/FUNCTIONAL_SPEC.md`
- Existing status map: `docs/IMPLEMENTATION_STATUS.md`
