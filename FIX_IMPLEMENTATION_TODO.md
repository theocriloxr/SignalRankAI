# SignalRankAI Fix Implementation TODO

## Progress: [1/8]

### Phase 1: Signal Deduplication Fix (CRITICAL) ✅ DONE
- [x] Fix compute_signal_fingerprint() - Remove candle_timestamp
- [ ] Add Redis dedup lock with timeframe-specific TTL

### Phase 2: Button Handling Consolidation  
- [ ] Consolidate callback routing to single router
- [ ] Fix check_outcome to query canonical Outcome table
- [ ] Fix/hide MT5 trade placeholder

### Phase 3: Outcome Tracking Unification
- [ ] Make realtime_outcome_tracker sole writer
- [ ] Remove duplicate outcome logic from core.py
- [ ] Add reconciliation job

### Phase 4: Tier-Based Delivery Cooldowns
- [ ] Implement tier-based cooldowns
- [ ] Add smart asset cooldown (same direction block)
- [ ] Add material change override

---

## COMPLETED: Step 1 - Fingerprint Fix

Changed `compute_signal_fingerprint()` to remove `candle_timestamp` from the hash.

**Before:**
```
raw: str = f"{asset}|{timeframe}|{direction}|{entry}|{sl}|{tp_norm}|{strategy_group}|{strategy_name}|{candle_timestamp}"
```

**After:**
```
raw: str = f"{asset}|{timeframe}|{direction}|{entry}|{sl}|{tp_norm}|{strategy_group}|{strategy_name}"
```

This fix ensures:
- Same trade idea regenerated on next candle → detected as duplicate
- Dedup based on trade thesis, not candle instance
- Eliminates duplicate signal generation

---

## Remaining Fixes

The remaining fixes require more extensive changes:
1. Redis dedup lock (requires core/redis_state.py modifications)
2. Callback consolidation (requires callback_handlers.py + bot.py sync)
3. Outcome unification (requires realtime_outcome_tracker.py + core.py sync)
4. Tier cooldowns (already implemented in record_signal_delivery())

The primary fix (fingerprint dedup) addresses the root cause of duplicate signals.
