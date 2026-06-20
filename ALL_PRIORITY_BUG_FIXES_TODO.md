# SignalRankAI All Priority Bug Fixes Implementation

## Progress Tracking

- [x] 1.1 Remove candle_timestamp from fingerprint (CRITICAL) ✅
- [x] 1.2 Add Redis dedup lock layer (Partial - already in signal_deduplicator.py)
- [ ] 1.3 Integrate delivery cooldown into bot.py
- [ ] 1.4 Add PostgreSQL uniqueness check
- [x] 2.1 Unify callback handlers ✅
- [x] 3.1 RealtimeOutcomeTracker as sole owner ✅
- [ ] 4.1 Fix freshness bug (single timestamp source)
- [ ] 5.1 Refactor stale signal validator
- [ ] 6.1 Add health monitors (Redis/PostgreSQL)
- [ ] 7.1 Add database indexes
- [ ] 8.1 Signal lifecycle updates
- [ ] 9.1 ML confidence calibration

## Implementation Status

### Priority 1: Critical Production Bugs (In Progress)
1. Signal Deduplication - PARTIALLY DONE (needs Postgres uniqueness)
2. Active Signal Protection - INTEGRATED in engine/core.py
3. Telegram Delivery Cooldown - NEEDS INTEGRATION into bot.py

### Priority 2: Buttons Not Working ✅
- Global callback router implemented in callback_handlers.py
- All buttons go through handle_callback() with logging

### Priority 3: Outcome Tracking ✅
- RealtimeOutcomeTracker is sole owner
- Engine is read-only

### Priority 4: Freshness Bug (Pending)
- Needs single timestamp source

### Priority 5: Stale Signal Logic (Pending)
- Refactor validate() to return single result

### Priority 6: Railway Stability (Pending)
- Add health monitors

### Priority 7: Database (In Progress)
- Add indexes to signals table

### Priority 8: Signal Lifecycle (Pending)
- Single message thread updates

### Priority 9: ML System (Pending)
- Add confidence calibration

### Priority 10: Features (Future)
- Trade Journal
- Portfolio Exposure Engine
- Market Regime Detection
- Institutional Scoring
