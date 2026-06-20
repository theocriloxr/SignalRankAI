# Signal Spam Fix TODO List

## P0 - Critical Fixes (Immediate)

- [ ] Fix signal deduplication API calls in engine/loop.py
  - [ ] Change from: `is_dup = await dedup.is_duplicate(asset, timeframe, sig.direction, sig.entry)`
  - [ ] Change to: `is_dup = await dedup.is_duplicate(signal_dict)`
  - [ ] Change from: `await dedup.register_signal(...)` 
  - [ ] Change to: `await dedup.mark_seen(signal_dict)`

- [ ] Add timeframe-based cooldown to deduplicator
  - [ ] 4H: 90 minutes cooldown
  - [ ] 1D: 6 hours cooldown
  - [ ] 1H: 20 minutes cooldown
  - [ ] 15M: 10 minutes cooldown

- [ ] Fix outcome tracker symbol mapping
  - [ ] Add normalize_symbol_for_outcome() function
  - [ ] Handle SOLUSDT -> SOLUSD conversion
  - [ ] Test with actual signals

## P1 - High Priority

- [ ] Add signal refresh/update logic
  - [ ] Check if signal exists before creating alert
  - [ ] Update metadata instead of creating new signal
  - [ ] Only send new alert on material changes

- [ ] Fix trade lifecycle tracking
  - [ ] Ensure open trades resolve properly
  - [ ] Link outcome to signal_id correctly

- [ ] Fix active signal message updates
  - [ ] In-place edit instead of new message
  - [ ] Preserve chat_id/message_id for edits

## P2 - Medium Priority

- [ ] Audit callback handlers
  - [ ] Verify pattern matching
  - [ ] Test button interactions

- [ ] Add state persistence
  - [ ] Persist user_data to database
  - [ ] Restore on callback

## Testing Checklist

- [ ] Test SOLUSDT signal spam is fixed
- [ ] Test cooldown is respected
- [ ] Test outcome tracking works
- [ ] Test inline buttons work
- [ ] Test signal updates work

## Completion Criteria

1. SOLUSDT BUY signals appear at most once per 90 minutes (for 4H)
2. No duplicate alerts for same setup
3. Outcome tracking finds correct trades
4. Inline buttons respond correctly
