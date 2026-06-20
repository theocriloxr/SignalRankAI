# SignalRankAI Fix Implementation TODO

## Progress: Priority 1 is DONE ✅

### PRIORITY 1: CRITICAL PRODUCTION BUGS - COMPLETE ✓
- [x] 1.1 Signal Deduplication - Fixed fingerprint in db/pg_features.py
- [x] 1.2 Active Signal Protection - Added active_trade check in core.py  
- [x] 1.3 Telegram Delivery Cooldown - Added _is_asset_delivery_locked() in bot.py

### PRIORITY 2: BUTTONS NOT WORKING
- [~] 2.1 Consolidate callback handlers
  - callback_handlers.py has global handler - GOOD ✓
  - bot.py still has inline handlers - CONFLICT
  - Need: Remove duplicate handlers from bot.py OR verify routing works

- [ ] 2.2 Add button press logging to all handlers

### PRIORITY 3: OUTCOME TRACKING  
- [ ] 3.1 Unify outcome ownership to RealtimeOutcomeTracker
- [ ] 3.2 Add signal_state enum

### PRIORITY 4: FRESHNESS BUG
- [ ] 4.1 Fix signal.created_at vs candle.timestamp conflict

### PRIORITY 5: STALE SIGNAL LOGIC
- [ ] 5.1 Refactor validate() to single result

### PRIORITY 6: RAILWAY STABILITY
- [ ] 6.1 Redis health monitor (PING every minute)
- [ ] 6.2 PostgreSQL health monitor (SELECT 1 every minute)
- [ ] 6.3 Engine heartbeat table

### PRIORITY 7: DATABASE INDEXES
- [ ] 7.1 Add indexes to Signals, Outcomes, Deliveries tables

### PRIORITY 8: SIGNAL LIFECYCLE
- [ ] 8.1 Implement message thread updates (NEW → UPDATED → TP1 → TP2 → CLOSED)

### PRIORITY 9: ML SYSTEM  
- [ ] 9.1 Add confidence calibration tracking

### PRIORITY 10: ADVANCED FEATURES
- [ ] 10.1 Trade Journal
- [ ] 10.2 Portfolio Exposure Engine
- [ ] 10.3 Market Regime Detection
- [ ] 10.4 Institutional Scoring

---

## Next Steps:

1. First verify the callback consolidation is working - check bot.py has callback_handlers.py imported and added
2. Add logging to all callback handlers  
3. Address outcome ownership in realtime_outcome_tracker.py
4. Continue with Priorities 4-10
