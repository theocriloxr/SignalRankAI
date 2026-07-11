# SignalRankAI Full Codebase Documentation

Generated on 2026-05-25.

This document provides a file-by-file walkthrough of the codebase, describing what each file does and how its logic works from top to bottom. It is intentionally detailed and follows the structure of the repository.

## Table of Contents

- 1. Root files
- 2. core/
- 3. data/
- 4. db/
- 5. engine/
- 6. ml/
- 7. payments/
- 8. services/
- 9. signalrank_telegram/
- 10. signalrank_discord/
- 11. strategies/
- 12. storage/
- 13. utils/
- 14. web/
- 15. worker/
- 16. admin/
- 17. scripts/
- 18. tests/
- 19. alembic/ and db/migrations/
- 20. telegram/ (legacy)

---

## 1. Root files

This section documents important top-level files like `README.md`, `main.py`, `run_server.py`, configuration (`config.py`, `.env` usage), and operational scripts (`deploy.sh`, `deploy.bat`). It summarizes purpose, startup entrypoints, environment variables, and quick-start commands so operators can run the service locally or in CI.

---

## 2. core/

### core/circuit_breaker.py

Top to bottom logic:
- Imports time utilities, deque, and dataclass for lightweight circuit tracking.
- Defines `CircuitConfig` with thresholds for failure count, rolling window duration, and open duration.
- Defines `CircuitBreaker` which stores recent failure timestamps and an open-until timestamp.
- `_now()` returns the current epoch seconds used for comparisons.
- `_prune()` removes failure timestamps older than the configured rolling window.
- `allow()` returns False if the breaker is still open; otherwise prunes and allows.
- `record_success()` resets the breaker by clearing failures and closing it.
- `record_failure()` appends the current timestamp, prunes, and opens the breaker if the threshold is met.
- Maintains a module-level `_provider_breakers` dict keyed by provider name for shared breaker instances.
- `provider_breaker(name)` returns the per-provider breaker, creating it if missing.
- `get_provider_breaker_snapshot()` exposes a read-only snapshot for dashboards, including remaining open time and config.

### core/command_limits.py

Top to bottom logic:
- Imports tier limits from `core.tier_constants` for consistent defaults.
- Defines rate limit profiles for tier checks, public commands, and `/start` flood control.
- Defines free-tier exposure constants derived from `TIER_SCORE_THRESHOLDS` and `TIER_DAILY_LIMITS`.

### core/performance.py

Top to bottom logic:
- Defines `avg_reward_risk()` stub returning a fixed average RR (currently 1.8).
- Defines `strategy_stats(strategy_name)` that attempts to load performance for a strategy from DB; uses a sync runner to call async DB logic; falls back to zeros on any error.
- Defines `dynamic_weight(strategy_name)` that adjusts a multiplier based on win-rate thresholds.
- Defines `PerformanceTracker`:
	- `reset()` initializes a defaultdict of per-strategy counters.
	- `log_trade()` updates trade counts, win/loss counters, total returns, and last update; optionally broadcasts if `OUTCOME_BROADCAST_ENABLED` is enabled.
	- `get_stats()` returns per-strategy or all-strategies stats; calculates win rate and average return.
	- `report()` builds a multi-line human-readable summary.
- Instantiates a module-level singleton `performance_tracker`.

### core/redis_cache.py

Top to bottom logic:
- Implements a thin Redis-backed cache via `core.redis_state.state` with JSON payloads and TTLs.
- `CACHE_TTL` holds category TTLs in seconds.
- `cache_get()` loads JSON, checks embedded TTL, and returns the cached value if not expired.
- `cache_set()` writes a JSON payload that includes TTL and `set_at` timestamp.
- `cache_key()` generates a deterministic MD5 hash from prefix and args for stable cache keys.
- `cached_market_data()` and `cache_market_data()` wrap the generic cache APIs for market data.
- `cached_signal()` and `cache_signal()` handle signal snapshots.
- `cached_user_prefs()` and `cache_user_prefs()` handle user preferences.
- `cached_news_sentiment()` and `cache_news_sentiment()` handle sentiment scores.
- `cache_stats()` returns hit/miss/eviction stats and computes hit rate.
- `record_cache_hit()` and `record_cache_miss()` increment counters in Redis.

### core/redis_state.py

