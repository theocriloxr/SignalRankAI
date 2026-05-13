SignalRankAI — Full System Documentation

Last updated: 2026-05-13

Purpose
-------
This document is a complete, developer-oriented system description for SignalRankAI. It documents the architecture, modules, runtime behavior, environment configuration, data models, signal lifecycle, strategy logic (including the Institutional Momentum Pulse (IMP) strategy), delivery mechanics, ML integration, observability, deployment recommendations, testing, and operational runbook. It aims to provide everything available in the repository and how it is implemented.

Table of contents
-----------------
1. Executive summary
2. High-level architecture and runtime modes
3. Repository layout and module responsibilities
4. Environment and deployment configuration
5. Data ingestion and indicator pipeline
6. Strategy layer (including IMP) and strategy orchestration
7. Engine pipeline, gates and scoring
8. Consensus, confluence and ranking
9. Risk model, expectancy, and dynamic down-weighting
10. Persistence models (DB tables) and key queries
11. Delivery, dispatch, and Telegram bot behaviors
12. Outcome tracking and analytics
13. ML integration: inference, features, and training
14. Scheduling, background jobs and workers
15. Tests and CI guidance
16. Observability and runtime metrics
17. Operational runbook and Railway guidance
18. Recent changes and rationale (what was applied in this session)
19. Next steps, toggles and safe deployment checklist

1. Executive summary
--------------------
SignalRankAI is a multi-stage trading signal generation and delivery system. It consumes market data across asset classes and timeframes, runs modular strategy code to generate candidate setups, and passes candidates through multiple validation and scoring layers (confluence, ML advisory, risk checks) before persisting and delivering signals to users by tier (Free, Premium, VIP). Outcomes are tracked and used to compute live metrics and to inform dynamic weighting.

2. High-level architecture and runtime modes
-------------------------------------------
Runtime modes (selected via `RUN_MODE` env):
- `all`: Monolith (engine + bot + web + worker)
- `engine`: signal generation loop only
- `bot`: Telegram bot and scheduler
- `web`: FastAPI endpoints (health, webhook handlers, payments)
- `worker`: background workers (market monitoring, proxies, maintenance)

Main runtime components:
- `engine/core.py`: main pipeline, run loop, signal generation & persistence.
- `strategies/`: modular strategy implementations including `imp.py`.
- `signalrank_telegram/`: Telegram UX, commands, dispatch and delivery helpers.
- `web/`: FastAPI web endpoints for health/metrics/webhooks.
- `db/`: SQLAlchemy models, repository functions, migrations.
- `ml/`: model inference and training utilities.
- `data/`: provider adapters, WS ingestion, indicator calculations.
- `worker/`: background worker tasks.

3. Repository layout and module responsibilities
-----------------------------------------------
Top-level directories and their intent:
- `engine/`: core intelligence pieces (signal context, risk checks, scoring, consensus, confluence, advanced filters).
- `strategies/`: all strategy groups (trend, momentum, volatility, structure, fx, stock, crypto, fallback, imp..).
- `data/`: fetchers, provider connectors, indicator calculation helpers.
- `signalrank_telegram/`: bot runtime, command handlers, formatting, delivery, and tier logic.
- `db/`: models, migrations, repository functions, and helper queries (pg_features etc.).
- `ml/`: model inference and retrain flows plus feature extraction.
- `web/`: public API endpoints including webhook handlers and health endpoints.
- `docs/`: operational docs and deployment templates.
- `tests/`: pytest test-suite covering strategies, engine, commands, deployment contracts.

4. Environment and deployment configuration
------------------------------------------
Primary runtime configuration is environment-driven (`os.getenv`). Key runtime variables (defaults and roles):
- `DATABASE_URL`, `REDIS_URL`: DB and cache backends.
- `TELEGRAM_BOT_TOKEN`: Bot authentication.
- Provisioning / deployment: `.env.example` updated to include strategy and open-signal caps:
  - `IMP_STRATEGY_ENABLED=1`
  - `IMP_ONLY_MODE=0`
  - `RUN_ALL_STRATEGIES=1`
  - `USE_FALLBACK_STRATEGIES=1`
  - `IMP_FX_SESSION_FILTER_ENABLED=1`
  - `IMP_FX_ALLOWED_SESSIONS=london,newyork,overlap`
  - `EXPECTANCY_HARD_BLOCK_ENABLED=0`
  - `OPEN_SIGNALS_MAX_PER_ASSET=20`
  - `OPEN_SIGNALS_MAX_PER_CLASS=20`

