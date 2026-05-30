# SignalRankAI Improvements TODO

## Task: Adaptive threshold and signal generation improvements
Status: Complete.

### Issue 1: SQLAlchemy KeyError (FIXED)
- Already in railway_main.py (lines 22-28)
- Ver

### Issue 2: Threshold not using optimizer (FIXED)
- Location: engine/core.py around line with `ML_PROB_THRESHOLD`
- Current: Uses the adaptive threshold optimizer when available, with env fallback
- Fix: Use _threshold_optimizer.get_threshold() when available

### Issue 3: Signal count logging (FIXED)
- Add logging for signals generated per cycle
- Already exists

### Issue 4: Continuous signal generation (FIXED)
- Main loop continues and generates multiple signals per cycle when eligible

## Implementation Progress

- [x] Step 1: Analyze codebase (COMPLETE)
- [x] Step 2: Update core.py to use threshold_optimizer
- [x] Step 3: Add periodic threshold refresh in main loop
- [x] Step 4: Validate behavior and log thresholds cleanly

## Files to Modify

1. engine/core.py - Use threshold_optimizer for ML threshold
2. Complete
