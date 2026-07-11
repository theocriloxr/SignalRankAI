# Engine Market Data Provider Stabilization Report - 2026-07-03

## Scope

This pass addresses the latest Railway logs where the engine repeatedly produced:

- `market_fetch_error=TimeoutError`
- `market_data_assets=0`
- `max_score=None`
- `max_score_absent_reason=market_fetch_error:TimeoutError`
- repeated provider fetch completions after the engine cycle had already timed out

The evidence showed that provider calls could succeed individually, but the batch-level engine fetch was timing out and discarding the entire scan.

## Changes

### Per-Asset Market Fetch Isolation

Updated `engine/core.py` so each asset fetch is wrapped in an individual `asyncio.wait_for(...)`.

The engine now:

- times out one slow asset without timing out the whole batch,
- uses `asyncio.gather(..., return_exceptions=True)`,
- returns partial market data for assets that completed successfully,
- logs per-asset fetch status,
- logs a candle-fetch batch summary.

Default per-asset timeout is now shorter:

- `20s` normal default,
- `30s` when Binance is detected as blocked,
- override with `MARKET_FETCH_TIMEOUT_SECONDS`.

This keeps a 20-asset batch within the outer `ENGINE_MARKET_FETCH_TIMEOUT_SECONDS` window when concurrency is healthy.

### Usable Market Data Accounting

The engine now counts `market_data_assets` as assets with usable candle payloads, not merely assets that returned empty dictionaries.

This prevents misleading diagnostics such as "20 market data assets" when all 20 assets actually failed candle validation.

### Max Score Absence Reason

The engine and `/engine_debug` now expose why `max_score` is absent, including:

- `market_fetch_error:<error>`
- `market_data:no_candles_all_assets`
- `market_data:no_assets_returned`
- `strategy_generation:no_strategy_signals`
- `strategy_generation:no_consensus`
- `scoring:no_scored_candidates`

### Outcome Notification Idempotency

Outcome notifications now use an atomic delivery claim before Telegram I/O.

This prevents duplicate close notifications when multiple workers see the same pending outcome at the same time.

Stuck `sending` notifications are recoverable after:

- `OUTCOME_NOTIFICATION_CLAIM_STALE_SECONDS` default `300`

### Database Pool Defaults

Railway pool defaults were raised from the old emergency cap to production-sized defaults:

- `DB_POOL_SIZE=20`
- `DB_MAX_OVERFLOW=20`
- `DB_POOL_SIZE_RAILWAY=20`
- `DB_MAX_OVERFLOW_RAILWAY=20`

Absolute caps remain available:

- `DB_POOL_RAILWAY_ABSOLUTE_CAP`
- `DB_MAX_OVERFLOW_RAILWAY_ABSOLUTE_CAP`

### Admin Diagnostics

Added `/engine_debug` for admins and owners.

It reports the latest engine cycle from `engine:last_cycle`, including:

- status,
- cycle/round,
- duration,
- assets attempted,
- usable market data assets,
- market fetch timing/error,
- max score,
- score absence reason,
- key pipeline counters.

## Operational Interpretation

If `/engine_debug` shows:

`market_data_assets=0` and `market_fetch_error=TimeoutError`

the issue is still provider fetch latency or a blocking provider path.

If it shows:

`market_data_assets>0` and `max_score_absent_reason=strategy_generation:no_strategy_signals`

then market data is flowing and the next investigation should move to strategy generation, feature construction, consensus, or scoring.

## Recommended Railway Settings

For the current monolith deployment:

```text
DB_POOL_SIZE=20
DB_MAX_OVERFLOW=20
DB_MAX_CONCURRENT_SESSIONS=40
DB_POOL_TIMEOUT_SECONDS=30
DB_COMMAND_TIMEOUT=45
MARKET_CACHE_FETCH_CONCURRENCY=8
MARKET_FETCH_TIMEOUT_SECONDS=20
ENGINE_MARKET_FETCH_TIMEOUT_SECONDS=180
OUTCOME_NOTIFICATION_CLAIM_STALE_SECONDS=300
```

If Railway Postgres is on a small plan, lower these together rather than only lowering the pool:

```text
DB_POOL_SIZE=8
DB_MAX_OVERFLOW=4
DB_MAX_CONCURRENT_SESSIONS=12
```

## Verification

Compile coverage:

```text
python -m py_compile engine/core.py engine/admin_pulse.py db/session.py db/pg_features.py engine/realtime_outcome_tracker.py signalrank_telegram/commands.py signalrank_telegram/bot.py signalrank_telegram/command_access.py tests/test_monolith_hardening_defaults.py tests/test_deploy_log_regressions.py tests/test_trader_profiles_and_platform_reliability.py
```

Regression tests added/updated:

- market-data batch timeout isolation,
- outcome notification claim-before-send,
- production DB pool defaults,
- `/engine_debug` registration and admin gating.