Railway templates and the go-live checklist in `docs/` were updated to document these defaults.

5. Data ingestion and indicator pipeline
---------------------------------------
- `data/fetcher.py` and `data/market_data.py` manage fetching candles and normalizing into a per-asset, per-timeframe structure used by strategies.
- Indicators are computed in `data/indicators.py` and stored in `market_data[timeframe]['indicators']` for each timeframe.
- `data/pair_discovery.py` discovers candidate universe (e.g., trending pairs) used by the round-robin cycle in `engine/core.py`.
- WebSocket adapters (Binance, CryptoCompare) are under `data/` connectors to support low-latency ingestion.
- Market hours and session gating (for FX) are implemented in `data/market_hours.py` and used by IMP and other strategies.

6. Strategy layer (including IMP) and strategy orchestration
-----------------------------------------------------------
Strategy interface:
- Each strategy group exposes functions returning list[dict] candidate signals.
- Each signal dict should include keys like: `asset`, `timeframe`, `direction`, `entry`, `stop_loss`, `take_profit`/`targets`, `strategy_name`, `strategy_group`, `confidence`/`strength`, and optional ML fields.

Strategy orchestration (in `strategies/__init__.py`):
- Env flags control behavior: `RUN_ALL_STRATEGIES`, `USE_FALLBACK_STRATEGIES`, `IMP_STRATEGY_ENABLED`, `IMP_ONLY_MODE`.
- If `IMP_ENABLED`, IMP signals run first and normalized to canonical fields.
- If `IMP_ONLY_MODE` is enabled (off by default) the engine returns only IMP signals.
- When `RUN_ALL_STRATEGIES` is true, run groups: trend, momentum, volatility, structure, stock, tradingview.
- If no main signals and `USE_FALLBACK_STRATEGIES` true, fallback strategies run to produce lower-confidence signals.

Institutional Momentum Pulse (IMP) — `strategies/imp.py`
- Purpose: high-quality confluence entries combining HTF trend + pullback + trigger + POC value + RSI momentum.
- Timeframes: HTF=4h (trend via EMA200), trigger and entry on 1h (EMA50 pullback + engulfing/pin-bar trigger + RSI crossing 50).
- Filters:
  - Require H4 close >/< EMA200 for direction LONG/SHORT.
  - H1 must touch EMA50 within a tolerance derived from ATR.
  - Volume Profile POC check on recent H1 candles.
  - Trigger candle must be bullish/bearish engulfing or pin bar and accompanied by RSI cross around 50.
- SL/TP: ATR-based stop (1.5× ATR) and class-based RR (crypto default 2.0R, others 1.5R).
- Session gating for FX:
  - Several environment knobs: `IMP_FX_OVERLAP_ONLY` (strict overlap mode), and `IMP_FX_SESSION_FILTER_ENABLED` with `IMP_FX_ALLOWED_SESSIONS` string to allow `london`, `newyork`, and/or `overlap`. This supports allowing London and New York sessions separately as requested.
- Output: normalized signal dict with `strategy_name: "Institutional Momentum Pulse"`, `strategy_group: "impulse"`.

7. Engine pipeline, gates and scoring
------------------------------------
Overview (`engine/core.py`) — per-cycle operations:
- Build universe with class coverage (crypto, fx, stock, commodity).
- Batch fetch market data for required timeframes.
- For each asset:
  - Validate candles freshness.
  - Detect market regime (`engine/regime.py`).
  - Run `run_all_strategies(...)` to generate candidate signals.
  - Normalize signals via `SignalController` (if available).
  - Apply consensus filter (`engine/consensus.py`).
  - Deduplicate and compute fingerprints (`db/pg_features.compute_signal_fingerprint`).
  - Strict candidate gating (signal structure validation, risk checks via `engine/risk.py`, confluence checks, news-sentiment gate).
  - ML advisory (non-blocking) and optional ML hard filter.
  - Scoring via `engine/scoring.calculate_signal_score`.
  - Advanced filters and ultra-quality filters (optional global quality lock).
  - Attach timeframe-aware expiry via `signal_context.calculate_signal_expiration` with fallback map for minutes per timeframe.
  - Collapse variants to one best signal per asset+direction using `_collapse_signal_variants`.
  - Final store in DB via `store_signal_compat` and add to trade tracker.