Top to bottom logic:
- Imports Redis and Postgres clients if available; otherwise uses in-memory fallback.
- Defines keys and prefixes for kill switch, extra signals, delivery tracking, and queues.
- `_webhook_queue_key()` reads an override from env for the Telegram updates queue key.
- `_redis_max_connections()` returns a fixed high connection count for production.
- `_resolve_redis_url()` resolves Redis URL from env, used by sync helpers.
- Defines delivery tracking helpers: `mark_signal_delivered_sync()`, `was_signal_delivered_sync()`, `get_delivered_signals_sync()`.
- Defines `KillSwitchState` dataclass for uniform returns.
- Defines `RedisState` class with sync and async-style APIs:
	- Maintains an in-memory store, optional Redis client, optional Postgres DSN, and a small LRU cache.
	- Provides a background flush thread that writes queued key updates to the Postgres `runtime_state` table.
	- `_get_pg_dsn()` resolves a sync DSN using `config.resolve_database_url` and normalizes schemes.
	- `_pg_exec_one()` executes a short-lived Postgres query for thread safety.
	- `_cache_get()` and `_cache_set()` provide LRU caching with optional expiry.
	- `_enqueue_write()` and `_flush_pending_once()` buffer and flush writes to Postgres.
	- `_get_redis_sync()` initializes and pings a Redis client; falls back to None on failure.
	- `get_killswitch_sync()` resolves kill switch state from Redis, then Postgres, then memory.
	- `set_killswitch_sync()` writes kill switch state to Redis or Postgres/memory.
	- `set_temp_owner_sync()` grants a temporary owner bypass keyed by user ID and a hashed BYPASS_KEY fingerprint.
	- `has_temp_owner_sync()` validates the bypass and revokes if fingerprints mismatch or TTL expires.
	- `add_extra_signals_sync()` grants additional free signals with TTL via Redis or Postgres.
	- Additional methods (not shown in excerpt) manage cached state, counters, and async wrappers using `asyncio.to_thread`.

### core/settings.py

Top to bottom logic:
- Uses `pydantic` or `pydantic_settings` (v2) to define environment-driven configuration.
- `Settings` includes required values (DATABASE_URL) and optional feature flags, logging, and Telegram timeouts.
- Provides version-specific config for env file loading and extra field handling.
- `get_settings()` lazy-loads settings and resolves a database URL if missing.
- `validate_required_settings()` enforces required fields based on RUN_MODE and logs warnings for optional values.

### core/signal_governor.py

Top to bottom logic:
- Imports `TIER_DAILY_LIMITS` and maps only premium and vip tiers into `MAX_SIGNALS_PER_DAY`.
- `signals_sent_today` tracks counts for PREMIUM and VIP.
- `can_send_signal(tier)` enforces per-day limits for these tiers, otherwise allows.
- `record_signal_sent(tier)` increments counters.

### core/tier_constants.py

Top to bottom logic:
- Defines the canonical tier model and delivery policy in module docstring.
- `TIER_DAILY_LIMITS` and `TIER_SCORE_THRESHOLDS` set per-tier caps and minimum scores.
- `TIER_SIGNAL_DEPTH` defines TP depth and detail level per tier.
- Upgrade prompt frequency constants control free-tier upsell pacing.
- `MAX_SIGNAL_AGE_SECONDS` sets freshness requirements by asset class.
- `PRICE_DRIFT_TOLERANCE` sets allowable deviation between entry and live price by asset class.
- `CANDLE_STALENESS_MULTIPLIER` defaults to 24.0 on Railway, 1.5 otherwise.
- Risk constants: `EXPECTANCY_MIN`, `DD_SOFT_THROTTLE`, `DD_HARD_LIMIT`.
- `STRONG_SENTIMENT_THRESHOLD` for news conflict gates.
- `ACTIVE_SIGNAL_LOOKBACK_HOURS` for monitoring windows.
- Free-tier constants for score limit, daily limit, and proof-feed length.

### core/trade_tracker.py

Top to bottom logic:
- Tracks open trades in memory and updates outcomes based on live prices.
- `_PRICE_CACHE` caches recent prices to reduce external calls.
- `_set_price_cache()` and `_get_price_cache()` manage cache entries and TTLs.
- `_env_get()` reads env with a default fallback.
- `TradeRecord` normalizes signal fields into a consistent trade representation and prepares a target list.
- `open_trades_list` stores active trades in memory.
- `_trade_key()` deduplicates trades using signal ID when available, or a fallback key.
- `_convert_symbol_for_yfinance()` maps exchange symbols to yfinance-friendly tickers.
- `_get_current_price()` tries yfinance, then Binance REST for crypto, then a providers waterfall.
- `price_hit_tp()` checks targets for TP hits; supports partial TP tracking.
- `price_hit_sl()` checks stop loss hits.
- `close_trade()` marks trade outcome as TP/SL/PARTIAL_TP based on targets hit.
- `add_trade()` adds trades to the open list, skipping duplicates.
- `update_trade_outcomes()` iterates open trades, closes them on TP/SL, and removes them.

