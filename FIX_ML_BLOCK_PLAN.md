# Fix Plan: ML Blocking All Signals

## Problem
The engine generates signals but ML filter blocks 100% of them:
- `strict_candidates=33 risk_passed=0`  
- `max_score=100.0` but no signals reach final storage

## Root Causes Identified

1. **ML Hard Filter Block** (PRIMARY)
   - Location: `engine/core.py` around line 730
   - Config: `ML_HARD_FILTER_MIN=0.25` (25% minimum ML probability)
   - Impact: ALL signals with ml_probability < 0.25 are rejected
   - Fallback: When ML is offline, threshold is too strict

2. **Score Threshold Gate** (SECONDARY)
   - Location: `_current_min_score_threshold()`  
   - Config: `PREMIUM_SCORE_THRESHOLD=35`
   - Impact: Signals scoring below 35 are rejected at final gate

3. **Dynamic Threshold Drift**
   - The threshold was auto-adjusted to 0.61 based on AUC=0.70 (below target 0.85)
   - When model degrades, threshold rises and blocks more signals

## Fixes to Apply

### Fix 1: Lower ML Hard Filter Threshold
**File**: `engine/core.py`
**Change**: Lower ML_HARD_FILTER_MIN from 0.25 to 0.15
```python
ml_hard_min = float(os.getenv("ML_HARD_FILTER_MIN", "0.15") or 0.15)
```

### Fix 2: Lower Score Threshold  
**File**: `engine/core.py`
**Change**: Lower PREMIUM_SCORE_THRESHOLD from 35 to 25
```python
DEFAULT_MIN_SCORE_THRESHOLD = _env_float("PREMIUM_SCORE_THRESHOLD", 25)
```

### Fix 3: Log Raw Scores for Debugging
**File**: `engine/core.py` in strict_candidates loop
**Add**: Log `_preview_score` with detailed breakdown for diagnostics

### Fix 4: Add ML Fallback Grace
**File**: `engine/core.py`
**Change**: When ML filter fails or returns None, allow signals through instead of blocking

## Implementation Steps

1. Read current threshold values from config
2. Apply Fix 1 (ML threshold)
3. Apply Fix 2 (Score threshold)
4. Apply Fix 3 (Add debug logging)
5. Test the changes

## Expected Outcome After Fixes

Pipeline should show:
- `strict_candidates=33 risk_passed>0` (not 0)
- `final_signals>0`
- `stored>0`

The `max_score=100.0` will still appear but signals will now PASS through to storage.