Key gates and behavior:
- Freshness/staleness thresholds based on `CANDLE_STALENESS_MULTIPLIER`.
- Risk gate checks RR >= 1.5 and ATR volatility limits.
- Expectancy gating updated in this pass: default is dynamic down-weight-first, with optional hard-block via `EXPECTANCY_HARD_BLOCK_ENABLED`.
- Open-signal concurrency caps (defaults applied): `OPEN_SIGNALS_MAX_PER_ASSET=20` and `OPEN_SIGNALS_MAX_PER_CLASS=20`. Engine preloads current open counts and prevents adding signals exceeding caps.

8. Consensus, confluence and ranking
-----------------------------------
- `engine/consensus.py` groups signals by `(symbol, timeframe, direction)` and sums weighted confidence; requires minimal `min_score` and `min_groups` (configurable). ML probabilities can boost consensus.
- Confluence engine (`engine/confluence_engine.py`) produces directional votes and drivers; mismatching confluence can veto a signal.
- Ranking and ROI heuristics exist in `engine/ranking.py` and `_signal_roi_score` used to pick best variant per asset.

9. Risk model, expectancy, and dynamic down-weighting
----------------------------------------------------
- `engine/risk.py` contains `calculate_dynamic_risk` and `risk_check`.
- `calculate_dynamic_risk` uses ATR-relative volatility, news sentiment, regime multipliers, and ML probabilities to compute `risk_pct` and other profile hints.
- Expectancy behavior updated per your instruction:
  - Default is to down-weight signals with low/negative `live_expectancy` via a decay multiplier applied to `score` and `confidence` during the final scoring phase. This is implemented in `engine/core.py` as `expectancy_weight` and score/confidence scaling.
  - Hard blocking remains available if `EXPECTANCY_HARD_BLOCK_ENABLED` is set to `1` (disabled by default).

10. Persistence models (DB tables) and key queries
------------------------------------------------
Primary models in `db/models.py`:
- `Signal` — `signal_id`, `asset`, `timeframe`, `direction`, `entry`, `stop_loss`, `take_profit`, `score`, `strategy_name`, `strategy_group`, `ml_probability`, `expires_at`, `expired`, `archived`.
- `Outcome` — stores final outcomes for signals (`status`, `r_multiple`, `percent`, timestamps).
- `SignalDelivery` — per-user delivery records (tracks `sent_ok`, `attempt_count`, `delivered_at`).
- `StrategyStat`, `StrategyLiveMetric`, and `AssetLiveMetric` for tracking performance.

Important DB operations:
- Dedup & fingerprint logic in `db/pg_features.py` to avoid duplicate signals.
- `persist_decision_log` and `decision_log` table store decisions for analytics and traceability.
- `get_user_performance_30d` used by Telegram dashboard command to compute wins/losses over 30 days while counting only delivered signals and related outcomes.

11. Delivery, dispatch, and Telegram bot behaviors
-------------------------------------------------
- `signalrank_telegram/bot.py` boots the Telegram `application` and scheduler, and contains delivery jobs (resend unsent, free-queue dispatch, etc.).
- `signalrank_telegram/commands.py` provides user-facing commands. The `/dashboard` command now includes open-cap usage and class usage summary.
- Delivery pipeline uses `TierDeliveryManager` to route to users by tier and template format via `tier_signal_formatter`.
- Free tier uses delayed randomized delivery via `FreeSignalQueue` logic in `db/pg_features.py`.
- Delivery dedup and idempotence rely on `SignalDelivery` and repository checks to prevent duplicate deliveries.

12. Outcome tracking and analytics
----------------------------------
- `engine/realtime_outcome_tracker.py` and `core/trade_tracker.py` maintain open trades and close them when TP / SL / time_stop conditions are met.
- Outcome persistence to `Outcome` then triggers notification fanout for users who received the signal, and increments strategy metrics stored in `StrategyLiveMetric` and `AssetLiveMetric`.
- The dashboard and stats commands compute 30-day wins/losses using `SignalDelivery` and `Outcome` relations while ensuring only delivered signals are counted (dashboard query revised to restrict to `SignalDelivery.sent_ok=True`).

