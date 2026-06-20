# SignalRankAI All Priority Bug Fixes Implementation

## Progress Tracking - All 10 Priorities

### ✅ Priority 1: Critical Production Bugs - COMPLETE
- [x] 1.1 Signal Deduplication - Fix fingerprint & add Redis lock
- [x] 1.2 Active Signal Protection - Check before signal creation  
- [x] 1.3 Telegram Delivery Cooldown - Per-user tier-based cooldowns

### 🔄 Priority 2: Buttons Not Working - IN PROGRESS
- [ ] 2.1 Consolidate callback handlers (verify single router)

### 🔄 Priority 3: Outcome Tracking - IN PROGRESS
- [ ] 3.1 Unify outcome ownership to RealtimeOutcomeTracker

### ⏳ Priority 4: Freshness Bug
- [ ] 4.1 Unify signal timestamp source

### ⏳ Priority 5: Stale Signal Logic  
- [ ] 5.1 Refactor validate() return to single result

### ⏳ Priority 6: Railway Stability
- [ ] 6.1 Add Redis health monitor (PING every minute)
- [ ] 6.2 Add PostgreSQL health monitor (SELECT 1 every minute)
- [ ] 6.3 Add engine_health heartbeat table

### ⏳ Priority 7: Database
- [ ] 7.1 Add indexes to signals table
- [ ] 7.2 Add indexes to outcomes table
- [ ] 7.3 Add indexes to deliveries table

### ⏳ Priority 8: Signal Lifecycle
- [ ] 8.1 Implement message threading (NEW → UPDATED → TP1 → TP2 → CLOSED)

### ⏳ Priority 9: ML System
- [ ] 9.1 Add confidence calibration storage
- [ ] 9.2 Monthly recalibration

### ⏳ Priority 10: Features That Would Put SignalRankAI Above Most
- [ ] 10.1 Trade Journal
- [ ] 10.2 Signal Replay
- [ ] 10.3 Portfolio Exposure Engine
- [ ] 10.4 Market Regime Detection
- [ ] 10.5 Institutional Scoring

## Implementation Notes

### Priority 1.1: Signal Fingerprint ✅ COMPLETE
- ✅ candle_timestamp already removed from fingerprint in db/pg_features.py
- ✅ Redis lock: signal_lock:{ASSET}:{DIRECTION}:{TIMEFRAME} TTL 4 hours exists in engine/signal_lock.py
- ✅ PostgreSQL uniqueness check implemented in get_or_create_signal()

### Priority 1.2: Active Signal Protection ✅ COMPLETE
- ✅ Function active_signal_exists() in db/pg_features.py
- ✅ Check before creating signal via _active_trade_has_asset()

### Priority 1.3: Telegram Delivery Cooldown ✅ COMPLETE
- ✅ Redis keys in db/pg_features.py: check_delivery_cooldown(), set_delivery_cooldown()
- ✅ TTL by tier: VIP=4h, Premium=6h, Free=12h already defined

### Priority 2: Buttons
- Global callback handler exists in signalrank_telegram/bot.py
- Need to verify handlers are properly wired

### Priority 3: Outcome Tracking
- RealtimeOutcomeTracker is already the canonical owner
- Need to ensure no other component writes outcomes

### Priority 4: Freshness Bug
- Need to determine which timestamp source to use consistently
- Likely use signal.created_at (not candle.timestamp)

### Priority 5: Stale Signal Logic  
- Already implemented in engine/stale_signal_validator.py
- Returns VALID/INVALID/ENTRY_ZONE_OVERRIDE

### Priority 6: Railway Stability
- Need health monitors for Redis, PostgreSQL
- Need engine_health table for tracking

### Priority 7: Database Indexes
- signals: asset, status, created_at, signal_id
- outcomes: signal_id, status, closed_at  
- deliveries: user_id, signal_id, asset

### Priority 8: Signal Lifecycle
- Need to implement message thread updates
- NEW → UPDATED → TP1 HIT → TP2 HIT → CLOSED

### Priority 9: ML System
- Need to store predicted_probability vs actual_result
- Monthly recalibration

### Priority 10: Enhancements
- Trade journal, replay, portfolio exposure, regime detection, institutional scoring
