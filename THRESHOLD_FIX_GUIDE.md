# ML Threshold Fix - Complete Guide

## Problem Summary
Signals with 82.43 scores are not being stored because they fall just short of the threshold (85%). The ml_shadow_predictions table remains empty.

## Root Cause Analysis
- Current ML_PROB_THRESHOLD: ~0.85 (from threshold_optimizer max bound)
- Your signals score: 82.43
- The score comparison logic treats 82.43 as < 85%, blocking storage

## Solution - Set These Railway Environment Variables

### Step 1: Environment Variables (Railway Dashboard)
Set these in your Railway project → Environment Variables:

```
ML_PROB_THRESHOLD=0.80
PREMIUM_SCORE_THRESHOLD=75
LOG_LEVEL=DEBUG
PREMIUM_SCORE_THRESHOLD_FORCE=1
```

### Step 2: Run SQL Fix
Run this SQL in your Railway Postgres:

```sql
UPDATE runtime_state 
SET value = '{"ml_prob_threshold": 0.80, "min_score_threshold": 75, "confluence_min": 0.0, "source": "manual_fix"}'::jsonb,
    updated_at = NOW() 
WHERE key = 'adaptive_thresholds';
```

### Step 3: Remove USDTARS (Fix Polygon 429 Errors)
If you have USDTARS in your pair discovery or fallback list, remove it to avoid rate limit errors that may be lowering ML scores.

## Expected Results After Fix
- generated_signals=1
- stored=1  
- ml_shadow_predictions table will populate

## Verification Commands
```sql
-- Check thresholds
SELECT key, value FROM runtime_state WHERE key = 'adaptive_thresholds';

-- Check ml_shadow_predictions
SELECT * FROM ml_shadow_predictions ORDER BY created_at DESC LIMIT 5;