### core/validators.py

Top to bottom logic:
- Defines a Prometheus counter `data_validation_failures_total` for failed validations.
- `validate_candles()` checks presence and shape of OHLC data; increments counter on failure.

### core/version.py

Top to bottom logic:
- Loads version metadata from environment variables for build-time visibility.
- `get_version_banner()` formats the version, short commit SHA, and build time.

---

## 3. data/

This section describes data ingestion, providers, connectors, and market-data helpers. Key responsibilities:
- Provider adapters and rate-limit logic (`data/providers.py`, `data/connectors/*`).
- Unified fetcher, caching, and provider-health (`data/fetcher.py`).
- Market data normalization, indicators, and pair discovery (`data/market_data.py`, `data/indicators.py`, `data/pair_discovery.py`).
Refer to the subsections below for module-level details already documented.

### data/providers.py

- Purpose: Implements multi-provider candle fetchers and a waterfall fallback strategy across providers (Yahoo, Polygon, TwelveData, AlphaVantage, OANDA, TradingView, Binance, Bybit, CryptoCompare, CoinGecko). It centralizes rate-limit cooldowns, provider cooldown application, and provider-specific adapters.
- Key behaviors:
	- Provider waterfall per asset class (crypto, fx, stock, commodity) with configurable preferred providers via env vars.
	- Rate-limiting hooks: `_rate_limit_cooldown_seconds()` and `_maybe_apply_rate_limit_cooldown()` apply cooldowns on 429s or provider-specific messages.
	- Local per-provider cooldown state stored in `_PROVIDER_COOLDOWN` and last-call timestamps in `_PROVIDER_LAST_CALL`.
	- Bridge functions for specific providers: `fetch_polygon_candles`, `fetch_twelvedata_candles`, `fetch_yahoo_candles`, `fetch_binance_ccxt_candles`, etc.
	- Caching helpers (`_get_candles_cache`, `_set_candles_cache`) and `_final_or_cache` fallback to serve cached or stale data when live providers fail.


---

## 4. db/

This section documents the database layer: ORM models, async helpers, and business-logic persistence functions. It explains idempotency guarantees (fingerprint dedupe), delivery auditing (`SignalDelivery`), free-queue scheduling, and outcome recording. See `db/models.py`, `db/pg_features.py`, and `db/pg_compat.py` for concrete contracts and env tuning knobs.

### db/pg_compat.py

- Purpose: Synchronous compatibility wrappers for async DB features so code running outside an event loop can call DB helpers.
- Key behaviors:
	- `postgres_enabled()` checks whether a database URL is configured.
	- `get_all_user_ids_compat()` and `store_signal_compat(signal)` run async DB coroutines via `utils.async_runner.run_sync` to provide a synchronous API; `store_signal_compat` calls `db.pg_features.get_or_create_signal` and returns the `signal_id`.


### db/pg_features.py

- Purpose: Collection of database access helpers and business-logic-oriented operations (create/get signals, record deliveries, outcomes, runtime state helpers, and strategy stats).
- Key behaviors:
	- `get_or_create_signal(session, signal, dedup_hours)` implements strict fingerprint-based deduplication and inserts or updates `Signal` rows, normalizing `take_profit` into JSON and writing `created_at`/`expires_at` fields.
	- `record_signal_delivery(session, telegram_user_id, signal_id, tier_at_send)` implements per-user and per-tier deduping, market cooldowns, dedupe reset epoch, and writes `SignalDelivery` rows safely.
	- Many other helpers exist for outcomes (`upsert_outcome`), outcome notifications, runtime state integer storage, strategy stats, and bot events. The module is central to persistence and enforces idempotency and deployment-safety patterns (e.g., dedupe-reset epochs, TTL-based caches).


---

## 5. engine/

This section covers the engine that runs strategies and produces candidate signals. It includes per-asset orchestration, ML integration, dynamic risk checks, scoring, deduplication, and hand-off to persistence and delivery subsystems. The subsections below summarize strategy generation, deduplication, ranking, realtime outcome tracking, and core loop behavior.

### engine/strategies/signal_generator.py

