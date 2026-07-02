# Railway Stabilization And System Hardening Report - 2026-07-02

## Scope

This pass moved the latest stabilization work into `SignalRankAI1` and focused on the live Railway symptoms from the July 2 logs:

- PostgreSQL pool exhaustion under monolith scheduler load.
- `/signals` not matching signals actually delivered to the requesting user.
- `/system` being planned but not registered.
- Stock/index/asset discovery diagnostics being too shallow for production triage.
- yfinance connector candles failing freshness checks because they lacked `timestamp`.
- Telegram flood-control retries not being centrally throttled.
- Short-timeframe signals being delivered hours after generation.

## Implemented Changes

### Database Concurrency

File: `db/session.py`

- Added a process-wide DB session gate around `get_session()`.
- Default Railway behavior is conservative: `DB_MAX_CONCURRENT_SESSIONS=1` unless explicitly overridden.
- Added session metrics:
  - opened
  - closed
  - active
  - waiting
  - errors
- Added `DB_SESSION_GATE_TIMEOUT_SECONDS` support.

This directly targets log errors such as:

```text
QueuePool limit of size 2 overflow 0 reached, connection timed out
```

### Database Health Visibility

File: `signalrank_telegram/commands.py`

- `/db_health` now shows session gate limit, active sessions, waiting sessions, errors, opened, and closed counts.
- Existing pool and Postgres activity details remain intact.

### Delivered Signal Query Semantics

File: `db/pg_features.py`

- Added `list_delivered_signals_for_user()`.
- The query starts from `signal_deliveries` and joins to `signals`, instead of listing raw generated signals.
- Supports:
  - active
  - running
  - closed
  - all
  - winners
  - losers
  - missed
  - asset filter
  - lookback window
  - strict `sent_ok=True`
- Active message fallback remains for active/running signals when Telegram definitely received a message but delivery marking was interrupted by DB pressure.

### `/signals` Command

File: `signalrank_telegram/commands.py`

- Default is now: delivered-to-me, active, last 7 days.
- Added parsing for:
  - `/signals today`
  - `/signals week`
  - `/signals 30d`
  - `/signals active`
  - `/signals running`
  - `/signals closed`
  - `/signals all`
  - `/signals winners`
  - `/signals losers`
  - `/signals missed`
  - `/signals asset XAUUSD`

### `/system` Command Registration

Files:

- `signalrank_telegram/commands.py`
- `signalrank_telegram/bot.py`
- `signalrank_telegram/command_access.py`

Implemented `/system` as an admin-gated alias for the operations health view and registered it in:

- Bot handler table.
- Per-tier command scope.
- Command access map.
- Help/description metadata.

### Asset Discovery Diagnostics

File: `signalrank_telegram/commands.py`

Expanded `/assets` diagnostics:

- `/assets discovered`
- `/assets inactive`
- `/assets providers`
- `/assets coverage`
- `/assets failing`
- `/assets quarantined`
- `/assets liquidity`
- `/assets sessions`
- `/assets pending`
- `/assets health`

These expose discovery counts, provider state, samples by asset class, inactive managed assets, and unhealthy provider snapshots.

### yfinance Timestamp Normalization

Files:

- `data/connectors/yfinance_adapter.py`
- `data/market_data.py`

Fixed yfinance connector output so every candle now includes:

- `time`
- `timestamp`

Both are normalized from the dataframe index into epoch milliseconds. `market_data._sanitize_ohlcv()` also backfills `timestamp` from `time` as a fallback.

This targets log warnings such as:

```text
Staleness check failed for 1m: no timestamp in latest candle
```

### Telegram Flood-Control Guard

File: `signalrank_telegram/bot.py`

- Added `_telegram_send_message_guarded()`.
- Serializes sends per chat.
- Adds a small global pacing delay.
- Honors Telegram `RetryAfter`.
- Caps retry attempts instead of retrying forever.
- Routed generic and signal-engagement sends through the guarded path.

New environment variables:

- `TELEGRAM_GLOBAL_SEND_DELAY_SECONDS` default `0.08`
- `TELEGRAM_RETRY_AFTER_MAX_SECONDS` default `180`
- `TELEGRAM_SEND_MAX_ATTEMPTS` default `2`

### Stale Signal Delivery Gate

Files:

- `engine/delivery_freshness.py`
- `signalrank_telegram/bot.py`
- `tests/test_delivery_freshness.py`

Added a hard delivery freshness gate so stale opportunities are rejected before Telegram delivery instead of merely showing `Freshness` and `Age` in the message.

The gate now checks:

