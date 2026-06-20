# SignalRankAI Comprehensive Bug Fix Implementation Plan

## Priority 1: Critical Production Bugs (FIX FIRST)

### 1.1 Signal Deduplication (CRITICAL)
**Files**: `db/pg_features.py`, `engine/signal_deduplicator.py`

**Current Problem**: Fingerprint is too granular causing duplicate signals

**Fix**:
- [ ] Simplify fingerprint to: `asset, direction, timeframe, strategy_group` (REMOVE: entry, stop_loss, take_profit)
- [ ] Add Redis lock: `signal_lock:{ASSET}:{DIRECTION}:{TIMEFRAME}` with 4h TTL
- [ ] Add PostgreSQL unique constraint on (asset, direction, timeframe, status='active')

**Implementation**:
```python
# New simplified fingerprint
def compute_signal_fingerprint(signal: Dict[str, Any]) -> str:
    asset = str(signal.get("asset")).upper()
    direction = str(signal.get("direction")).lower()
    timeframe = str(signal.get("timeframe")).lower()
    strategy_group = str(signal.get("strategy_group")).lower()
    raw = f"{asset}|{direction}|{timeframe}|{strategy_group}"
    return hashlib.sha256(raw.encode()).hexdigest()[:64]
```

### 1.2 Active Signal Protection
**Files**: `engine/core.py`, `db/pg_features.py`

**Current Problem**: Can create multiple signals for same asset/timeframe

**Fix**:
- [ ] Add `active_signal_exists(asset, direction, timeframe)` check before signal creation
- [ ] If exists with status='active', skip generation
- [ ] Add Redis lock: `signal_active:{ASSET}:{DIRECTION}:{TIMEFRAME}`

### 1.3 Telegram Delivery Cooldown
**Files**: `signalrank_telegram/bot.py`, `signalrank_telegram/delivery.py`

**Current Problem**: Same signal sent repeatedly to user

**Fix**:
- [ ] Add Redis key: `delivery:{USER_ID}:{ASSET}:{DIRECTION}`
- [ ] TTL by tier: VIP=4h, Premium=6h, Free=12h
- [ ] Check before sending: if redis.exists(), skip

---

## Priority 2: Buttons Not Working

### 2.1 Consolidate Callback Handlers
**Files**: `signalrank_telegram/bot.py`, `signalrank_telegram/callback_handlers.py`

**Current Problem**: Callbacks in multiple places - wrong handler executes

**Fix**:
- [ ] Create single `callback_router.py` with `handle_callback(update, context)`
- [ ] Add logging: `logger.info(f"Button pressed {callback.data}")`
- [ ] Remove duplicate handlers from bot.py
- [ ] Route all callbacks through central handler

---

## Priority 3: Outcome Tracking

### 3.1 Unify Outcome Ownership
**Files**: `engine/realtime_outcome_tracker.py`, `worker/`

**Current Problem**: Multiple trackers creating race conditions

**Fix**:
- [ ] Designate `RealtimeOutcomeTracker` as SOLE owner
- [ ] All other code: read-only access
- [ ] Add signal_state enum: ACTIVE, TP1_HIT, TP2_HIT, TP3_HIT, SL_HIT, EXPIRED, CANCELLED

---

## Priority 4: Freshness Bug

### 4.1 Fix Freshness Calculation
**Files**: `engine/signal_formatter.py`, `engine/freshness.py`

**Current Problem**: Shows "Freshness: Aging, Age: 0m" (impossible)

**Fix**:
- [ ] Use single source for both freshness and age
- [ ] If using signal.created_at, keep consistent
- [ ] If using candle.timestamp, keep consistent

---

## Priority 5: Stale Signal Logic

### 5.1 Refactor Stale Signal Validator
**Files**: `engine/stale_signal_validator.py`

**Current Problem**: Contradictory logic - signals invalidated then accepted

**Fix**:
- [ ] Refactor validate() to return single result: VALID, INVALID, or ENTRY_ZONE_OVERRIDE
- [ ] Remove contradictory checks
- [ ] Add clear logging

---

## Priority 6: Railway Stability

### 6.1 Health Monitors
**Files**: `railway_main.py`, `worker/worker.py`

**Fix**:
- [ ] Add Redis Health Monitor: PING every minute
- [ ] Add PostgreSQL Health Monitor: SELECT 1 every minute
- [ ] Add Engine Health Table: last_cycle, last_signal, last_outcome, last_news_sync

---

## Priority 7: Database

### 7.1 Add Indexes
**Files**: `db/models.py`, `alembic/*`

**Fix**:
- [ ] Signals: (asset, status, created_at, signal_id)
- [ ] Outcomes: (signal_id, status, closed_at)
- [ ] Deliveries: (user_id, signal_id, asset)

---

## Priority 8: Signal Lifecycle

### 8.1 Single Message Thread
**Files**: `engine/core.py`, `signalrank_telegram/bot.py`

**Current Problem**: Multiple NEW SIGNAL messages

**Fix**:
- [ ] Use lifecycle: NEW → UPDATED → TP1 HIT → TP2 HIT → CLOSED
- [ ] Edit existing message instead of sending new

---

## Priority 9: ML System

### 9.1 Confidence Calibration
**Files**: `ml/*`, `engine/core.py`

**Fix**:
- [ ] Store: predicted_probability, actual_result
- [ ] Recalibrate monthly
- [ ] Track drift over time

---

## Priority 10: Enhanced Features

### 10.1 Trade Journal
**Implementation**: Per user stats - win rate, profit factor, avg RR, monthly ROI

### 10.2 Signal Replay
**Implementation**: Show EMA, RSI, OB, Volume, Confluence, ML Score

### 10.3 Portfolio Exposure Engine
**Implementation**: Prevent correlated asset overexposure

### 10.4 Market Regime Detection
**Implementation**: Auto-adapt strategies to TRENDING/RANGING/VOLATILE/NEWS

### 10.5 Institutional Scoring
**Implementation**: Add Liquidity sweep, Fair Value Gap, Order Block Strength

---

## Implementation Order

1. **Week 1**: Fix Priority 1 (Signal Deduplication, Active Signal, Delivery Cooldown)
2. **Week 2**: Fix Priority 2 (Buttons), Priority 3 (Outcome Tracking)
3. **Week 3**: Fix Priority 4-7 (Freshness, Stale, Railway, Database)
4. **Week 4**: Fix Priority 8-10 (Lifecycle, ML, Enhanced Features)

---

## Key Files to Edit

| File | Priority | Changes |
|------|---------|--------|
| db/pg_features.py | 1, 3 | Simplify fingerprint, add Redis lock |
| engine/signal_deduplicator.py | 1 | Add Redis dedup lock |
| engine/core.py | 1, 2, 3 | Active signal check, callback routing |
| signalrank_telegram/bot.py | 1, 2 | Delivery cooldown, callback consolidation |
| signalrank_telegram/callback_handlers.py | 2 | Single callback router |
| engine/realtime_outcome_tracker.py | 3 | Unify ownership |
| engine/stale_signal_validator.py | 5 | Refactor validate() |
| db/models.py | 7 | Add indexes |
| ml/*.py | 9 | Confidence calibration |
