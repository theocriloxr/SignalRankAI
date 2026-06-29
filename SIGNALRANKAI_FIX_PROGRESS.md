# SignalRankAI Fix Implementation Progress

## Priority 1: Critical Production Bugs ✅ COMPLETED

### 1.1 Signal Deduplication (db/pg_features.py)
- ✅ Simplified fingerprint to `asset|direction|timeframe|strategy_group`
- Removed: candle_timestamp, generated_at, created_at

### 1.2 Active Signal Protection (db/pg_features.py)  
- ✅ Added `check_active_signal_exists()` - checks Redis + DB for active signals
- ✅ Added `acquire_signal_lock(asset, direction, timeframe, 4h)` - Redis lock
- ✅ Added `release_signal_lock(asset, direction, timeframe)`

### 1.3 Telegram Delivery Cooldown (db/pg_features.py)
- ✅ Added tier-based cooldown Redis keys
- ✅ Key format: `delivery:{USER_ID}:{ASSET}:{DIRECTION}`
- ✅ TTL: VIP=4h, Premium=6h, Free=12h

---

## Priority 2: Buttons Not Working 🔲 PENDING

**Files**: signalrank_telegram/bot.py, signalrank_telegram/callback_handlers.py

**Issues**:
- Callback logic in multiple places
- Button pressed → Handler A → Handler B → Nothing
- Button registered → Wrong callback data → Ignored

**Plan**:
- [ ] Create unified `callback_router.py` 
- [ ] All buttons go through single `handle_callback()` function
- [ ] Add logging: `logger.info(f"Button pressed {callback.data}")`

---

## Priority 3: Outcome Tracking 🔲 PENDING

**Files**: 
- engine/realtime_outcome_tracker.py
- engine/shadow_outcome_worker.py  
- engine/core.py
- worker/worker.py
- db/models.py

**Issues**:
- Multiple trackers (A, B, engine) touch outcome state
- Creates race conditions

**Plan**:
- [ ] Choose RealtimeOutcomeTracker as sole owner
- [ ] Everything else read-only
- [ ] Add `signal_state` enum: ACTIVE, TP1_HIT, TP2_HIT, TP3_HIT, SL_HIT, EXPIRED, CANCELLED

---

## Priority 4: Freshness Bug 🔲 PENDING

**Files**: 
- engine/signal_formatter.py
- engine/freshness.py

**Issue**: Messages show "Freshness: Aging" but "Age: 0m" - Impossible

**Plan**:
- [ ] Use one source (either signal.created_at OR candle.timestamp, not both)

---

## Priority 5: Stale Signal Logic 🔲 PENDING

**File**: engine/stale_signal_validator.py

**Issue**: Logs show "Signal INVALIDATED" then "ACCEPTED" for same asset

**Plan**:
- [ ] Refactor `validate()` to return single result: VALID, INVALID, or ENTRY_ZONE_OVERRIDE

---

## Priority 6: Railway Stability 🔲 PENDING

**Files**: railway_main.py, worker/worker.py, db/session.py

**Plan**:
- [ ] Add Redis Health Monitor (PING every minute)
- [ ] Add PostgreSQL Health Monitor (SELECT 1 every minute)
- [ ] Create engine_health table tracking:
  - last_cycle
  - last_signal
  - last_outcome  
  - last_news_sync

---

## Priority 7: Database Indexes 🔲 PENDING

**Files**: db/models.py, alembic/*

**Plan**:
- [ ] Add indexes for Signals table: asset, status, created_at, signal_id
- [ ] Add indexes for Outcomes table: signal_id, status, closed_at
- [ ] Add indexes for Deliveries table: user_id, signal_id, asset

---

## Priority 8: Signal Lifecycle 🔲 PENDING

**Files**: engine/core.py, signalrank_telegram/bot.py

**Current**: NEW SIGNAL → NEW SIGNAL → NEW SIGNAL (multiple messages)

**Plan**:
- [ ] Implement single message thread with states:
  - NEW SIGNAL → UPDATED → TP1 HIT → TP2 HIT → CLOSED

---

## Priority 9: ML System 🔲 PENDING

**Files**: ml/*, engine/core.py

**Plan**:
- [ ] Add confidence calibration 
- [ ] Store: predicted_probability, actual_result
- [ ] Recalibrate monthly

---

## Priority 10: Enhanced Features 🔲 PENDING

### Trade Journal
- [ ] Per user: Win rate, Profit factor, Average RR, Monthly ROI

### Signal Replay  
- [ ] Show: Why was this signal generated?
- [ ] Display: EMA, RSI, OB, Volume, Confluence, ML Score

### Portfolio Exposure Engine
- [ ] Prevent: SOL BUY + ETH BUY + BTC BUY all at once (correlated assets)

### Market Regime Detection
- [ ] Detect modes: TRENDING, RANGING, VOLATILE, NEWS
- [ ] Strategies adapt automatically

### Institutional Scoring
- [ ] Add: Liquidity sweep, Fair Value Gap, Market Structure Shift, Order Block Strength, Volume Imbalance

---

## Implementation Notes

### New Functions Added to db/pg_features.py:
```python
# Fingerprint
compute_signal_fingerprint(signal) -> str

# Active signal protection  
check_active_signal_exists(session, asset, direction, timeframe) -> bool

# Redis locks
acquire_signal_lock(asset, direction, timeframe, ttl_seconds=14400) -> bool
release_signal_lock(asset, direction, timeframe) -> None

# Delivery cooldown
DELIVERY_COOLDOWN_TTL = {"vip": 14400, "premium": 21600, "free": 43200}
check_delivery_cooldown(user_id, asset, direction) -> bool
set_delivery_cooldown(user_id, asset, direction) -> None
```

### Usage:
```python
# Before generating signal:
from db.pg_features import acquire_signal_lock, check_active_signal_exists

locked = await acquire_signal_lock(asset, direction, timeframe)
if not locked:
    return  # Skip - another cycle is handling this

# Check if active signal exists
active_exists = await check_active_signal_exists(session, asset, direction, timeframe)
if active_exists:
    return  # Skip - don't create duplicate

# Before delivering signal:
from db.pg_features import check_delivery_cooldown, set_delivery_cooldown

in_cooldown = check_delivery_cooldown(user_id, asset, direction)
if in_cooldown:
    return  # Skip - user in cooldown

# After successful delivery:
set_delivery_cooldown(user_id, asset, direction)
```

---

## Database Migration Needed

Run this SQL to add the uniqueness constraint:

```sql
-- Create partial unique index for active signals
CREATE UNIQUE INDEX idx_signal_active_unique 
ON signals (asset, direction, timeframe, status) 
WHERE expired = FALSE AND archived = FALSE;
