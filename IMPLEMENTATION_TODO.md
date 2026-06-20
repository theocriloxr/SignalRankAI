# SignalRankAI All Priority Implementations Detailed Plan

## Priority 1: Critical Production Bugs (START HERE)

### 1.1 Signal Deduplication - Fingerprint Fix + Redis Lock
**Files:** engine/signal_deduplicator.py, db/pg_features.py

**Current State:**
- db/pg_features.py already removed candle_timestamp from fingerprint ✅
- engine/signal_deduplicator.py uses fingerprint with asset, direction, timeframe, strategy_group

**Still Needed:**
- Add Redis lock: signal_lock:{asset}:{direction}:{timeframe}
- TTL: 4 hours for 4H signals
- Add PostgreSQL uniqueness check

**Implementation:**
```python
# In engine/signal_deduplicator.py or db/pg_features.py
async def check_active_signal_lock(asset: str, direction: str, timeframe: str) -> bool:
    """Check if active signal exists for asset+direction+timeframe"""
    key = f"signal_lock:{asset}:{direction}:{timeframe}"
    return await state.cache_exists(key)

async def acquire_active_signal_lock(asset: str, direction: str, timeframe: str, ttl_seconds: int = 14400) -> bool:
    """Acquire lock with 4h default TTL"""
    key = f"signal_lock:{asset}:{direction}:{timeframe}"
    # Only set if not exists (atomic)
    return await state.cache_set_if_not_exists(key, "1", ex=ttl_seconds)
```

### 1.2 Active Signal Protection
**Files:** engine/core.py, db/pg_features.py

**Current:** Already has active_trade check in engine/core.py but at storage stage.

**Needed:** Check BEFORE generating new signal
- Query for active signal with same asset+direction+timeframe
- Skip generation if active signal exists

### 1.3 Telegram Delivery Cooldown (Per-User Redis Key)
**Files:** signalrank_telegram/bot.py, signalrank_telegram/delivery.py

**Implementation:**
```python
# Delivery cooldown per user per asset
# Key: delivery:{user_id}:{asset}:{direction}
# TTL by tier:
#   VIP = 4h (14400s)
#   Premium = 6h (21600s)
#   Free = 12h (43200s)

TIER_DELIVERY_COOLDOWN_SECONDS = {
    "vip": 4 * 3600,
    "premium": 6 * 3600, 
    "free": 12 * 3600,
}

async def check_delivery_cooldown(user_id: int, asset: str, direction: str) -> bool:
    """Check if delivery cooldown is active"""
    key = f"delivery:{user_id}:{asset}:{direction}"
    return await state.cache_exists(key)

async def set_delivery_cooldown(user_id: int, asset: str, direction: str, tier: str) -> None:
    """Set delivery cooldown"""
    ttl = TIER_DELIVERY_COOLDOWN_SECONDS.get(tier, 12 * 3600)
    key = f"delivery:{user_id}:{asset}:{direction}"
    await state.cache_set(key, "1", ex=ttl)
```

## Priority 2: Buttons Not Working
**Current:** callback_handlers.py already has global callback router ✅

## Priority 3: Outcome Tracking
**Current:** realtime_outcome_tracker.py is already implemented ✅
**Still Needed:** signal_state enum and unify ownership

## Priority 4: Freshness Bug
**Files:** engine/signal_formatter.py, engine/freshness.py
**Needed:** Use one timestamp source

## Priority 5: Stale Signal Logic
**File:** engine/stale_signal_validator.py
**Needed:** Refactor validate() to single result

## Priority 6: Railway Stability
**Files:** railway_main.py, worker/worker.py, db/session.py
**Needed:**
- Redis Health Monitor (PING every minute)
- PostgreSQL Health Monitor (SELECT 1 every minute)
- Engine Heartbeat Table

## Priority 7: Database Indexes
**Files:** db/models.py, alembic/versions/
**Needed:** Add indexes

## Priority 8: Signal Lifecycle
**Files:** engine/core.py, signalrank_telegram/bot.py
**Needed:** Message threading (UPDATE vs NEW SIGNAL thread)

## Priority 9: ML System Confidence Calibration
**Files:** ml/*, engine/core.py
**Needed:** Store predicted_probability and actual_result

## Priority 10: Features (Future)
- Trade Journal
- Signal Replay
- Portfolio Exposure Engine
- Market Regime Detection
- Institutional Scoring
