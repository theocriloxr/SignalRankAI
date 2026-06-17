# TODO: ML Blocking All Signals Fix

## Status: IN PROGRESS

### Root Causes:
1. ML Hard Filter Block - ML_HARD_FILTER_MIN too high
2. Dynamic Threshold Drift - threshold climbs unbounded when AUC drops  
3. max_score=100 bug - normalization causing misleading scores

### Fixes to implement:

#### 1. ML Hard Filter (FIXED)
- [x] Lower ML_HARD_FILTER_MIN from 0.15 to 0.10
- [x] Current value already shows "0.15" in code

#### 2. Dynamic Threshold Drift (IN PROGRESS)
- [ ] Add clamping to dynamic_threshold.py to prevent unlimited growth
- [ ] Max threshold should be capped at 0.40

#### 3. max_score=100 Bug (PENDING)
- [ ] Find where score normalization creates 100.0
- [ ] Fix to show raw scores instead

#### 4. Diagnostics (PENDING)
- [ ] Add logging to show exactly where signals die

## Implementation Notes:
- The logs show: base=0.50, current_auc=0.72, target=0.85, adjusted=0.59
- This means base_threshold in env is 0.50, not 0.20 as code defaults
- Need to check what ML_PROB_THRESHOLD is set to in environment

## Next Steps:
1. Lower ML_HARD_FILTER_MIN to 0.10
2. Add threshold clamping in ml/dynamic_threshold.py
3. Find and fix max_score normalization
4. Add diagnostic logging
