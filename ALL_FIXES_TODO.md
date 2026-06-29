# SignalRankAI All Bug Fixes - Implementation Tracking

## Progress: Priority 1 Critical Bugs (These are causing real failures)

### 1.1 Signal Deduplication - Fingerprint ✅ (Already Fixed)
- Files: db/pg_features.py, engine/signal_deduplicator.py
- Status: FIXED - candle_timestamp removed from fingerprint
- Fingerprint now: asset, direction, timeframe, entry, sl, tp, strategy_group, strategy_name

### 1.2 Redis Lock ✅ (Already Implemented)
- Files: engine/signal_lock.py
- Format: signal_lock:ASSET:DIRECTION:TIMEFRAME
- TTL: 4 hours for 4H, 1.5h for 1h, etc.

### 1.3 PostgreSQL Uniqueness Check
- Files: db/pg_features.py, alembic migrations
- Add UNIQUE(asset, direction, timeframe, status='active') constraint to signals table
- Status: ❌ NOT DONE - NEEDED

### 1.4 Active Signal Protection
- Files: engine/core.py
- Before creating signal - check active_signal_exists(asset, direction, timeframe)
- If active exists: skip generation
- Status: ⚠️ PARTIALLY DONE - signal_lock.py has check_active_signal_exists, needs integration

### 1.5 Telegram Delivery Cooldown
- Files: signalrank_telegram/bot.py
- Redis key: delivery:user_id:ASSET:DIRECTION
- TTL by tier: VIP=4h, Premium=6h, Free=12h
- Status: ⚠️ PARTIALLY DONE - signal_lock.py has functions, needs integration into bot.py

## Priority 2: Buttons Not Working ✅ (Already Fixed in callback_handlers.py)
- Global callback_handler exists
- Calls query.answer() immediately
- Single point of routing
- Status: ✅ FIXED

## Priority 3: Outcome Tracking ✅ (Already Implemented)
- Files: engine/realtime_outcome_tracker.py
- RealtimeOutcomeTracker as sole owner
- Status: ✅ IMPLEMENTED

## Priority 4: Freshness Bug
- Files: engine/signal_formatter.py, engine/freshness.py
- Issue: Freshness shows "Aging" but Age=0m (impossible)
- Likely uses signal.created_at vs candle_timestamp mismatch
- Status: ❌ NOT FIXED - NEEDS INVESTIGATION

## Priority 5: Stale Signal Logic
- Files: engine/stale_signal_validator.py
- Issue: Logs show "INVALIDATED" then "ACCEPTED" for same asset
- Needs: Single validate() returns VALID/INVALID/ENTRY_ZONE_OVERRIDE
- Status: ❌ NOT FIXED - NEEDS REFACTOR

## Priority 6: Railway Stability
- Files: railway_main.py, worker/worker.py, db/session.py
- Needs:
  - Redis Health Monitor: PING every minute
  - PostgreSQL Health Monitor: SELECT 1 every minute
  - Engine Health Table: last_cycle, last_signal, last_outcome, last_news_sync
- Status: ❌ NOT IMPLEMENTED

## Priority 7: Database Indexes
- Files: db/models.py, alembic/versions/
- Add indexes:
  - Signals: asset, status, created_at, signal_id
  - Outcomes: signal_id, status, closed_at
  - Deliveries: user_id, signal_id, asset
- Status: ❌ NOT IMPLEMENTED

## Priority 8: Signal Lifecycle Updates
- Files: engine/core.py, signalrank_telegram/bot.py
- Instead of NEW SIGNAL x4, use thread updates:
  - NEW SIGNAL → UPDATED → TP1 HIT → TP2 HIT → CLOSED
- Status: ❌ NOT IMPLEMENTED

## Priority 9: ML Confidence Calibration
- Files: ml/ , engine/core.py
- Store: predicted_probability + actual_result
- Recalibrate monthly
- Status: ❌ NOT IMPLEMENTED

## Priority 10: Features That Would Put Above Most Bots

### 10.1 Trade Journal
- Per user: Win rate, Profit factor, Average RR, Monthly ROI
- Status: ❌ NOT IMPLEMENTED

### 10.2 Signal Replay
- Show: Why signal was generated (EMA, RSI, OB, Volume, Confluence, ML Score)
- Status: ❌ NOT IMPLEMENTED

### 10.3 Portfolio Exposure Engine
- Prevent correlated exposure (SOL BUY + ETH BUY + BTC BUY all at once)
- Status: ⚠️ PARTIALLY DONE in engine/correlation_filter.py

### 10.4 Market Regime Detection
- Modes: TRENDING, RANGING, VOLATILE, NEWS
- Strategies adapt automatically
- Status: ❌ NOT IMPLEMENTED

### 10.5 Institutional Scoring
- Add: Liquidity sweep, Fair Value Gap, Market Structure Shift, Order Block Strength, Volume Imbalance
- Status: ❌ NOT IMPLEMENTED

## Implementation Priority Order

### Phase 1: Critical Production Bugs (NOW)
- [x] 1.1 Fingerprint fix
- [x] 1.2 Redis lock
- [ ] 1.3 PostgreSQL uniqueness constraint
- [ ] 1.4 Active signal check integration in core.py
- [ ] 1.5 Delivery cooldown integration in bot.py

### Phase 2: High Priority Bugs
- [x] 2.1 Callback handler consolidation
- [x] 2.2 Outcome tracking

### Phase 3: Need Investigation
- [ ] 4.1 Freshness bug - investigate signal.created_at vs candle.timestamp
- [ ] 5.1 Stale signal validator refactor

### Phase 4: Infrastructure
- [ ] 6.1 Railway health monitors
- [ ] 7.1 Database indexes
- [ ] 8.1 Signal lifecycle updates

### Phase 5: ML & Features
- [ ] 9.1 ML confidence calibration
- [ ] 10.1-10.5 Enhancements

## Quick Wins Implementation Steps

# Step 1: Add PostgreSQL uniqueness constraint (TODO: db migrations)
# Step 2: Integrate signal_lock in engine/core.py before signal creation
# Step 3: Integrate delivery cooldown in bot.py before send
# Step 4: Debug freshness issue - unified timestamp source
# Step 5: Refactor stale_signal_validator.py for single result
# Step 6: Add health monitors for Railway stability
# Step 7: Add database indexes
# Step 8: Implement signal lifecycle updates
# Step 9: ML confidence calibration
# Step 10: Trade journal and replay