13. ML integration: inference, features, and training
----------------------------------------------------
- `ml/inference.py` defines `MLFilter` which provides non-blocking advisory outputs; `ml` probabilities may be used as a boost multiplier in consensus and scoring.
- Feature extraction occurs in `ml/features.py` and in-engine feature derivation (price velocity, ATR regime, relative volume, MTF trends) in `engine/core.py` and `engine/signal_analytics.py`.
- Offline training scripts: `ml/train_model.py`, `ml/retrain.py`, and `ml/optuna_tuner.py`.
- Model artifacts: `ml/model.json` and `ml/model_manifest.json`.

14. Scheduling, background jobs and workers
-----------------------------------------
Background tasks include:
- Resend unsent signals job
- Free-signal queue deliveries
- Outcome notification fanout
- Weekly and daily recaps
- ML retrain and threshold refresh
- Auto-kill/auto-throttle monitors

Jobs are scheduled via the bot scheduler (in `signalrank_telegram/bot.py`) and/or worker processes.

15. Tests and CI guidance
------------------------
- Pytest is used with `pytest.ini` configured. Key tests include `test_imp_strategy.py`, `test_risk_dynamic.py`, `test_command_contracts.py` and many more.
- Recent changes were validated via a focused suite:
  - IMP strategy tests
  - Risk dynamic tests
  - Command contracts

16. Observability and runtime metrics
------------------------------------
- FastAPI `/metrics` endpoint and internal logging provide metrics for queue depths, DB pool metrics and error rates.
- Sentry integration optional via `SENTRY_DSN`.
- Redis-backed queue size metrics are used for webhook queue monitoring.

17. Operational runbook and Railway guidance
-------------------------------------------
- Use `docs/RAILWAY_GO_LIVE_CHECKLIST.md` and `docs/RAILWAY_VARIABLE_MATRIX.md` to map environment variables and preflight checks.
- Suggested deployment sequence: push code → set `AUTO_MIGRATE=false` → deploy → run migrations manually → validate readiness → flip any toggles.
- Post-deploy smoke tests available in `scripts/post_deploy_smoke.py`.

18. Recent changes and rationale (this session)
---------------------------------------------
Applied the following changes per your requests in this session:
- Enabled `USE_FALLBACK_STRATEGIES` by default and left IMP enabled so "all strategies + IMP" run by default (`strategies/__init__.py`). Rationale: you requested all strategies plus IMP mode enabled.
- Enhanced IMP FX session gating (`strategies/imp.py`): added explicit `IMP_FX_ALLOWED_SESSIONS` to support `london,newyork,overlap` and added London and New York session checks. Rationale: allow London and NY separately.
- Changed expectancy handling (engine): implemented dynamic down-weight-first behavior instead of immediate hard-block. Hard-block remains optional via `EXPECTANCY_HARD_BLOCK_ENABLED`. Rationale: you asked to "dynamicdown weight first".
- Implemented open-signal concurrency caps (`engine/core.py`): `OPEN_SIGNALS_MAX_PER_ASSET` and `OPEN_SIGNALS_MAX_PER_CLASS` default to 20 and enforced pre-store. Rationale: you specified `20`.
- Dashboard improvements (`signalrank_telegram/commands.py`): added live open cap and class/asset usage summary.
- Added runtime defaults into `.env.example` and updated Railway checklist docs.
- Tests updated and executed; focused regression suite passed.

19. Next steps, toggles and safe deployment checklist
---------------------------------------------------
Short commands to run locally for validation:

```bash
# run targeted tests
.venv/Scripts/python -m pytest tests/test_imp_strategy.py tests/test_risk_dynamic.py tests/test_command_contracts.py

# run the engine loop once (local dev helper)
python scripts/run_engine_brief.py

# run post-deploy smoke checks
python scripts/post_deploy_smoke.py
```

Recommended runtime toggles for canary rollout:
- Start with `IMP_ONLY_MODE=0` and monitor performance. If you want a strict canary run only IMP: `IMP_ONLY_MODE=1`.
- Keep `EXPECTANCY_HARD_BLOCK_ENABLED=0` initially so poor-expectancy signals are down-weighted instead of blocked.
- Monitor `OPEN_SIGNALS_MAX_PER_ASSET` and `OPEN_SIGNALS_MAX_PER_CLASS` metrics and lower if execution capacity is constrained.

End of full documentation.
