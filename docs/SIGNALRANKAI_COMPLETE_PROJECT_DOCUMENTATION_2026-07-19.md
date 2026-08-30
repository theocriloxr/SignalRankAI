# SignalRankAI — Complete Project Documentation

**Documentation date:** 2026-07-19  
**Canonical repository:** `C:\Users\sammm\Desktop\SignalRankAI1`  
**Current release verdict:** `LIMITED_PUBLIC_TEST_READY`  
**Current safety posture:** auto-trading, copy-trading, real payouts, and public payments are disabled by default.

This document is the operational index for the current SignalRankAI codebase. It
describes what is implemented, how the services fit together, how to run and
test them, what the safety gates mean, what the database contains, and what
still requires real staging evidence. Historical phase reports remain useful
for design rationale; this document is the current-state summary.

## 1. What SignalRankAI is

SignalRankAI is a Telegram-first, multi-asset trading-intelligence platform.
It combines market-data providers, deterministic strategy/risk validation,
optional AI/ML review, Telegram delivery, lifecycle/outcome tracking, paper and
shadow evaluation, tiered product access, Paystack payment readiness, and
Railway deployment/runtime tooling.

It is financial-adjacent software, not a profit guarantee. The system must
never invent a win rate, hide losses, deliver stale data as fresh, or execute
real money without explicit future approval and independent safety controls.

## 2. Current implementation status

### Implemented in code

- Final live-price and freshness validation, including stale, expired, missed,
  TP-already-hit, drift, market-hours, and provider-confidence checks.
- Delivery proof, active-message persistence, idempotent dispatch, Telegram
  retry handling, outcome snapshots, and monotonic outcome progression.
- Fast command/database-priority paths so interactive commands are not starved
  by background work.
- Central tier policy, upgrade UX, profile/risk settings, and command gating.
- Security/privacy controls for API keys, broker credentials, Paystack payloads,
  receipt data, logs, and sensitive identifiers.
- API token rotation/revocation with authentication and scope checks.
- AI review router with deterministic-first validation and safe fallback.
- Backtesting, spread/slippage assumptions, missed/expired events, shadow
  separation, sample-size thresholds, confidence intervals, and purged
  walk-forward split helpers.
- Virtual paper ledger and simulation-only Automaton state machine.
- Sixteen-role Agent Council manifest with forbidden actions and approvals.
- Read-only CodexOps primitives and versioned prompt files.
- Confirmed-payment receipt service, idempotency, refund/credit-note foundation,
  and manual payout-readiness checks.
- Runtime role adapters, dispatcher, liveness/readiness contracts, schema audit,
  soak reporting, and release guard.
- Public tester/support/payment-help/refund/feedback/admin command surfaces.

### Implemented but deliberately hidden or default-off

- Telegram rich messages/canary mode.
- Paystack public payment flow and paid beta entitlement mutation.
- MT5/broker execution, copy trading, and automatic trading.
- Real payouts or automated Nigerian-bank funding.
- Model/strategy promotion that would affect production without evidence and
  human approval.

### Requires real operational evidence

- Railway staging deployment with real Postgres, Redis, Telegram, provider, and
  Paystack test credentials.
- 24–72 hours of clean soak logs and metrics before any paid-beta decision.
- A sufficiently large, methodology-disclosed outcome sample before public
  performance claims. The project does not currently claim a 60% win rate.

## 3. System architecture

The canonical signal loop is:

```text
market providers
  -> provider health/freshness
  -> strategy generation and confluence
  -> deterministic risk validation
  -> optional AI/ML review
  -> final live-price validation
  -> queue/time-to-Telegraph validation
  -> idempotent Telegram delivery
  -> delivery proof + active message ID
  -> user buttons / Check Outcome
  -> outcome lifecycle and notifications
  -> provenance-separated analytics
  -> strategy/provider/automaton recommendations
  -> tier and release diagnostics
```

### Runtime roles

`main.py` selects a `RUN_MODE` and delegates through `runtime.dispatcher`.
The role adapters are intentionally lazy and preserve the existing monolith
while making boundaries explicit:

