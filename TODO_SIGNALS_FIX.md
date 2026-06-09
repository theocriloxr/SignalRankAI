# TODO: Fix /signals Command Issues

## Issues Identified:

1. **Sent Flag Mismatch**: `/signals` queries only `sent_ok=True` signals
2. **Invalidation Filter**: Signals marked "invalidated" (SL hit before entry) don't show
3. **No Status Display**: No way to see why a signal isn't active
4. **Resend Job Delivery Tracking**: May not properly update sent_ok flag

## Plan:

### 1. FIX: Broaden /signals query (signal_commands.py)
   - Change query to show signals from last 48 hours regardless of sent status
   - Include signals that are invalidated/missed but recently generated
   - Add status column to display why signals aren't active

### 2. FIX: Add status info to signal display (formatter.py)
   - Add "Status: Active/Invalidated/Missed/Expired" to formatted output
   
### 3. FIX: Ensure resend job updates delivery properly (bot.py)
   - Verify sent_ok=True is being set correctly
   - Add fallback for signals created but not in delivery table

### 4. FIX: Use Redis for recent signals (core/redis_state.py)
   - Store last 10 sent signals in Redis for instant access

## Implementation Steps:

- [x] 1. Read signal_commands.py and identify exact query
- [x] 2. Added list_recent_signals_for_user function in db/pg_features.py
- [x] 3. Modified signal_commands.py to use new broader query
- [ ] 4. Update formatter to show status information  
- [ ] 5. Test the fixes with /signals command

## What was fixed:

1. Added `list_recent_signals_for_user()` in db/pg_features.py - this function fetches ALL signals for a user in the lookback period, regardless of:
   - sent_ok status (shows signals even if delivery marking failed)
   - outcome status (shows invalidated/missed signals too)

2. Updated signal_commands.py for PREMIUM/VIP to use list_recent_signals_for_user() instead of list_unresolved_signals_for_user()

This ensures users see all their signals, not just the ones marked as "active" or "sent_ok = True".
