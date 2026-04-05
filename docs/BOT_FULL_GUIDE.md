# SignalRankAI Bot — Full Detailed Guide

## 1) What the bot is

SignalRankAI is an algorithmic trading signal platform delivered primarily through Telegram, with a web/API layer and background worker services.  
It generates signals from market data, filters/ranks them, dispatches them by user tier, tracks outcomes, and supports subscription/payments.

At a high level, the product combines:
- Market data ingestion and normalization
- Multi-strategy signal generation
- Rule-based validation and scoring
- Tier-aware delivery/rate controls
- Outcome/performance tracking
- Monetization and access control

---

## 2) What the bot can do

### User-facing capabilities
- Register users from Telegram (`/start`)
- Show tier-aware command menus and gated features
- Deliver signals with tier-specific formatting and limits
- Provide performance/outcome history views
- Show market overviews and live price data
- Handle referrals and rewards
- Support upgrade/payment flows via Paystack
- Offer Premium/VIP feature paths, including advanced workflows

### Operator/admin capabilities
- Owner/admin command access controls
- Runtime kill-switch and protective throttling
- Environment/readiness diagnostics
- Webhook observability and health endpoints
- Background jobs and periodic maintenance tasks

### ML capabilities
- Load and score signals with XGBoost model metadata
- Maintain model payload with feature schema
- Verify model artifact integrity via hash metadata
- Train/retrain pipelines with model persistence

---

## 3) How the bot works (architecture flow)

## 3.1 Runtime entrypoints
- `main.py` controls multi-mode startup (`RUN_MODE`)
- `railway_main.py` provides monolith mode for Railway (web + bot + jobs)
- `web/app.py` handles API endpoints, health/metrics, and webhooks

## 3.2 Data and signal pipeline
- Data ingestion from connectors/providers (`data/*`)
- Feature/indicator preparation
- Strategy execution (`strategies/*`, `engine/strategies/*`)
- Signal validation/ranking/scoring (`engine/*`)
- Tiered dispatch through Telegram layer (`signalrank_telegram/*`)
- Outcome tracking and historical persistence (`db/*`, `engine/*`)

## 3.3 Delivery and governance
- Tier access matrix in `signalrank_telegram/command_access.py`
- Canonical delivery/quality gates in `core/tier_constants.py`
- Central command/free-feed throttle constants in `core/command_limits.py`
- Runtime state and rate limits via Postgres-backed state store in `core/redis_state.py` (Redis intentionally disabled)

## 3.4 Payments and subscriptions
- Signed Paystack webhook verification in `web/app.py`
- Subscription activation and seat constraints in DB/repository layer
- Tier resolution and gating used by bot commands and delivery logic

---

## 4) Core modules and responsibilities

- `engine/`: signal logic, filtering, scoring, risk, tracking
- `data/`: market providers/connectors/fetching
- `signalrank_telegram/`: Telegram commands, formatting, tier UX
- `web/`: API, health, metrics, payment webhooks
- `db/`: schema/session/repository and migrations
- `ml/`: training, inference artifacts, model registry
- `core/`: shared settings, constants, state helpers, version metadata
- `scripts/`: operational automation (env docs/changelog generation)

---

## 5) Security and reliability controls

- Webhook signature verification for payments
- Owner/admin tier-based command controls
- Rate-limiting on public and sensitive command paths
- Kill-switch support for emergency pauses
- Secrets sourced from environment variables (not committed)
- Postgres-backed runtime state for Railway/no-Redis deployments

---

## 6) Tiers and access model

Tier access is command-driven and centrally checked, with user experience tailored by tier:
- FREE: basic/discovery access, limited signal exposure
- PREMIUM: expanded analytics/history and fuller signal experience
- VIP: premium + stricter quality/advanced access profile
- ADMIN/OWNER: operational and control capabilities

Tier limits/scoring thresholds are centralized and reused by command and delivery flows.

---

## 7) ML model lifecycle

- Model artifacts are persisted in `ml/model.json`
- Required payload: `model_bytes_b64` + `feature_cols`
- Added metadata: `version`, `trained_at`, `xgboost_version`, `artifact_hash_sha256`
- Runtime loading validates payload and checks artifact hash integrity
- Training/retraining paths now emit metadata-compatible artifacts

---

## 8) Deployment and operations

### Supported deployment style
- Railway split services or monolith mode (`RUN_MODE=all`/`railway_main`)

### Added operational automation
- `scripts/gen_env_index.py` generates `docs/ENV_VARS.md` and checks `.env.example` sync with `core/settings.py`
- `scripts/gen_changelog.py` generates `docs/CHANGELOG_SUMMARY.md` from the main changelog
- `core/version.py` exposes runtime build/version banner
- `start.sh` prints version/build banner at startup

---

## 9) Testing and validation overview

Project CI uses pytest with Postgres service and migrations.  
New validation coverage includes:
- No-Redis Railway runtime behavior tests
- ML registry/integrity tests
- Existing webhook tests and targeted regression checks

---

## 10) Current strengths and next improvements

### Strengths
- End-to-end signal pipeline with governance gates
- Tier-aware product model and monetization path
- Railway-friendly runtime behavior without Redis dependency
- Operational automation for env documentation and release metadata
- ML artifact integrity checks for safer model loading

### Recommended next improvements
- Expand integration tests around monolith lifecycle startup/shutdown flows
- Add deeper contract tests for tier command matrix vs help surface
- Add richer SLO-focused monitoring/alerts around queueing/outcome latency
- Continue hardening ML schema evolution/version migration paths

---

## 11) Quick file map for reviewers

- Bot commands: `signalrank_telegram/commands.py`
- Command tier matrix: `signalrank_telegram/command_access.py`
- Tier constants: `core/tier_constants.py`
- Command throttles/constants: `core/command_limits.py`
- Runtime state/rate limits: `core/redis_state.py`
- Railway monolith: `railway_main.py`
- Webhooks/health/metrics: `web/app.py`
- ML runtime scoring: `engine/ml.py`
- ML registry/integrity: `ml/model_registry.py`
- Environment index generator: `scripts/gen_env_index.py`
- Changelog summary generator: `scripts/gen_changelog.py`