- Purpose: Implements a suite of ~20 technical strategies that generate candidate `StrategySignal` objects. Each strategy emits a structured signal (asset, timeframe, entry, stop_loss, take-profit levels, score, strategy metadata, ML features, and confidence).
- Key behaviors:
	- `SignalGenerator.generate_signals()` runs many small strategy functions (EMA crossover, MACD histogram, ADX directional, Supertrend, Ichimoku, Parabolic SAR, volume/volatility breakouts, pattern detectors) and collects signals above a quality floor (score >= 70).
	- Each strategy returns a `StrategySignal` dataclass-like object with `ml_features` used later by ML ranking.
	- Strategy selection per-asset uses `StrategySelector` to prefer asset-class-appropriate strategies.


### engine/signal_deduplicator.py

- Purpose: Detect and avoid duplicate signals and track ML rejections for offline learning.
- Key behaviors:
	- `SignalDeduplicator` provides a DB-backed dedup check (`is_duplicate`) that searches recent signals (default dedup window 1 hour in the local in-memory cache, controlled via env) and a lightweight in-process registration API.
	- `MLRejectionTracker` persists signals that were rejected by filters or ML for later outcome labeling. It supports configurable outcome windows (5m,15m,1h,4h,1d by default), parsing TP levels, and backfilling decision-log rejections into `MLRejectedSignal` rows for supervised learning.


### engine/ranking.py

- Purpose: Blend base strategy score with ML model probability to split signals into `vip`, `premium`, and `free` buckets.
- Key behaviors:
	- Calls `engine.ml.score_signal(signal)` to get an ML probability (0–1) and computes `score_ml = ml_prob * 100`.
	- Blends final score as `0.6 * base_score + 0.4 * ml_score` when ML is available; persists `score_final` and `score_ml` on the signal dict for downstream consumers.
	- Thresholds for VIP / Premium are configurable via env `VIP_SCORE_THRESHOLD` and `PREMIUM_SCORE_THRESHOLD`.


### engine/realtime_outcome_tracker.py

- Purpose: Long-running async task that polls open signals, checks live prices, detects TP/SL hits, persists outcomes, and queues notifications.
- Key behaviors:
	- Periodically fetches unresolved signals (`_fetch_active_signals`) and delivered-but-untracked signals (`_fetch_delivered_untracked_signals`) and resolves outcomes using `_get_live_price()`.
	- Uses robust helpers to parse TP levels and detect hits (`_check_hit`), supports partial TP progress tracking in Redis, and writes outcomes via `db.pg_features.upsert_outcome` and queues notifications.
	- Implements idempotent guards using Redis cached keys so notifications for the same event are not repeated.

### engine/core.py

- Purpose: Main engine loop orchestrating per-asset pipelines. Responsibilities include fetching market data, running strategies, scoring, applying filters (confluence, regime, risk), persisting signals, and triggering deliveries.
- Key storage/delivery behavior:
	- After signal generation and confluence/risk checks, the engine stamps `sig['created_at']` and calls `store_signal_compat(sig)` (db wrapper) to persist the signal.
	- On successful persistence, the engine writes back `sig['signal_id']`, increments `pipeline_stats['stored']`, appends to `stored_signals`, and increments open-trade counters per asset/class.
	- Only signals that were actually stored are added to the in-memory trade tracker via `core.trade_tracker.add_trade()`; this prevents tracking of non-persisted signals.
	- Failures to store are counted in `pipeline_stats['store_failed']` and heatmap diagnostics are recorded when cycles produce no stored signals.
	- Delivery is handled asynchronously by `signalrank_telegram.tier_delivery.TierDeliveryManager` (invoked via `dispatch_signals_async`), which reads the stored signals and sends to eligible users.


---

## 6. ml/

ML artifacts, model scoring wrappers, training utilities, and shadow prediction tables live here. The folder contains model serving wrappers (`engine.ml`), shadow prediction logging, and utilities for building training datasets from outcomes and rejected signals. See the `ml/` module files for model-specific details and how probabilities feed into `engine/ranking.py`.

---

## 7. payments/

Payment integration, subscription management, and webhook handlers live under `payments/` and `paystack/`. This includes payment event parsing, subscription lifecycle updates, and reconciliation helpers used by `db/pg_features` to credit subscriptions and bonuses.

---

## 8. services/

External integrations and platform services such as economic calendar, sentiment providers, proxy management, and auxiliary HTTP services are placed here. Each adapter encapsulates rate limits and graceful fallback logic used by the engine and fetcher.

---

## 9. signalrank_telegram/

Telegram bot logic, tiered formatting, delivery, command handlers, and admin utilities are documented here. Key capabilities covered: dispatch reservation, formatters per tier, developer owner commands, free/random queue handling, and the `/provider_status` diagnostic command. See subsections above for detailed summaries.

