# Latency, All-Asset and Active-Cooldown Fix — 2026-07-09

## What this patch fixes

Latest Railway logs showed the engine was healthy through market data and scoring:

- `market_data_assets=20`
- `strategy_signals=528`
- `max_score_pre_threshold=97.34`
- `final_signals=24`

But nothing was stored because every final candidate was blocked by:

- `skipped_db_asset_cooldown=24`
- `cooldown(db-asset): active signal exists ...`

That means the issue was not storage timeout anymore. Old active/undelivered/stale signal rows were blocking new signals.

## Code changes

### 1. Delivered-only active asset lock

The DB asset-repeat lock now defaults to blocking only signals that were actually delivered to at least one user.

New default behavior:

- delivered active signals still block repeats
- stale expired rows do not block
- undelivered/reserved/formatter_failed rows do not block
- cooldown precheck fails open by default instead of starving the engine

Relevant envs:

```env
ASSET_REPEAT_LOCK_REQUIRE_DELIVERED=1
ACTIVE_SIGNAL_COOLDOWN_IGNORE_EXPIRED_BY_TIME=1
ASSET_REPEAT_LOCK_HOURS=12
SIGNAL_COOLDOWN_MINUTES=30
COOLDOWN_PREFLIGHT_TIMEOUT_SECONDS=15
COOLDOWN_PREFLIGHT_FAIL_OPEN=1
```

### 2. Gemini circuit breaker

Repeated Gemini 429 errors were making cycles slow and risking late signals. Signal review now degrades quickly to local AI review when Gemini is rate-limited or over budget.

Relevant envs:

```env
GEMINI_SIGNAL_REVIEW_CIRCUIT_BREAKER_ENABLED=1
GEMINI_RATE_LIMIT_COOLDOWN_SECONDS=900
GEMINI_SIGNAL_REVIEW_WINDOW_SECONDS=60
GEMINI_SIGNAL_REVIEW_MAX_CALLS_PER_WINDOW=3
GEMINI_SIGNAL_REVIEW_TIMEOUT_SEC=4
GEMINI_SIGNAL_REVIEW_SYNC_TIMEOUT_SEC=6
AI_REVIEW_FALLBACK_ENABLED=1
```

### 3. All-asset mode override

`ALL_ASSET_MODE=1` now intentionally overrides `CRYPTO_ONLY_MODE=1`. This prevents an old Railway crypto-only variable from accidentally keeping the bot in crypto-only mode.

Relevant envs:

```env
ALL_ASSET_MODE=1
ASSET_CLASSES_ENABLED=crypto,fx,index,commodity,stock
CRYPTO_ONLY_MODE=0
```

### 4. Score saturation defaults tightened

Soft-cap defaults were tightened so scores do not cluster around 97–99 as aggressively.

Relevant envs:

```env
SCORE_SOFT_CAP_ENABLED=1
SCORE_SOFT_CAP_KNEE=90
SCORE_SOFT_CAP_CEILING=97
SCORE_SOFT_CAP_SCALE=25
SCORE_DISPLAY_MAX=97
SCORE_ALLOW_HARD_100=0
```

## Recommended fast-delivery Railway mode

For faster signal delivery, reduce batch size and Gemini budget:

```env
CYCLE_BATCH_SIZE=8
ENGINE_UNIVERSE_CAP=40
ENGINE_CYCLE_SLEEP_SECONDS=20
MARKET_FETCH_TIMEOUT_SECONDS=12
MARKET_TIMEFRAME_FETCH_TIMEOUT_SECONDS=10
MARKET_PROVIDER_TIMEOUT_SECONDS=4
MARKET_CACHE_FETCH_CONCURRENCY=12

GEMINI_SIGNAL_REVIEW_CIRCUIT_BREAKER_ENABLED=1
GEMINI_SIGNAL_REVIEW_MAX_CALLS_PER_WINDOW=3
GEMINI_RATE_LIMIT_COOLDOWN_SECONDS=900
GEMINI_SIGNAL_REVIEW_TIMEOUT_SEC=4
GEMINI_SIGNAL_REVIEW_SYNC_TIMEOUT_SEC=6
```

## Success markers

The next log should show:

```text
skipped_db_asset_cooldown < final_signals
stored > 0
signals_this_batch > 0
delivery summary users_dispatched > 0
telegram_message_id present in /delivery_debug
```