| Role | Adapter | Responsibility |
|---|---|---|
| Web | `runtime/web.py`, `web/app.py` | FastAPI health, dashboard, API, webhook routes |
| Telegram bot | `runtime/bot.py`, `signalrank_telegram/bot.py` | Commands, callbacks, delivery, user UX |
| Engine | `runtime/engine.py`, `engine/core.py` | Market scan, strategy/risk pipeline |
| Delivery | `runtime/delivery.py`, `delivery/service.py` | Queue, freshness, idempotency, proof |
| Outcome | `runtime/outcome.py`, outcome tracker modules | TP/SL/missed/expired lifecycle |
| Analytics | `runtime/analytics.py`, `engine/analytics.py` | Performance and segment reporting |
| Scheduler | `runtime/scheduler.py` | Background cadence and deferred work |
| All/dev | `runtime/all_dev.py` | Compatibility orchestration for local/all mode |

`runtime/health.py` provides dependency-neutral `livez`, `readyz`, and role
readiness contracts. `scripts/architecture_smoke.py` imports role modules
without starting workers.

### Main entrypoints

- Local/all mode: `python main.py` or `RUN_MODE=all python main.py`.
- Web-only: `RUN_MODE=web python main.py`.
- Bot-only: `RUN_MODE=bot python main.py`.
- Engine-only: `RUN_MODE=engine python main.py`.
- Worker-only: `RUN_MODE=worker python main.py`.
- Railway monolith: `uvicorn railway_main:app --host 0.0.0.0 --port ${PORT:-8000}`.
- Container: `./start.sh` (see `Dockerfile`/`Dockerfile.prod`).

`Procfile` contains the Railway service examples. `AUTO_MIGRATE=false` is the
safe default; migrations should run explicitly in a release/deploy step.

## 4. Repository map

### Core policy and safety

- `core/env.py` — typed safety flags and environment parsing.
- `core/security.py` — masking, hashing, redaction, and sensitive-data rules.
- `core/feature_flags.py` — HIDDEN/OWNER_ONLY/INTERNAL_TEST/PUBLIC_TEST/
  PAID_BETA/PUBLIC_RELEASED/DISABLED states.
- `core/tier_policy.py` — canonical command-to-tier and feature policy.
- `core/automaton.py` — virtual-treasury survival state machine.
- `core/agent_council.py` — governed 16-role agent manifest.
- `core/codexops.py` — read-only engineering-audit primitives.
- `core/release_guard.py` — structural release checks and verdicts.
- `core/signal_lifecycle.py`, `core/signal_governor.py` — lifecycle and safety
  coordination.
- `core/redis_state.py`, `core/redis_cache.py` — shared state/cache interfaces.
- `core/paper_ledger.py`, `core/trade_tracker.py` — virtual and tracked trades.

### Market, strategy, and engine

- `engine/core.py` — main scan/orchestration path.
- `engine/strategies/` — strategy interfaces, runners, and signal generation.
- `engine/price_validator.py`, `engine/delivery_freshness.py`,
  `engine/stale_signal_validator.py` — quote/freshness gates.
- `engine/risk.py`, `engine/risk_manager.py`, `engine/risk_sizer.py`,
  `engine/risk_profiles.py` — risk and exposure checks.
- `engine/confluence_engine.py`, `engine/consensus.py`, `engine/ranking.py` —
  ranking and signal quality.
- `engine/realtime_outcome_tracker.py`, `engine/outcome_snapshots.py`,
  `engine/shadow_outcome_worker.py` — lifecycle and shadow outcomes.
- `engine/performance_truth.py` — event counting, costs, latency, WFO, and
  promotion criteria.
- `engine/portfolio_intelligence.py`, `engine/correlation_guard.py`,
  `engine/market_circuit_breaker.py` — exposure and market safety.
- `market/session_classifier.py` and provider modules — session/calendar logic.

### ML and AI

- `services/ai_review_router.py` — deterministic-first local/remote reviewer
  selection and fallback.
