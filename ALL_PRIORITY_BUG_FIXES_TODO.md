# SignalRankAI All Priority Bug Fixes Implementation

## Priority 1: Critical Production Bugs (IN PROGRESS)

### 1.1 Signal Deduplication ✅ STARTED
- [x] Remove candle_timestamp from fingerprint (db/pg_features.py)
- [x] Remove generated_at, created_at from fingerprint
- [ ] Add Redis dedup lock layer (signal_lock:SOLUSDT:BUY:4H, 4h TTL)
- [ ] Add PostgreSQL uniqueness constraint

### 1.2 Active Signal Protection
- [ ] Check active signal exists before creating new signal
- [ ] Check (asset, direction, timeframe, status='active')

### 1.3 Telegram Delivery Cooldown
- [ ] Add Redis key: delivery:user_id:ASSET:DIRECTION
- [ ] TTL by tier: VIP=4h, Premium=6h, Free=12h

## Priority 2: Buttons Not Working ✅ PARTIALLY DONE
- [x] Global callback router in callback_handlers.py
- [ ] Add logging for button presses

## Priority 3: Outcome Tracking ✅ DONE
- [x] RealtimeOutcomeTracker is sole owner
- [x] engine/core.py and worker.py read-only

## Priority 4: Freshness Bug
- [ ] Unify signal.created_at vs candle.timestamp source

## Priority 5: Stale Signal Logic ✅ PARTIALLY DONE
- [x] stale_signal_validator.py exists
- [ ] Refactor validate() to return single result

## Priority 6: Railway Stability
- [ ] Redis health monitor (PING every minute)
- [ ] PostgreSQL health monitor (SELECT 1)
- [ ] Engine heartbeat table

## Priority 7: Database Indexes
- [ ] Add indexes to signals table
- [ ] Add indexes to outcomes table
- [ ] Add indexes to deliveries table

## Priority 8: Signal Lifecycle
- [ ] Update NEW SIGNAL → UPDATED → TP1 HIT flow

## Priority 9: ML System
- [ ] Confidence calibration
- [ ] Store predicted_probability and actual_result

## Priority 10: Advanced Features
- [ ] Trade Journal
- [ ] Portfolio Exposure Engine
- [ ] Market Regime Detection
- [ ] Institutional Scoring
