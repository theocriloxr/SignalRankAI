# TODO: ML Shadow Predictions Table Fix

## Problem Summary
The `ml_shadow_predictions` table remains empty while the engine generates signals with max_score=0. This indicates the ML model is running but returning 0 probability for all candidates, and shadow predictions aren't being persisted.

## Root Causes Identified

### 1. Feature Vector Mismatch (Primary)
- Model expects specific features in `ml/model.json` (38 features)
- Signals passed from engine may be missing many required features
- `_feature_vector()` in `engine/ml.py` returns None when features are missing
- This causes `score_signal()` to return None, skipping shadow prediction

### 2. Silent Failure Without Logging
- No DEBUG logging when ML scoring fails due to missing features
- INFO level hides the real error messages

### 3. Data Provider 429 Errors
- Binance Restricted: Binance pairs disabled
- Rate Limited: fetch_failed symbol=BRENT status=429
- Missing technical indicator data causes feature calculation to fail

### 4. Feature Schema Strict Mode
- `ML_STRICT_SCHEMA` defaults to False, but might be set to True
- Missing features return None instead of default values

## Implementation Plan

### Step 1: Fix Feature Vector in engine/ml.py
Edit the `_feature_vector()` function to provide sensible defaults instead of None when features are missing.

```python
# Change from returning None to using default values
missing = [col for col in feature_cols if col not in values]
if missing:
    logger.debug("[ml] missing features, using defaults: %s", missing[:5])
    # Don't return None - use 0.0 for missing features instead
```

### Step 2: Always Persist Shadow Predictions
Edit `engine/ml.py` `score_signal()` to always write to ml_shadow_predictions, even when probability is 0 or None.

### Step 3: Add Comprehensive Debug Logging
Change LOG_LEVEL to DEBUG to see [ml] skipping prediction messages.

### Step 4: Fix scoring.py max_score=0 Issue
Review and fix the scoring thresholds in engine/scoring.py that are causing max_score=0.

### Step 5: Ensure Feature Data Availability
Verify external data providers are working and not hitting 429 rate limits.

## Execution Order

1. First: Fix feature vector defaults in engine/ml.py
2. Second: Always persist shadow predictions
3. Third: Add DEBUG logging
4. Fourth: Verify and test
