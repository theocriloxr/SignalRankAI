# SignalRankAI Bug Fixes Comprehensive Implementation Plan

## Executive Summary
This document outlines the implementation plan for fixing 10 priority areas of production bugs affecting SignalRankAI. The fixes target critical production issues causing signal spam, broken buttons, and outcome tracking problems.

---

## Priority 1: Critical Production Bugs

### 1.1 Signal Deduplication

**Files Affected:**
- `engine/signal_deduplicator.py`
- `engine/core.py`
- `db/pg_features.py`

**Current Issue:**
The fingerprint currently includes `candle_timestamp`, `generated_at`, and `created_at` which causes the same trade idea (same asset, direction, entry, SL, TP) to be detected as different signals when regenerated on a different candle.

**Changes:**

1. **db/pg_features.py - compute_signal_fingerprint()**
   - REMOVE: `candle_timestamp`, `generated_at`, `created_at` from fingerprint raw string
   - FINGERPRINT = `asset|timeframe|direction|entry|stop_loss|take_profit|strategy_group|strategy_name`

2. **engine/signal_deduplicator.py - SignalFingerprint.to_key()**
   - USE: `asset|direction|timeframe|strategy_group` (exclude entry_zone)
   - ADD: Redis lock with TTL

3. **db/pg_features.py - get_or_create_signal_impl()**
   - ADD: PostgreSQL unique constraint on (asset, direction, timeframe, status='active')

**Redis Lock Implementation:**
```
Key: signal_lock:{ASSET}:{DIRECTION}:{TIMEFRAME}
TTL: 4 hours (for 4H signals)
Format: signal_lock:SOLUSDT:BUY:4H
```

### 1.2 Active Signal Protection

**Files Affected:**
- `engine/core.py`
- `db/models.py`
- `db/pg_features.py`

**Changes:**

1. **Add active_signal_exists() check in engine/core.py**
   - Before creating signal, check:
     - asset = same
     - direction = same  
     - timeframe = same
     - status = 'active' (not expired, not archived)
   
2. **If active signal exists:**
   - Skip signal generation
   - Log: "Skipping - active signal exists for {asset} {direction} {timeframe}"

3. **PostgreSQL unique constraint:**
   ```sql
   ALTER TABLE signals 
   ADD CONSTRAINT active_signal_unique 
   UNIQUE (asset, direction, timeframe, status) 
   WHERE status = 'active';
   ```

### 1.3 Telegram Delivery Cooldown

**Files Affected:**
- `signalrank_telegram/bot.py`
- `signalrank_telegram/message_router.py`
- `signalrank_telegram/delivery.py`

**Changes:**

1. **Add Redis key per user per asset:**
   ```
   Key: delivery:{USER_ID}:{ASSET}:{DIRECTION}
   TTL by tier:
   - VIP: 4 hours
   - Premium: 6 hours  
   - Free: 12 hours
   ```

2. **Before sending signal:**
   ```python
   if redis.exists(f"delivery:{user_id}:{asset}:{direction}"):
       skip  # Already sent within cooldown period
   ```

3. **Set TTL based on tier:**
   ```python
   tier_ttl = {
       "vip": 4 * 3600,
       "premium": 6 * 3600,
       "free": 12 * 3600
   }
   redis.setex(key, ttl, "1")
   ```

---

## Priority 2: Buttons Not Working

**Files Affected:**
- `signalrank_telegram/bot.py`
- `signalrank_telegram/callback_handlers.py`

**Current Issue:**
Callback logic is scattered across multiple handlers causing:
- Button pressed → Handler A → Handler B → Nothing
- Button registered → Wrong callback data → Ignored

**Changes:**

1. **Create single callback router:**
   - `signalrank_telegram/callback_router.py` (new file)
   - All buttons go through `handle_callback(callback_query)`

2. **Consolidate handlers:**
   - Remove inline callbacks from bot.py
   - Move all to callback_handlers.py
   - Single entry point: callback_router.handle_callback()

3. **Add logging:**
   ```python
   logger.info(f"Button pressed {callback.data}")
   ```

---

## Priority 3: Outcome Tracking

**Files Affected:**
- `engine/realtime_outcome_tracker.py`
- `engine/shadow_outcome_worker.py`
- `engine/core.py`
- `worker/worker.py`
- `db/models.py`

**Current Issue:**
Multiple components (tracker A, tracker B, engine) touch outcome state causing race conditions.

**Changes:**

1. **Choose RealtimeOutcomeTracker as sole owner:**
   - Only `engine/realtime_outcome_tracker.py` writes outcomes
   - All other components read-only

2. **Add signal_state enum:**
   ```python
   class SignalState(str, Enum):
       ACTIVE = "active"
       TP1_HIT = "tp1_hit"
       TP2_HIT = "tp2_hit" 
       TP3_HIT = "tp3_hit"
       SL_HIT = "sl_hit"
       EXPIRED = "expired"
       CANCELLED = "cancelled"
   ```

3. **Remove outcome writes from:**
   - engine/core.py (remove outcome persistence)
   - worker/worker.py (remove outcome updates)

---

## Priority 4: Freshness Bug

**Files Affected:**
- `engine/signal_formatter.py`
- `engine/freshness.py`

**Current Issue:**
Messages show "Freshness: Aging" but "Age: 0m" - impossible state because:
- One module uses `signal.created_at`
- Another uses `candle.timestamp`

**Changes:**