### signalrank_telegram/tier_delivery.py

- Purpose: Central tier-based delivery manager that decides eligibility, selects recipients, formats messages per tier, and records delivery telemetry.
- Key behaviors:
	- `TierDeliveryManager.should_send_signal()` enforces per-tier minimum score gates using `core.tier_constants.TIER_SCORE_THRESHOLDS` (sync and async variants available).
	- `format_for_delivery()` chooses the appropriate formatter via `signalrank_telegram.formatter.format_signal` and returns tier-appropriate message text or `None` if filtered.
	- `get_users_for_signal()` delegates to `SignalDistributor` (in `signal_distribution.py`) to sample recipients while enforcing per-user and per-tier dedupe and daily limits.
	- Provides helpers for TP update alerts, no-trade alerts, tier feature descriptions (`get_tier_features`), TP depth (`get_max_tp_level_for_tier`), upgrade prompts, and delivery logging (`log_delivery`, `get_delivery_stats`).
	- A global `_delivery_manager` instance is exposed via `get_delivery_manager()`.


### signalrank_telegram/tier_signal_formatter.py and `signalrank_telegram/formatter.py`

- Purpose: Produce human-friendly HTML/text messages per subscription tier (free, premium, vip, admin) for initial signals, updates (TP/SL), no-trade alerts, and outcome notifications.
- Key behaviors:
	- `tier_signal_formatter` contains low-level helpers to sanitize/format prices, parse TP ladders, ensure a minimum TP ladder per tier, compute RR and expected move percentages, and present freshness/expiry text.
	- `formatter.py` contains high-level tier-based formatters: `format_signal_free`, `format_signal_premium`, `format_signal_vip` and routing helpers that normalize tier and compute risk/confidence tags.
	- Combined, these modules ensure messages are: idempotent-friendly, parse-safe for Telegram `HTML` mode, and tailored to tier features (e.g., VIP receives confluence breakdown and no-trade alerts; Free receives minimal proof messages).


### signalrank_telegram/signal_distribution.py

- Purpose: Smart sampling and delivery gating to spread signals across users and prevent duplicate deliveries.
- Key behaviors:
	- `SignalDistributor` implements per-tier sampling, per-cycle limits, and daily limit enforcement.
	- Uses the `SignalDelivery` DB model to record attempts and prevent re-delivery via a unique constraint (user_id + signal_id).
	- `get_eligible_users_for_tier()` queries users by tier who have not yet received the signal and applies a per-cycle sampling limit.
	- `can_receive_signal()` and `count_delivered_signals_today()` enforce daily limits and provide human-readable reasons for ineligibility.
	- `record_delivery_attempt()` atomically creates the delivery record and logs success/failure, ensuring retries can't re-send the same signal.
	- Exported factory `create_distributor(session)` returns a `SignalDistributor` instance for use by delivery/dispatch code.


### signalrank_telegram/bot.py — `dispatch_signals_async`

- Purpose: Central async entrypoint the bot uses to dispatch stored or generated signals to a single Telegram `user_id` according to tier rules and delivery guarantees.
- High-level flow:
	- Resolve user tier (`resolve_user_tier`) and normalize routing tier.
	- Honor global killswitch and per-user extra-signal quota (`state.get_extra_signals_left_sync`).
	- Accept either a ranked bucket dict (`{'vip': [...], 'premium': [...]}`) or a flat list of signals.
	- Apply canonical per-tier score gates via `TierDeliveryManager.should_send_signal()` when available.
	- Apply user preferences filtering (`user_prefs_store`) for assets/timeframes/strategies.
	- Validate freshness using `engine.stale_signal_validator.validate_signal_freshness()` (async) and drop stale signals.
	- Collapse duplicate/variant signals (keep highest-ROI) and compute simple `entry_status` flags.

- DB-backed reservation & delivery (preferred path for `premium`/`vip`/`owner`/`admin`):
	- Uses `db.session.get_engine_for_event_loop()` and `db.pg_features.get_or_create_signal()` to ensure a single DB `Signal` row exists for the candidate signal.
	- Calls `db.pg_features.record_signal_delivery()` to atomically record the user+signal delivery (unique constraint prevents double-sends).
	- Reserved signals are formatted and sent via `_deliver_or_update_signal_async()`; on success `state.consume_extra_signals_sync()` is called for extra-free users.
	- If reservation fails, a synchronous fallback `_reserve_one()` attempts to create a DB record and send immediately.