- `ml/evidence.py` — reproducible manifests, leakage checks, and WFO splits.
- `ml/scorer.py`, `ml/inference.py`, `ml/model_registry.py` — model use and
  registry metadata.
- `ml/drift_monitor.py`, `ml/feedback_loop.py`, `ml/retrain.py` — drift and
  feedback lifecycle.
- `configs/prompts/*.yaml` — versioned signal, risk, post-trade, automaton,
  support, CodexOps, and release prompts.

AI can improve explanation, contradiction detection, ranking commentary, and
post-trade review. AI cannot override stale blocking, live-price checks, risk
limits, evidence truth, or execution consent.

### Persistence and delivery

- `db/session.py` — async session/pool configuration and Railway caps.
- `db/models.py` — SQLAlchemy models.
- `db/repository.py`, `db/pg_features.py`, `db/priority.py` — data access and
  priority/session behavior.
- `delivery/service.py` — delivery reservation, send, proof, and idempotency.
- `delivery/receipts.py` — delivery receipt helpers.
- `signalrank_telegram/signal_distribution.py` and `tier_delivery.py` — user
  delivery/tier behavior.

### Payments and execution

- `payments/paystack.py`, `payments/paystack_webhook.py` — Paystack verification
  and webhook handling.
- `payments/receipt_service.py` — verified-payment receipts and credit notes.
- `payments/payout_readiness.py` — masked bank details/manual approval; no real
  payout side effect.
- `execution/service.py` — fail-closed `ExecutionGate` and explicit execution
  request/result contracts.
- `services/mt5_client.py`, `services/mt5_bridge.py`, `services/mt5_signal_router.py`
  — broker foundation, disabled unless separately configured and approved.

### Telegram and web

- `signalrank_telegram/bot.py` — application registration and lifecycle.
- `signalrank_telegram/commands.py`, `user_commands.py`, `admin_commands.py`,
  `owner_commands.py` — command implementations.
- `signalrank_telegram/signal_commands.py` — signal UX and fast unresolved path.
- `signalrank_telegram/callback_handlers.py` — button/callback routing.
- `signalrank_telegram/extended_commands.py` — public-test, receipt, paper,
  automaton, support, and CodexOps adapters.
- `signalrank_telegram/formatter.py`, `tier_signal_formatter.py`,
  `rich_messages.py` — message presentation (rich mode is off by default).
- `web/app.py` — canonical FastAPI application and mounted API.
- `web/api.py` — `/api/v1` endpoints, API-key auth, signal and token routes.
- `web/userdash/` — dashboard templates and static assets.

## 5. Signal correctness and delivery contract

Every candidate must pass deterministic checks before Telegram delivery:

1. Provider response exists and is fresh.
2. Asset/timeframe/session are supported.
3. Entry, stop, and take-profit ordering is valid.
4. Risk, R/R, exposure, correlation, and strategy gates pass.
5. AI/ML output is supplementary and cannot bypass deterministic rejection.
6. A final live quote is fetched when strict mode is enabled.
7. The signal is rejected if stale, expired in queue, drifted beyond policy,
   already hit TP, missed, or provider confidence is too low.
8. Delivery is reserved idempotently by signal/user key.
9. Telegram send success is followed by delivery-proof and active-message writes.
10. Callback paths acknowledge quickly and use the saved active message ID.

The system records `sent_ok`, message identifiers, timestamps, provider/source
metadata, latency, and failure state. A send without proof is an operational
failure and must not be counted as a normal delivered signal.

## 6. Outcome and performance truth

Outcome events are monotonic and idempotent:

- `TP1`, `TP2`, and `TP3` are separate win events.
- `SL` is a loss event.
- `MISSED_ENTRY` means the entry zone was never reached before expiry.
- `EXPIRED` means the signal expired without resolution.
- `PROVIDER_UNAVAILABLE` is an operational outcome, not a fabricated win/loss.

Performance is separated by provenance: `backtest`, `walk_forward`, `shadow`,
`paper`, `manual`, and `live_delivered`. Reports include sample size, costs,
spread/slippage assumptions, latency, drawdown, expectancy, and methodology.

