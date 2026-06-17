# TODO: Risk Pipeline Diagnostics Fix

## PROBLEM SUMMARY FROM LOG:
```
cycle=15
assets=20
generated_signals=0
max_score=100.0
max_score_pre_threshold=100.0
strategy_signals=247
normalized=247
consensus=65
selected=55
unique=55
strict_candidates=33
risk_passed=0  ← PROBLEM: 100% rejection
final_signals=0
stored=0
```

## ISSUES TO FIX:

### 1. Risk Manager Rejection Tracking (CRITICAL)
**Problem**: risk_passed=0 with NO reason logged
**Fix**: Add rejection reason Counter tracking

### 2. Max Score Always 100.0
**Problem**: max_score=100.0 every cycle
**Fix**: Add score distribution logging (avg, median, top_5)

### 3. Duplicate Candidates
**Problem**: 33 candidates from 20 assets
**Fix**: Log candidate details before risk filtering

### 4. Missing Pipeline Diagnostics
**Problem**: Can't see WHY signals are rejected
**Fix**: Comprehensive pipeline_stats logging

## IMPLEMENTATION STEPS:

### Step 1: Add Risk Rejection Counter
- Location: engine/core.py where strict_candidates are processed
- Add: `risk_rejection_reasons = Counter()`
- Track: spread, atr, rr_ratio, volatility, confidence, etc.

### Step 2: Add Score Distribution Logging
- Location: After scoring in core.py
- Log: top_5_scores, avg_score, median_score

### Step 3: Add Candidate Diagnostics
- Location: Before risk filtering in core.py
- Log: symbol, direction, timeframe per candidate

### Step 4: Enhanced Pipeline Stats
- Location: End of cycle in core.py
- Log: Full breakdown of all rejection reasons

## FILES TO MODIFY:
- engine/core.py

## DEPENDENCIES:
- collections.Counter (already imported in core.py)

## FOLLOWUP:
- Deploy and verify logs show rejection reasons
- Adjust thresholds if needed based on new diagnostics
