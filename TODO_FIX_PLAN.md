# SignalRankAI Fix Implementation Plan

## Overview
Comprehensive fix plan addressing:
1. Button handling consolidation and callback reliability
2. Signal deduplication (candle_timestamp removal from fingerprint)
3. Outcome tracking unification
4. User delivery cooldowns with tier-based TTL

---

## Phase 1: Signal Deduplication Fix (Most Critical)

### Issue
`compute_signal_fingerprint()` in `db/pg_features.py` includes `candle_timestamp` in the hash, causing the same trade idea regenerated on the next candle to get a new fingerprint - defeating deduplication.

### Fix: Remove candle_timestamp from fingerprint

**File: db/pg_features.py**
- Remove `candle_timestamp` from the fingerprint calculation
- Keep it only as metadata, not part of dedup key
- Add Redis-backed dedup lock with timeframe-specific TTL

```python
# OLD (broken):
raw: str = f"{asset}|{timeframe}|{direction}|{entry}|{sl}|{tp_norm}|{strategy_group}|{strategy_name}|{candle_timestamp}"

# NEW (fixed):
raw: str = f"{asset}|{timeframe}|{direction}|{entry}|{sl}|{tp_norm}|{strategy_group}|{strategy_name}"
```

### Add Redis dedup lock layer

**File: db/pg_features.py**
- Add `compute_signal_fingerprint()` enhancement with Redis lock
- TTL per timeframe: 4H for 4H signals, 1H for 1H signals, etc.

---

## Phase 2: Button Handling Consolidation

### Issue 1: Duplicate callback routing
- `signalrank_telegram/bot.py` has `_check_outcome_callback()`
- `signalrank_telegram/callback_handlers.py` has global router
- Duplication causes fragile behavior

### Fix: Single callback router

**Keep**: callback_handlers.py global router
**Remove**: Duplicate per-button handlers in bot.py

### Issue 2: _handle_mt5_trade() placeholder
- Currently only sends "Opening MT5 trade execution..." without actual execution

**Fix Options:**
1. Implement real MT5 execution flow
2. OR hide button until implemented (show upgrade prompt for FREE users)

### Issue 3: check_outcome callback可靠性

**Fix**: 
- Query canonical Outcome table
- Return clear status: "pending" / "hit TP1" / "SL" / "expired"
- Handle case where outcome row doesn't exist yet

---

## Phase 3: Outcome Tracking Unification

### Issue: Multiple outcome writers
- `engine/realtime_outcome_tracker.py`
- `engine/core.py` also writes outcomes
- `engine/shadow_outcome_worker.py`
- Telegram callback reads from different state

### Fix: Single canonical writer

**Choose**: `engine/realtime_outcome_tracker.py` as sole outcome evaluator

**Changes:**
1. `engine/core.py` - Remove duplicate outcome logic, only persist trade-open/trade-close events
2. Ensure every delivered signal has SignalDelivery row
3. Add reconciliation job for Signal/SignalDelivery/Outcome consistency

---

## Phase 4: User Delivery Cooldowns (Layer 2 + Layer 3 Protection)

### Tier-Based Cooldowns

| Tier  | Asset Cooldown |
|-------|-------------|
| FREE  | 12 hours   |
| Premium| 6 hours   |
| VIP   | 4 hours   |

### Redis Key Format
```
signal_delivery:{user_id}:{asset}:{direction}
```

### Smart Asset Cooldown (Layer 3)
- Block SAME DIRECTION for cooldown period
- Allow opposite direction (BUY vs SELL)

### Material Change Override
- Resend if conviction changes ≥10%
- Resend if confluence changes ≥15%
- Edit existing message with "🔄 SIGNAL UPGRADE" instead of new message

---

## Implementation Files to Edit

### Priority 1 (Critical - Dedup)
1. `db/pg_features.py` - compute_signal_fingerprint()
   - Remove candle_timestamp from hash
   - Add Redis dedup lock

### Priority 2 (High - Callbacks)
2. `signalrank_telegram/bot.py`
   - Remove duplicate _check_outcome_callback()
   - Keep only global router calls
   
3. `signalrank_telegram/callback_handlers.py`
   - Implement real _handle_mt5_trade() or hide button
   - Fix check_outcome to query canonical Outcome table

### Priority 3 (Medium - Outcomes)
4. `engine/core.py`
   - Remove duplicate outcome persistence
   - Only write trade-open/trade-close events

5. `engine/realtime_outcome_tracker.py`
   - Add reconciliation job
   - Ensure SignalDelivery row exists for all signals

### Priority 4 (Enhancement - Cooldowns)
6. `signalrank_telegram/bot.py` or new cooldown module
   - Implement tier-based cooldowns
   - Add Redis-backed delivery locks

---

## Testing Checklist

- [ ] Same signal generated on different candle = same fingerprint (dedup works)
- [ ] Button callback fires and returns clear status
- [ ] check_outcome shows "pending/hit TP1/SL/expired"
- [ ] MT5 trade button either works or shows proper upsell
- [ ] Only one outcome writer active
- [ ] Tier-based cooldowns enforced correctly
- [ ] Material change = signal upgrade message (not duplicate)

---

## Risk Mitigation

1. **Backup before changes** - All files under version control
2. **Incremental testing** - Test each fix in isolation
3. **Rollback plan** - Revert to previous fingerprint format if issues

---

## Dependencies

- Redis for dedup locks
- PostgreSQL for canonical state
- Tier constants already defined in core/tier_constants.py