Evidence thresholds used by the performance layer:

| Sample | Interpretation |
|---:|---|
| `<30` | Exploratory only |
| `30–99` | Early/internal signal |
| `100–299` | Minimum usable internal evidence |
| `300–499` | Stronger promotion evidence |
| `500+` | Candidate for public claims only with disclosed methodology |

Promotion is conservative: adequate sample, multiple positive out-of-sample
folds, positive expectancy, profit-factor/drawdown constraints, and human
approval are required. No code hardcodes or advertises a 60% win rate.

## 7. Automaton and Agent Council

`core.automaton.AutomatonState` supports:

`OBSERVE`, `SIMULATE`, `PAPER_TRADE`, `CONSERVE`, `RECOVER`, `OPTIMIZE`,
`SCALE`, `PAUSE`, and `KILL_SWITCH`.

The default virtual balance is `AUTOMATON_STARTING_BALANCE_USD=5000`; it is not
real money. State decisions consume equity, drawdown, win rate, expectancy,
sample size, provider confidence, delivery latency, DB/Redis/outcome health,
and missed/expired rates. The automaton can recommend lower volume, quarantine,
stricter validation, provider changes, or paper scaling. It cannot trade,
withdraw, fund, deploy, rewrite production, or bypass risk controls.

The Agent Council roles are: Market Data, Strategy Research, Signal Quality,
Risk Manager, Final Delivery Guard, Outcome, Backtest, Shadow Trading, Paper
Trading, Automaton Supervisor, Portfolio, Business, Support, Compliance and
Trust, CodexOps, and Release Guard. Each role has inputs/outputs, forbidden
actions, approvals, fallback, and feature-flag expectations in
`core/agent_council.py`.

## 8. Payments, receipts, API, and privacy

### Payments

Only a verified successful Paystack payment with a reference can create a
receipt. Receipt creation is idempotent and stores receipt number, user, plan,
amount, currency, payment reference, billing period, status, support contact,
and the no-guaranteed-profit disclaimer. Failed/unverified webhooks do not
create successful receipts. Refunds are represented as credit-note/refund
records; payouts remain manual and disabled.

### API

The FastAPI app mounts the router under `/api/v1`. Token rotation/revocation
requires an authenticated API key/bearer credential and scope checks. Missing
or invalid credentials correctly return `401`; unavailable database/token
services return `503`. API keys are hashed/masked and never intended for logs.

### Broker/MT5

Credentials are encrypted/masked/redacted where stored or displayed. The
execution gate requires explicit account consent, trusted fresh quote, valid
risk/evidence state, idempotency, stop-loss direction, and enabled mode. AUTO
and COPY modes are disabled by default; ambiguous broker outcomes fail closed.

## 9. Telegram command catalog

The canonical source of tier access is `core/tier_policy.py`; the bot handlers
are registered in `signalrank_telegram/bot.py`. Commands below are grouped by
minimum tier.

### Free/public testing

`/start`, `/help`, `/about`, `/faq`, `/disclaimer`, `/pricing`, `/upgrade`,
`/tiers`, `/signals`, `/signal`, `/proof`, `/outcome`, `/profile`,
`/profile_debug`, `/invite`, `/policy`, `/refunds`, `/recap`, `/language`,
`/support`, `/status`, `/liveprice`, `/market`, `/myid`, `/account`,
`/leaderboard`, `/public_test_status`, `/provider_health`, `/performance_truth`,
`/receipt`, `/receipts`, `/report_issue`, `/payment_help`, `/refund_request`,
`/contact_admin`, `/tester_feedback`, `/paper_balance`, `/paper_positions`,
`/paper_history`, `/paper_performance`, `/paper_reset`, `/paper_settings`,
`/automaton_status`, `/automaton_pause`, `/automaton_resume`,
`/automaton_reset_paper`, `/referral_leaderboard`, `/referral_rewards`.

The pause/resume/reset commands are safe explanatory surfaces unless an owner
performs a separately audited action; they do not move money.