- Extra & FREE-tier behavior:
	- `free` users with `extra_left` receive the highest-scoring available signal via `get_highest_scoring_available_signal_for_user()` and are recorded as `premium` deliveries.
	- `free` users without extras are served from a global pool: `get_random_available_signals_for_free_user()` or queued via `queue_free_signal_summary_pg()` to distribute sends across time. A legacy immediate-send path exists controlled by `FREE_DIRECT_DISPATCH` env var.

- Safety & limits:
	- Enforces daily limits using `db.pg_features.count_signals_sent_today()` or local `TIER_DAILY_LIMITS` when DB unavailable.
	- Prevents asset-level burst delivery using `_is_asset_delivery_locked()` checks.
	- Uses `validate_signal_freshness()` and entry checks to avoid sending stale or out-of-entry signals.

- Integration points worth noting:
	- `TierDeliveryManager` for per-tier gating and formatting.
	- `engine.stale_signal_validator` for freshness checks.
	- `db/pg_features` for `get_or_create_signal`, `record_signal_delivery`, and various query helpers used by free/random/extras paths.
	- `_deliver_or_update_signal_async()` performs the actual Telegram send and updates active message keyboards.


### db/pg_features.py — delivery & queue helpers

- Purpose: Async Postgres helpers used by the bot to persist signals, enforce delivery dedupe/ cooldowns, and queue FREE/random signals.
- Key functions used by `dispatch_signals_async` and their contracts:
	- `get_or_create_signal(session, signal, dedup_hours=None) -> Signal`:
		- Normalizes signal fields, computes a fingerprint, and either returns an existing recent `Signal` row (within `dedup_hours`) or inserts a new `Signal` record.
		- Returns a SQLAlchemy `Signal` instance with canonical fields (`signal_id`, `asset`, `timeframe`, `entry`, `take_profit`, `score`, etc.).
	- `record_signal_delivery(session, telegram_user_id, signal_id, tier_at_send) -> bool`:
		- Atomically records a `SignalDelivery` row to prevent duplicate sends for the same `(user_id, signal_id)`.
		- Implements multi-level dedupe/cooldown checks: per-user identical-signal dedupe, same-asset cooldown, market cooldowns (same strat/tf/dir), and delivery window cutoffs controlled via env vars (e.g., `DELIVERY_DEDUPE_HOURS`, `DELIVERY_SAME_ASSET_COOLDOWN_HOURS`).
		- Returns `True` when a delivery row was created (ok to send) or `False` when unique constraint/dedupe prevented creation (treat as already-sent).
	- `count_signals_sent_today(session, telegram_user_id) -> int` / `list_signals_sent_today(...)`:
		- Helpers to enforce daily limits and to show recent deliveries for a user.
	- `queue_free_signal_summary(session, telegram_user_id, signal, delay_minutes=None, daily_limit=None) -> bool`:
		- Queue a single FREE user delivery (records `FreeSignalQueue`), enforcing per-user daily caps tied to the user's join time window.
	- `get_random_available_signals_for_free_user(session, telegram_user_id, limit=2) -> list[Signal]`:
		- Returns random recent `Signal` rows the user hasn't received and which have no outcome; used for free/random distribution.
	- `get_highest_scoring_available_signal_for_user(session, telegram_user_id) -> Optional[Signal]`:
		- Returns the top-scoring recent `Signal` not yet delivered to the user; used for paid extra signals.
	- `queue_random_free_signals_for_all_users(session) -> int`:
		- Periodic job that picks random signals for FREE users and creates `FreeSignalQueue` rows to schedule sends across the user's day window.
	- `upsert_outcome(session, signal_id, status, ...) -> Outcome` and `queue_outcome_notifications_for_outcome(...)`:
		- Record outcome state for a signal (TP/SL/invalid/etc.), merge meta, compute duration, and enqueue notification jobs when outcomes progress.

- Environment variables and tuning points referenced:
	- `SIGNAL_DEDUP_HOURS` — timeframe for fingerprint-based deduping in `get_or_create_signal`.
	- `DELIVERY_DEDUPE_HOURS`, `DELIVERY_SAME_ASSET_COOLDOWN_HOURS`, `DELIVERY_MARKET_COOLDOWN_MINUTES` — control delivery-dedupe/cooldowns.
	- `FREE_DELAY_MINUTES`, `FREE_DAILY_LIMIT`, `FREE_MIN_DELAY_MINUTES`, `FREE_MAX_DELAY_MINUTES` — control free/random queue timing and per-user caps.


