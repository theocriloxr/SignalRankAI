# Fix Plan: Threshold and Scoring Issues

## Issues Identified from Logs

### Issue 1: max_score=100 (appears stuck at 100.0)
- This is actually NOT a bug - it's the max of pre-threshold candidates
- The bug is that no signals pass the FINAL threshold to become final_signals

### Issue 2: risk_rejected_risk=36, final_signals=0
**ROOT CAUSE**: All 36 strict_candidates are failing at one of these gates:
1. Advanced filters (advanced_filters.run_all_filters)
2. Score threshold (PREMIUM_SCORE_THRESHOLD)
3. Ultra quality filter (if enabled)

Looking at the code flow:
1. strict_candidates generated (36)
2. ML filter applied → all pass (risk_rejected_ml=0)
3. risk_passed becomes the list of signals that passed ML
4. Scoring computed for risk_passed signals
5. Final score threshold applied → ALL REJECTED (final_signals=0, risk_rejected_risk=36)

## Fixes to Apply

### Fix 1: Lower PREMIUM_SCORE_THRESHOLD
Current: 35.0 in config.py
Engine default: 30.0 (in core.py)
Fix: Lower to 25.0 to allow more signals through

### Fix 2: Lower ML_PROB_THRESHOLD  
Current: 0.25 in config.py
Engine default: 0.15 
Fix: Lower to 0.15 to allow more signals through ML

### Fix 3: Verify Advanced Filters aren't blocking all signals
The SmartFilterSuite.run_all_filters() returns passed=False only when rejections list has items.
Most filters return False (allow) by default - so this is NOT the issue.

## Plan
1. Update config.py with lower thresholds
2. Update core.py runtime threshold defaults if needed
3. Verify no other blocking issues

## Testing
After fix, check that:
- final_signals > 0
- risk_rejected_risk < 36 (some pass)