### Premium

`/performance`, `/stats`, `/history`, `/risk`, `/alerts`, `/analyze`,
`/dashboard`, `/feedback`, `/apikey`, `/filter`, `/reports`, `/notify`,
`/portfolio`, `/mission`, `/quality`, `/signal_quality`, `/winrate`,
`/shadow_report`, `/strategy_leaderboard`, `/drawdown`, `/setlot`, `/mystats`,
`/referral`, `/mt5`, `/mt5link`, `/mt5_link`, `/mt5_status`, `/connect_broker`,
`/cancel`.

### VIP

`/simulate`, `/setrisk`, `/setwebhook`, `/elite`, `/early`, `/report`.

### Admin/owner diagnostics

Admin: `/admin`, `/admin_dashboard`, `/admin_broadcast`, `/force_market_scan`,
`/force_signal`, `/gemini`, `/gemini_review`, `/gemini_analyze`,
`/gemini_audit`, `/gemini_predict`, `/codex_audit`, `/codex_log_review`,
`/codex_fix_plan`, `/codex_security_scan`, `/codex_release_check`,
`/codex_test_plan`, `/codex_refactor_plan`, `/codex_pr_summary`,
`/codex_generate_issue`, `/admin_top_assets`, `/admin_top_strategies`,
`/admin_user_engagement`, `/admin_user`, `/admin_subscription_fix`,
`/admin_signal_lookup`, `/admin_feedback`, `/admin_payment_lookup`,
`/admin_receipt_lookup`, `/qa_report`, `/selfcheck`, `/ops_health`, `/system`,
`/db_health`, `/engine_debug`, `/assets`, `/release_guard`, `/automaton_report`.

Owner: `/dev_pause`, `/dev_resume`, `/dev_force_signal`, `/dev_invalidate`,
`/owner_users`, `/owner_revenue`, `/version`, `/correct_signal`,
`/provider_status`, `/broadcast`.

Important buttons include Check Outcome, Open Signal, Monitor, Taking It,
Watching, manual/paper Take Trade, profile, pricing/upgrade, receipt, support,
and paper-trade controls. Callback handlers must acknowledge promptly.

## 10. Database and migrations

Postgres is the durable system of record. Redis is used for shared state,
queues, caches, locks, and webhook dispatch where configured. SQLite files in
the repository are local/test artifacts, not the production source of truth.

Migration chain (`db/migrations/versions`):

`0001_init`, `0002_features`, `0003_runtime_state`, `0004_payment_events`,
`0005_bot_events`, `0006_bigint_telegram_ids`, `0007_market_data_cache`,
`0008_user_tier_column`, `0009_archived_column`, `0010_consolidate_full_schema`,
`0011_platform_hardening_security_scaling`, `0012_outcome_notify_state`,
`0013_proxy_nodes`, `0014_add_outcome_pnl_pct`, `0015_active_signal_guard`,
`0016_signal_profile_metadata`, `0017_signal_delivery_proof`,
`0018_signal_lifecycle_events`, `0019_user_timezone_privacy`,
`0020_payment_receipts`.

Run and audit migrations:

```powershell
python -m alembic upgrade head
python scripts/schema_audit.py
```

The current audit reports 20 revisions, one head (`0020_payment_receipts`), and
no revision errors. Never use destructive resets on a live database. Rehearse
the migration on a disposable/staging database first.

## 11. Environment configuration

Start from `.env.example`; use `.env.production.template` as a production
checklist. Never commit real secrets. Important groups are:

| Group | Variables |
|---|---|
| Required infrastructure | `DATABASE_URL`, `REDIS_URL`, `TELEGRAM_BOT_TOKEN`, `SENTRY_DSN` |
| Providers | `GEMINI_API_KEY`, news/calendar keys, TwelveData/Polygon/AlphaVantage/FMP/FCS/Tiingo/CryptoCompare/CoinGecko keys |
| Provider routing | `CRYPTO_PREFERRED_PROVIDER`, `CRYPTO_MARKET_DATA_PROVIDERS`, `MARKET_PROVIDER_TIMEOUT_SECONDS`, failover/cooldown controls |
| Runtime | `RUN_MODE`, `PAPER_MODE`, `ENABLE_NEWS`, `ENABLE_ML`, `LOG_JSON`, Telegram timeouts |
| Database | `DB_POOL_SIZE`, `DB_MAX_OVERFLOW`, `DB_POOL_TIMEOUT_SECONDS`, `DB_POOL_RECYCLE_SECONDS`, `DB_RETRY_ATTEMPTS`, Railway caps |
| Engine | `ENGINE_CYCLE_SLEEP_SECONDS`, `ENGINE_UNIVERSE_CAP`, outcome interval/lifecycle flags, strategy and exposure caps |
| Delivery safety | `FINAL_SEND_LIVE_PRICE_CHECK_ENABLED=1`, `FINAL_SEND_FORCE_FRESH_PRICE=1`, unresolved/active limits, idempotency flags |
| Public testing | `PUBLIC_TESTING_MODE=0` by default, `AUTOMATON_MODE=SIMULATION`, `AUTOMATON_STARTING_BALANCE_USD=5000` |
| Trading/payment safety | `AUTO_TRADE_ENABLED=0`, `COPY_TRADE_ENABLED=0`, `REAL_PAYOUTS_ENABLED=0`, `PAYMENTS_PUBLIC_ENABLED=0`, `PAYMENTS_PUBLIC_TEST_MODE=0` |
| Trust/operations | `RECEIPTS_ENABLED=1`, `CODEXOPS_MODE=READ_ONLY_AUDIT`, provider health and observability flags |

The complete variable list and safe defaults are authoritative in
`.env.example`; do not infer production values from local test values.

## 12. Test inventory and evidence

### Commands executed for the completed implementation

```powershell
# Phase 1–5 regression contract suites
python -m pytest tests/test_phase4_pass1_quote_contract.py `
  tests/test_phase4_pass1_live_validation.py `
  tests/test_phase4_pass2_db_priority_and_command_speed.py `
  tests/test_phase4_pass3_delivery_reliability.py `
  tests/test_phase4_pass4_outcome_tracker_redesign.py `
  tests/test_phase4_pass5_tier_policy_and_upgrade_ux.py -q --disable-warnings

# New staged/security/runtime/command contracts
python -m pytest tests/test_phase4_pass6_security_api_payments.py `
  tests/test_phase4_pass7_runtime_roles.py `
  tests/test_staged_release_contracts.py `
  tests/test_command_tier_contract.py -q --disable-warnings

# Full regression suite
python -m pytest -q --tb=no --disable-warnings

# Static/runtime checks
python -m py_compile signalrank_telegram/bot.py signalrank_telegram/extended_commands.py
python -m compileall -q -x '\\.venv' .
python scripts/schema_audit.py
python scripts/architecture_smoke.py
python scripts/release_guard.py
```

### Recorded results

- Phase 1–5 regression suite: **80 passed**, 4 warnings.
- Staged/P6/P7 focused suite: **17 passed**.
- Final command/security/staged compatibility suite: **15 passed** in the
  completed implementation run; the final command-only rerun was **9 passed**.
- Full final-tree suite: **534 passed, 1 failed, 2 errors, 36 warnings**.
- Schema audit: **20 revisions, one head, no errors**.
- Architecture smoke: **passed**.
- Compile checks: **passed**.
- Release guard: **`LIMITED_PUBLIC_TEST_READY`**.

### Full-suite exceptions and interpretation

1. `tests/test_web_api_tokens.py::TestWebApiTokens::test_rotate_and_revoke_token`
   expects an unauthenticated token rotation to be `200` or `503`. The secure
   implementation requires an API key and returns `401`, which is the intended
   security contract. The test is legacy/order-sensitive and should be updated
   to assert `401` for missing credentials, then test rotation with a valid
   credential.