### signalrank_telegram/tier_delivery.py — `TierDeliveryManager` (detailed)

- Purpose: Centralizes per-tier gating, formatting selection, recipient sampling, and light-weight delivery logging.
- Public methods and semantics:
	- `should_send_signal(user_tier, score, user_id=None, session=None) -> bool`:
		- Synchronous quality gate using `core.tier_constants.TIER_SCORE_THRESHOLDS`.
		- Returns `False` when `score` is below the tier minimum; callers still enforce daily limits via DB.
	- `should_send_signal_async(...) -> bool`:
		- Async variant for use in `async` flows (same logic).
	- `format_for_delivery(signal, user_tier) -> Optional[str]`:
		- Applies `should_send_signal` then delegates to `signalrank_telegram.formatter.format_signal` to produce tier-appropriate message text (or `None` if filtered).
	- `get_users_for_signal(signal, signal_id, session=None) -> Dict[str, List[int]]`:
		- Uses `SignalDistributor` (in `signal_distribution.py`) to sample recipients per tier while respecting per-cycle and daily limits and dedupe rules.
	- `create_update_alert(signal, tp_number, user_tier) -> Optional[str]`:
		- Return TP-hit update messages (premium+ only) via `format_signal_update_tp_hit`.
	- `create_no_trade_alert(user_tier) -> Optional[str]`:
		- VIP-only no-trade alert helper.
	- `get_tier_features(tier) -> Dict`:
		- Returns a short feature map (min_score, TP depth, updates, priority delivery) used by help pages and command auto-sync.
	- `get_max_tp_level_for_tier(tier) -> int`:
		- Returns the max TP count shown to a tier (reads `core.tier_constants.TIER_SIGNAL_DEPTH`).
	- `should_show_upgrade_prompt(user_tier, signal, signal_count_today) -> bool`:
		- Strategy to show upgrade prompts to free users on high-quality signals or periodic cadence.
	- `can_record_sl_outcome(signal_id, has_tp_been_hit) -> bool`:
		- Business rule to avoid recording SL after TP has been recorded.
	- `format_outcome_for_tier(signal_id, outcome_type, tp_count=None, user_tier='free') -> Optional[str]`:
		- Format outcome notifications per tier, suppressing certain outcomes for lower tiers.
	- `log_delivery(signal_id, user_id, tier, delivered, reason='')` and `get_delivery_stats(days=7) -> Dict`:
		- In-memory delivery log useful for short-term diagnostics and owner `/provider_status` style commands.

- Notes:
	- `TierDeliveryManager` is intentionally lightweight and deterministic — heavy state (daily counts, dedupe, queueing) is stored in Postgres via `db/pg_features` to ensure idempotence across restarts.
	- The global instance `get_delivery_manager()` returns a process-local manager used across the bot and engine.


### engine/core.py — main pipeline

- Purpose: The orchestrator that runs the per-asset signal pipeline: fetch → indicators → strategies → consensus → scoring → filters → persist → dispatch.
- Key responsibilities:
	- Calls `data.fetcher` to obtain candles and indicators, runs `run_all_strategies` and applies `engine.scoring` and `engine.filters`.
	- Integrates ML and advanced filters (`ml_rejection_tracker`, `ultra_quality`, `threshold_optimizer`) to accept/reject signals.
	- Stamps `created_at` on signals, calls `db.pg_compat.store_signal_compat()` (or `db.pg_features.get_or_create_signal`) to persist canonical `Signal` rows, and only tracks stored signals in trade trackers.
	- Emits diagnostics (gate heatmaps) and records diagnostic artifacts under `ENGINE_DIAGNOSTIC_DIR` when many cycles produce no signals for an asset.
	- Hands off stored signals to `signalrank_telegram.bot.dispatch_signals_async()` for delivery, respecting per-tier routing and DB reservation flows.


### data/fetcher.py — unified candle provider & health tracking

- Purpose: Provide a resilient multi-provider candle fetcher with provider waterfall, short-lived in-process caching, provider health tracking, and retry/backoff helpers.
- Key behaviors:
	- `get_candles(asset, timeframe)` coordinates provider priority per asset type (crypto/FX/stocks) and returns normalized candle lists + indicators.
	- Short-lived `_CANDLE_CACHE` coalesces concurrent calls for the same (asset,tf) to prevent N+1 provider calls.
	- Provider health state via `_PROVIDER_HEALTH` with `mark_provider_result()` and `provider_is_healthy()` to deprioritize failing providers.
	- `retry_with_backoff()` and async `retry_async_httpx()` wrappers implement exponential backoff with jitter.
	- Exposes `get_unhealthy_providers()` to show providers down longer than configured thresholds — useful for owner diagnostics and dashboarding.