- signal age by timeframe,
- user trade profile maximum age,
- remaining opportunity decay,
- live price availability,
- current setup validity through the existing stale-signal validator,
- whether TP/SL has already been reached.

This directly targets the production failure where a `5m` signal could be generated nearly five hours earlier and still be delivered.

The resend pipeline also expires stale candidates before sending, so DB or scheduler recovery should not flush old signals to users.

## Railway Environment Variables To Review

Recommended production values for the current Railway monolith shape:

```text
DB_MAX_CONCURRENT_SESSIONS=1
DB_SESSION_GATE_TIMEOUT_SECONDS=30
DB_POOL_SIZE_RAILWAY=2
DB_MAX_OVERFLOW_RAILWAY=0
DB_POOL_TIMEOUT_SECONDS=30
TELEGRAM_GLOBAL_SEND_DELAY_SECONDS=0.08
TELEGRAM_RETRY_AFTER_MAX_SECONDS=180
TELEGRAM_SEND_MAX_ATTEMPTS=2
DELIVERY_FRESHNESS_GATE_ENABLED=true
DELIVERY_REQUIRE_LIVE_PRICE=true
DELIVERY_DEFAULT_MAX_SIGNAL_AGE_MINUTES=60
DELIVERY_OPPORTUNITY_MIN_REMAINING_PCT=30
DELIVERY_MAX_SIGNAL_AGE_BY_TF_MINUTES={"1m":2,"5m":10,"15m":20,"1h":60,"4h":180,"1d":720}
DELIVERY_MAX_SIGNAL_AGE_BY_PROFILE_MINUTES={"scalp":10,"day":45,"swing":360,"position":4320}
NO_CANDLE_LOG_COOLDOWN_SECONDS=900
PROVIDER_OUTAGE_ALERT_SCHEDULE_MINUTES=10,30,60
PROVIDER_OUTAGE_ALERT_INTERVAL_MINUTES=60
```

If Railway Postgres is upgraded and `max_connections` is proven higher, `DB_MAX_CONCURRENT_SESSIONS` can be raised carefully to `2`, then monitored through `/db_health`.

## Verification

Commands run:

```text
python -m py_compile db/session.py db/pg_features.py data/connectors/yfinance_adapter.py data/market_data.py signalrank_telegram/commands.py signalrank_telegram/bot.py signalrank_telegram/command_access.py
python -m pytest tests/test_trader_profiles_and_platform_reliability.py tests/test_deploy_log_regressions.py -q
python -m py_compile engine\delivery_freshness.py signalrank_telegram\bot.py
python -m pytest tests\test_delivery_freshness.py tests\test_trader_profiles_and_platform_reliability.py tests\test_deploy_log_regressions.py -q
```

Result:

```text
19 passed, 3 warnings
24 passed, 3 warnings
```

Warnings are pre-existing deprecation/runtime warnings:

- `datetime.utcnow()` deprecation.
- Eventlet deprecation from an installed dependency path.

## Current Condition

The project is materially more stable after this pass, but it still requires live Railway evidence before it can be called production-complete.

Most important next checks after deploy:

- `/db_health` should show low or zero waiting sessions during active scans.
- Railway logs should stop showing repeated `QueuePool limit ... timed out`.
- yfinance fallback candles should no longer fail with `no timestamp in latest candle`.
- `/signals` should show only signals delivered to the requesting Telegram account.
- `/system` should execute for admin/owner users.
- `/assets discovered` and `/assets providers` should explain why stocks or indices are absent instead of leaving only log warnings.
- Telegram flood-control warnings should decrease; if they persist, lower send volume or increase `TELEGRAM_GLOBAL_SEND_DELAY_SECONDS`.
- Short-timeframe signals should be rejected or expired if their age exceeds the delivery freshness gate.

## Remaining Live-Evidence Items

These cannot be proven from local tests alone:

- Real Railway Redis/Postgres behavior under a multi-hour soak.
- Real Telegram flood-control behavior with the production audience.
- Live provider coverage for stocks and indices during their market sessions.
- MT5/Binance/Bybit broker order placement in sandbox/live environments.
- Actual win-rate improvement, because win rate requires statistically meaningful tracked outcomes after the infrastructure stops dropping or misclassifying signals.

## Operator Notes

Do not raise signal volume until:

- DB pressure is clean for at least one full trading day.
- Outcome tracking coverage improves materially.
- `/signals`, `/mission`, and inline signal buttons match delivered active signals.
- Provider freshness is clean for the assets being scanned.

Quality and win rate depend on stable data, stable delivery, and reliable outcome tracking first.