2. `tests/test_codex_governance_and_asset_locks.py::test_railway_dump_analyzer_reports_same_asset_duplicates`
   and `tests/test_orderbook_loader.py::test_normalize_top_of_book_and_convert`
   hit `PermissionError [WinError 5]` while pytest creates the Windows temp
   directory `C:\Users\sammm\AppData\Local\Temp\pytest-of-Theophilus`. This is
   host ACL state, not an application assertion failure. Run those tests on a
   writable temp root or repair the local ACL before treating the full suite as
   a release blocker.

### Test module inventory

The repository currently contains 108 test modules covering access/tier policy,
callbacks, command contracts, providers, market routing, engine loops,
freshness/deduplication, delivery/outcome lifecycle, risk, ML, WFO/backtesting,
paper ledger, payments/Paystack, Railway lifecycle, runtime health, security,
storage priority, strategy execution, telemetry, and web tokens. The exact
inventory is available with:

```powershell
rg --files tests
```

Notable contract modules include:

`test_phase4_pass1_quote_contract.py`, `test_phase4_pass1_live_validation.py`,
`test_phase4_pass2_db_priority_and_command_speed.py`,
`test_phase4_pass3_delivery_reliability.py`,
`test_phase4_pass4_outcome_tracker_redesign.py`,
`test_phase4_pass5_tier_policy_and_upgrade_ux.py`,
`test_phase4_pass6_security_api_payments.py`,
`test_phase4_pass7_runtime_roles.py`, `test_staged_release_contracts.py`,
`test_execution_safety.py`, `test_delivery_freshness.py`,
`test_signal_delivery_ack.py`, `test_signal_visibility_and_proof_quality.py`,
`test_outcome_delivery_contract.py`, `test_outcome_integration_multi_tp.py`,
`test_backtest_wfo.py`, `test_wfo_train.py`, `test_paper_ledger_exits.py`,
`test_payments.py`, `test_paystack_webhook.py`, `test_production_quality_guard.py`,
`test_production_readiness_check.py`, `test_railway_lifecycle.py`,
`test_railway_monolith_contract.py`, and `test_web_api_tokens.py`.

## 13. Operational runbooks