### core/circuit_breaker.py — per-provider circuit breakers

- Purpose: Lightweight circuit breaker implementation used by provider wrappers to stop calling misbehaving providers for a configured cooldown window.
- Key functions:
	- `CircuitBreaker` class: tracks timestamped failures, prunes by window, enters open state for `open_seconds` when `failure_threshold` exceeded.
	- `provider_breaker(name)` returns a global breaker per provider name.
	- `get_provider_breaker_snapshot()` returns a dict snapshot (open, open_remaining_s, failures, thresholds) for diagnostics and owner commands.


### db/models.py — DB schema overview

- Purpose: Declarative SQLAlchemy models representing users, subscriptions, signals, deliveries, outcomes, queues, and auxiliary tables (managed assets, execution records, webhooks, metrics, ML tables).
- Notable models:
	- `User`, `Subscription` — user/profile and subscription state used for tiering and daily limits.
	- `Signal` — canonical persisted signals (fingerprint, score, ml_probability, rr_estimate, expires_at, created_at).
	- `SignalDelivery` — delivery audit table with a unique constraint on `(user_id, signal_id)` to prevent double-sends.
	- `FreeSignalQueue` — queued entries for FREE-tier randomized dispatch.
	- `Outcome` — captures TP/SL/invalid results and is used to re-enable or suppress notifications.
	- ML and metrics tables: `MLShadowPrediction`, `MLRejectedSignal`, `StrategyStat`, live/asset metrics for reporting and offline training.







### signalrank_telegram/owner_commands.py

- `provider_status_command`: owner/admin command that reports current provider health and circuit breaker snapshot. Gathers data from `data.fetcher.get_unhealthy_providers()` and the internal `_PROVIDER_HEALTH` map, and uses `core.circuit_breaker.get_provider_breaker_snapshot()` to show per-provider circuit breaker state (open/closed, open_remaining, failures). Used by owners to quickly diagnose upstream provider outages and circuit-breaker activations.


---

## 10. signalrank_discord/

Discord integration layer mirroring Telegram functionality for delivery and notifications. Contains formatters and command handlers adapted for Discord channels and guild permissions; reuses much of the Telegram delivery logic with Discord-specific adapters.

---

## 11. strategies/

Contains strategy implementations and strategy registration. Each strategy emits structured candidate signals consumed by the engine; used by `engine/strategies/*` and registered via `strategies.__init__` to allow modular enabling/disabling.

---

## 12. storage/

Helpers and adapters for object storage (S3, MinIO, local disk), snapshotting, and archival of diagnostic artifacts. Used for persisting engine diagnostics, model artifacts, and exported CSV/JSON reports.

---

## 13. utils/

Reusable utilities: `timeutils`, `async_runner`, HTTP clients, JSON helpers, small compatibility shims, and test fixtures. Many modules provide safe sync/async bridges used across engine and bot code.

---

## 14. web/

REST endpoints, webhooks, health checks, and lightweight admin UI pages. Includes `web/healthz.py` for liveness/readiness probes and optional endpoints to expose provider health, queue status, and simple dashboards.

---

## 15. worker/

Background job implementations and scheduler tasks: resend jobs, free-random distribution, outcome notification workers, and periodic maintenance tasks. Hooks into the same DB and Redis state used by the bot for idempotent job execution.

---

## 16. admin/

Operational scripts and admin utilities (e.g., `kill_switch.py`, `auto_kill.py`). Used by operators to control running environments, trigger emergency shutoffs, or perform mass updates.

---

## 17. scripts/

Convenience scripts for deployment, quick DB maintenance, and one-off fixes. Examples: migration helpers, CSV imports, and environment bootstrapping scripts.

---

## 18. tests/

Unit and integration tests organized under `tests/`. Use `pytest` with fixtures that mock DB/Redis where appropriate. Important tests: `test_core.py`, `test_startup.py`, `test_tradingview_integration.py`, and formatters/dispatch tests.

---

## 19. alembic/ and db/migrations/

Alembic migration scripts and manual migration SQL lives here. Migrations include schema updates for `signals`, `signal_deliveries`, outcomes, and ML-related tables. Manual SQL files provide one-off fixes applied during upgrades.

---

## 20. telegram/ (legacy)

Legacy Telegram bot code (older handlers and message formats) retained for backward compatibility. New functionality has been migrated to `signalrank_telegram/`, but legacy code is preserved to ease migrations and testing.
