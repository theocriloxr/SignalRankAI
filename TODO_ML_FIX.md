# TODO: ML Blocking All Signals Fix

## Status: COMPLETE (All fixes applied)

### Root Causes:
1. ~~ML Hard Filter Block - ML_HARD_FILTER_MIN too high~~ → FIXED: Set to 0.10
2. ~~Dynamic Threshold Drift - threshold climbs unbounded~~ → FIXED: Clamped at 0.40
3. ~~max_score=100 bug~~ → NOT A BUG: By design (scoring caps at 100)

### Fixes Applied:

#### 1. ML Hard Filter (COMPLETE)
- [x] ML_HARD_FILTER_MIN = 0.10 (engine/core.py line ~1571)
- [x] Allows signals with ML probability >= 10% to pass

#### 2. Dynamic Threshold Drift (COMPLETE)
- [x] Added clamping in ml/dynamic_threshold.py
- [x] Max threshold capped at 0.40 regardless of AUC drift

#### 3. max_score=100 (NOT A BUG)
- [x] Scoring caps at 100 by design (scoring.py)
- [x] Logs show raw_scores before cap via _preview_score

#### 4. Diagnostics (IMPROVED)
- [x] ENGINE_PIPELINE_DEBUG logging tracks rejections
- [x] [RISK_REJECTION] log shows ML vs risk filter blocks

### Known Issues to Monitor:
- ML_PROB_THRESHOLD env var may be set to 0.50 (check .env)
- Check logs for [ml.dynamic_threshold] messages

### Expected Results After Fixes:
| Metric | Before | After |
|--------|--------|-------|
| strict_candidates | 33 | 33 |
| risk_passed | 0 | 20-30 |
| final_signals | 0 | 10-20 |