### Local developer setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
python -m alembic upgrade head
python scripts/architecture_smoke.py
python main.py
```

For a local bot without Telegram credentials, keep `RUN_MODE` limited to the
component being tested and use paper/simulation paths. Do not enable AUTO or
COPY modes just to make a test pass.

### Railway deployment

1. Configure Railway Postgres and Redis variables through the Railway secret
   store; do not put secrets in Git.
2. Deploy application code and install `requirements.txt`.
3. Run `python -m alembic upgrade head` as a reviewed release step.
4. Start the web/monolith entrypoint from `railway_main.py`/`start.sh`.
5. Verify health, webhook, DB, Redis, provider, and delivery metrics.
6. Run `scripts/schema_audit.py`, `scripts/architecture_smoke.py`, and the
   release guard.
7. Exercise public-test commands and one controlled paper signal.
8. Soak 24–72 hours before considering paid beta.

Relevant runbooks: `docs/PRODUCTION_LAUNCH_RUNBOOK.md`,
`docs/LIVE_PRODUCTION_EVIDENCE_RUNBOOK.md`,
`docs/PRODUCTION_READINESS_SCORECARD.md`, and
`docs/PHASE4_FINAL_HANDOFF_2026-07-19.md`.

### Incident response

If provider confidence drops, data becomes stale, DB/Redis health degrades,
delivery latency rises, outcomes stop progressing, or duplicate sends appear:

1. Stop public signal delivery or move to shadow/paper mode.
2. Preserve logs, delivery proofs, provider responses, and outcome events.
3. Run `/release_guard`, `/provider_health`, `/db_health`, `/ops_health`, and
   `/automaton_status`.
4. Do not delete outcome/payment records to hide a defect.
5. Roll back application configuration/image first; use a reviewed migration
   rollback procedure only if schema compatibility requires it.

## 14. Release stages

| Stage | Allowed | Disabled until evidence |
|---|---|---|
| Internal owner testing | Manual, paper, shadow, diagnostics, backtests, test receipts | Public payments, auto/copy, real payouts |
| Limited public testing | Bot, profiles, signals, outcomes, paper if stable, support/reporting | Auto/copy, real payouts, paid claims |
| Limited paid beta | Verified Paystack/receipts/refunds/support with disclosed performance | Auto/copy, real payouts, guarantees |
| Public production | Only after clean soak, security review, migration rehearsal, and evidence | Any capability that fails independent safety gates |

The release guard can return `BLOCKED`, `INTERNAL_BETA_READY`,
`LIMITED_PUBLIC_TEST_READY`, `PAID_BETA_READY`, or
`PUBLIC_PRODUCTION_READY`. The current offline result is limited testing only.

## 15. Risks and limitations

- The full suite is not completely green because of one stale test contract and
  two Windows temp ACL errors; resolve both before claiming a clean CI run.
- No live Railway soak has been performed in this local environment.
- Provider quality depends on configured credentials, rate limits, and market
  availability; local smoke tests cannot prove production freshness.
- Payment/receipt flows require verified Paystack test webhooks and a real
  database to validate end-to-end.
- Performance evidence is not large enough for a public win-rate claim.
- Rich messages, broker execution, copy trading, automatic payouts, and public
  payments are intentionally not production-enabled.
- Existing legacy modules remain for backward compatibility; runtime adapters
  establish boundaries before any future physical service split.

## 16. Canonical supporting documents

- `docs/PHASE1_FULL_CODEBASE_COMPREHENSION_2026-07-14.md`
- `docs/PHASE2_COMPETITIVE_RESEARCH_AND_GAP_ANALYSIS_2026-07-14.md`
- `docs/PHASE3_MASTER_OPTIMIZATION_PLAN_2026-07-14.md`
- `docs/PHASE4_PASS1_SIGNAL_CORRECTNESS_AND_LIVE_VALIDATION_2026-07-14.md`
- `docs/PHASE4_PASS2_DB_PRIORITY_AND_COMMAND_SPEED_2026-07-15.md`
- `docs/PHASE4_PASS3_DELIVERY_IDEMPOTENCY_AND_ACTIVE_MESSAGE_RELIABILITY_2026-07-18.md`
- `docs/PHASE4_PASS4_OUTCOME_TRACKER_REDESIGN_2026-07-18.md`
- `docs/PHASE4_PASS5_TIER_POLICY_AND_UPGRADE_UX_2026-07-18.md`
- `docs/PHASE4_PASS6_SECURITY_PRIVACY_API_PAYMENT_2026-07-19.md`
- `docs/PHASE4_PASS7_RUNTIME_ROLE_BOUNDARIES_2026-07-19.md`
- `docs/PHASE4_PASS8_EVIDENCE_AND_PERFORMANCE_TRUTH_2026-07-19.md`
- `docs/PHASE4_PASS9_AUTOMATON_AND_PAPER_ECOSYSTEM_2026-07-19.md`
- `docs/PHASE4_PASS10_RELEASE_READINESS_AND_SOAK_2026-07-19.md`
- `docs/STAGED_PUBLIC_TESTING_RELEASE_STATUS_2026-07-19.md`
- `docs/PHASE4_FINAL_HANDOFF_2026-07-19.md`
- `CODEBASE_FULL_DOCUMENTATION.md` and `docs/FULL_SYSTEM_DOCUMENTATION.md`
  for historical/deeper subsystem notes.

## 17. Next actions before public testing

1. Repair the Windows pytest temp ACL or run CI on a clean writable runner.
2. Update the token smoke test to match the authenticated API contract.
3. Re-run the complete suite with zero failures/errors.
4. Rehearse migration `0020_payment_receipts` on disposable Postgres.
5. Deploy to Railway staging with Redis, Telegram, provider, and Paystack test
   credentials.
6. Exercise every command/button in the limited-public checklist.
7. Run and review a 24–72 hour soak with no unexplained delivery/outcome
   regressions.
8. Only then evaluate paid beta; do not enable auto/copy or real payouts as a
   shortcut.
