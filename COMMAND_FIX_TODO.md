# SignalRank AI Command Surface Fix Implementation TODO

## Overview
Fix the large command surface issues identified:
- Commands registered but returning no data ("No active unresolved signals")
- Missing startup command audit
- No delivery telemetry
- AUDUSD pricing bug

## Root Cause Analysis - COMPLETED

### 1. /signals "No active unresolved signals" Bug ✅ FIXED
**Root Cause:** The query in `signal_commands.py` used `SignalDelivery.sent_ok.is_(True)` which filters
to only signals where delivery SUCCEEDED. Signals can exist in DB without successful delivery.

**Location:** `signalrank_telegram/signal_commands.py` - `signals_command()` function
- Bug location: `.where(SignalDelivery.sent_ok.is_(True))`
- **FIX APPLIED:** Removed the sent_ok filter to show ALL delivered signals

**Evidence from code:**
```python
# OLD (buggy) - filters by sent_ok
.where(SignalDelivery.user_id == user_row.id,
       SignalDelivery.sent_ok.is_(True),  # <-- REMOVED
       SignalDelivery.delivered_at >= cutoff)

# NEW (fixed) - show all delivered signals
.where(SignalDelivery.user_id == user_row.id,
       SignalDelivery.delivered_at >= cutoff)  # No sent_ok filter
```

### 2. Database Function Also Fixed ✅
**Location:** `db/pg_features.py` - `list_unresolved_signals_for_user()` function
- **FIX APPLIED:** Removed sent_ok filter in this fallback function too

### 3. Duplicate Telegram Stacks ❌ FALSE ALARM
- `signalrank_telegram/` = Main implementation (ACTIVE)
- `telegram/` = Legacy stub - already disabled via ALLOW_LEGACY_TELEGRAM_BOT
- No action needed

### 4. Startup Command Audit ✅ ALREADY EXISTS
- Located in `bot.py` - runs in `run_bot()` after handler registration
- Logs: `[bot] command registry mismatch: missing=...`
- Logs: Missing handlers at startup
- Already adequate

## Implementation Progress

### Phase 1: Signal Status Fix ✅ COMPLETED
- [x] Fix /signals command to remove sent_ok filter
- [x] Fix fallback function list_unresolved_signals_for_user()
- [x] Test with users who have signals but see "no signals"

### Phase 2: Startup Command Audit ✅ READY
- [x] Already exists in bot.py
- [x] Logs missing handlers at startup

### Phase 3: /diag Command 📋 NOT STARTED
- [ ] Add /diag command for health verification
- [ ] Include command registration status
- [ ] Include subsystem health checks

### Phase 4: Delivery Telemetry 📋 NOT STARTED
- [ ] Track delivery stages: GENERATED → STORED → QUEUED → TELEGRAM_SENT → DELIVERED
- [ ] Log where signals die in the pipeline

### Phase 5: Price Validation (AUDUSD Bug) 📋 NOT STARTED
- [ ] Add AUDUSD sanity check (0.60-0.85 range)
- [ ] Apply to validate_price_sanity() in engine/validators.py

### Phase 6: Threshold Persistence 📋 NOT STARTED
- [ ] Save dynamic thresholds to DB/Redis instead of recalculating each cycle

## Command Audit Status
- Expected commands: ~85+ (from COMMAND_TIERS)
- Help entries: Multiple per tier
- Registration: Happens in bot.py run_bot()

## Files Modified
1. signalrank_telegram/signal_commands.py - FIXED sent_ok filter
2. db/pg_features.py - FIXED list_unresolved_signals_for_user
3. signalrank_telegram/command_access.py - Already has COMMAND_TIERS
4. signalrank_telegram/bot.py - Has startup audit

## Next Steps
1. ✅ Core fix completed - /signals should now show signals
2. Consider adding /diag command
3. Consider adding price validation
4. Consider adding delivery telemetry

## Summary of Changes Made
```
1. signalrank_telegram/signal_commands.py:
   - REMOVED: SignalDelivery.sent_ok.is_(True) filter
   - Added clear comments explaining the fix
   - Now shows ALL delivered signals regardless of delivery success

2. db/pg_features.py - list_unresolved_signals_for_user():
   - REMOVED: SignalDelivery.sent_ok.is_(True) filter
   - Added documentation explaining the fix
   - Now shows ALL signals, not just successfully delivered ones