1. **Unify to single source:**
   - Use `signal.created_at` consistently
   - Remove candle.timestamp usage for freshness

2. **If candle.timestamp needed:**
   - Store as `signal.candle_timestamp` 
   - Use ONLY for analytics, not freshness

---

## Priority 5: Stale Signal Logic

**Files Affected:**
- `engine/stale_signal_validator.py`

**Current Issue:**
Logs show "Signal INVALIDATED" then "ACCEPTED" for same asset - contradictory logic.

**Changes:**

1. **Refactor validate() to return single result:**
   ```python
   def validate(signal, live_price) -> ValidationResult:
       VALID = "valid"
       INVALID = "invalid" 
       ENTRY_ZONE_OVERRIDE = "entry_zone_override"
   ```

2. **Remove duplicate validation paths:**
   - One validation check, one result
   - Clear decision tree

---

## Priority 6: Railway Stability

**Files Affected:**
- `railway_main.py`
- `worker/worker.py`
- `db/session.py`

**Changes:**

1. **Redis Health Monitor:**
   ```python
   # Every minute
   redis.ping()
   # If fails: alert admin
   ```

2. **PostgreSQL Health Monitor:**
   ```python
   # Every minute
   await session.execute(select(1))
   # If fails: alert admin
   ```

3. **Engine Heartbeat Table:**
   ```sql
   CREATE TABLE engine_health (
       id SERIAL PRIMARY KEY,
       last_cycle TIMESTAMP,
       last_signal TIMESTAMP,
       last_outcome TIMESTAMP,
       last_news_sync TIMESTAMP
   );
   ```

---

## Priority 7: Database Indexes

**Files Affected:**
- `db/models.py`
- `alembic/migrations/`

**Changes:**

1. **Signals table indexes:**
   ```sql
   CREATE INDEX idx_signals_asset ON signals(asset);
   CREATE INDEX idx_signals_status ON signals(status);
   CREATE INDEX idx_signals_created_at ON signals(created_at);
   CREATE INDEX idx_signals_signal_id ON signals(signal_id);
   ```

2. **Outcomes table indexes:**
   ```sql
   CREATE INDEX idx_outcomes_signal_id ON outcomes(signal_id);
   CREATE INDEX idx_outcomes_status ON outcomes(status);
   CREATE INDEX idx_outcomes_closed_at ON outcomes(closed_at);
   ```

3. **Deliveries table indexes:**
   ```sql
   CREATE INDEX idx_deliveries_user_id ON signal_deliveries(user_id);
   CREATE INDEX idx_deliveries_signal_id ON signal_deliveries(signal_id);
   CREATE INDEX idx_deliveries_asset ON signal_deliveries(asset);
   ```

---

## Priority 8: Signal Lifecycle

**Files Affected:**
- `signalrank_telegram/bot.py`
- `engine/core.py`

**Current Issue:**
Multiple separate messages for same signal:
- NEW SIGNAL
- NEW SIGNAL  
- NEW SIGNAL
- NEW SIGNAL

**Changes:**

Use single message thread:
```
NEW SIGNAL
↓
UPDATED (price refresh)
↓
TP1 HIT (partial close)
↓
TP2 HIT (partial close)
↓
CLOSED (final outcome)
```

1. **Track signal message thread:**
   ```python
   signal.thread_id = signal.signal_id
   signal.parent_id = original_signal_id  # for updates
   ```

2. **Edit message vs new message:**
   - Price refresh: edit original message
   - New signal: new message only if different asset/TF

---

## Priority 9: ML System

**Files Affected:**
- `ml/*`
- `engine/core.py`

**Changes:**

1. **Confidence Calibration:**
   ```python
   # Store predictions
   ml_predictions table:
   - signal_id
   - predicted_probability
   - actual_result
   - created_at
   ```

2. **Monthly Recalibration:**
   ```python
   # At month's end
   actual_win_rate = wins / total_predictions
   adjust_threshold(actual_win_rate)
   ```

---

## Priority 10: Advanced Features

### Trade Journal
- Per user stats: win rate, profit factor, avg RR, monthly ROI

### Portfolio Exposure Engine
- Prevent correlated trades:
  - Don't allow SOL BUY + ETH BUY + BTC BUY simultaneously
- Track correlation between assets

### Market Regime Detection
- Detect: TRENDING, RANGING, VOLATILE, NEWS
- Adapt strategies per regime

### Institutional Scoring
- Add scores:
  - Liquidity sweep
  - Fair Value Gap
  - Market Structure Shift
  - Order Block Strength
  - Volume Imbalance

---

## Implementation Order

1. **Week 1: Priority 1 (Critical)**
   - Signal deduplication fix
   - Active signal protection
   - Delivery cooldown

2. **Week 2: Priority 2-3**
   - Callback consolidation
   - Outcome tracking unification

3. **Week 3: Priority 4-6**
   - Freshness fix
   - Stale signal logic
   - Railway stability

4. **Week 4: Priority 7-10**
   - Database indexes
   - Signal lifecycle
   - ML calibration
   - Advanced features

---

## Risk Assessment

| Priority | Risk | Mitigation |
|----------|------|------------|
| 1 | Breaking existing signals | Feature flags, gradual rollout |
| 2 | Button breakage | Test thoroughly, keep fallback |
| 3 | Outcome loss | Backup before changes |
| 4-6 | Low | Incremental changes |
| 7-10 | Low | New features |
