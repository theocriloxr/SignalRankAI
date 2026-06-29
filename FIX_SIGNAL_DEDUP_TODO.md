# SignalRankAI Signal Deduplication & Callback Fix Implementation

## Progress Tracking

- [x] 1. Remove candle_timestamp from fingerprint (CRITICAL)
- [ ] 2. Add Redis dedup lock layer
- [ ] 3. Consolidate callback handlers
- [ ] 4. Fix check_outcome callback
- [ ] 5. Fix MT5 placeholder
- [ ] 6. Unify outcome tracking
- [ ] 7. Add tier-based delivery cooldowns
- [ ] 8. Add material change override

## Implementation Notes

### FIX 1: Remove candle_timestamp from fingerprint (db/pg_features.py)
The fingerprint should NOT include candle_timestamp because it makes the same 
trade idea (same asset, direction, entry, SL, TP, strategy) appear as different 
signals when regenerated on a different candle.

FIXED in compute_signal_fingerprint() - removed candle_timestamp from raw string.

### FIX 2: Redis Dedup Lock
Added Redis-backed dedup lock to prevent same signal generation within timeframe window.

### FIX 3-5: Callback Consolidation  
Global callback router in callback_handlers.py handles all callbacks. Per-button handlers 
in bot.py should be removed or consolidated.

### FIX 6: Check Outcome
Query the canonical Outcome table and show clear status.

### FIX 7: MT5 Button
Currently a placeholder - either implement or hide.

### FIX 8: Outcome Tracking
One canonical writer - worker tracker should own outcomes.
