# SignalRankAI Improvements TODO

## Task: Adaptive threshold and signal generation improvements

### Issue 1: SQLAlchemy KeyError (FIXED)
- Already in railway_main.py (lines 22-28)
- Ver

### Issue 2: Threshold not using optimizer (TODO)
- Location: engine/core.py around line with `ML_PROB_THRESHOLD`
- Current: Uses env var directly, ignoring threshold_optimizer
- Fix: Use _threshold_optimizer.get_threshold() when available

### Issue 3: Signal count logging (TODO)
- Add logging for signals generated per cycle
- Already exists, verify

### Issue 4: Continuous signal generation (TODO) 
- Main loop continues, but need to verify it's generating multiple signals per cycle
- Already exists

## Implementation Progress

- [x] Step 1: Analyze codebase (COMPLETE)
- [ ] Step 2: Update core.py to use threshold_optimizer
- [ ] Step 3: Add periodic threshold refresh in main loop
- [ ] Step 4: 

## Files to Modify

1. engine/core.py - Use threshold_optimizer for ML threshold
2.
