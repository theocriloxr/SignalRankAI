# ML Drift - Empty ml_shadow_predictions Fix Plan

## Root Cause Analysis

The `ml_shadow_predictions` table is empty because:

1. **ML Drift**: Model accuracy dropped (Δacc=0.112, Δauc=0.329), causing max_score to plummet from 82.43 to 56.67
2. **Threshold Too High**: Current threshold is 0.55 (55%), but model outputs 56% - so signals are REJECTED before shadow predictions can be saved
3. **Data Rate Limits**: Polygon 429 errors are causing stale data, which contributes to drift

## Fix Steps

### Step 1: Lower ML Probability Threshold (CRITICAL)

Update the threshold to allow the drifted model's 56% predictions through:

```sql
-- Run in Railway PostgreSQL console
UPDATE threshold_configs SET value = '0.50' WHERE key = 'ml_min_confidence';
```

Or set via environment variable:
```
ML_PROB_THRESHOLD=0.50
```

### Step 2: Remove Low-Liquidity Assets Causing 429 Errors

Remove these from your TRADABLE_ASSETS to reduce rate limits:
- DOGEIDR
- USDTARS  
- Any other exotic pairs

Keep only: BTC, ETH, SOL, XAU, Major FX pairs

### Step 3: Verify Shadow Prediction Persistence

Check that the shadow table gets populated:

```sql
SELECT COUNT(*) FROM ml_shadow_predictions;
-- Should be > 0 now
```

### Step 4: Force Model Retrain (Long-term fix)

Once you have 500+ rows in `ml_shadow_predictions` with outcomes:

```bash
# Trigger retrain via env var or API
ML_WEEKLY_RETRAIN_ENABLED=1
```

## Verification

After applying the fixes, check:

1. `SELECT COUNT(*) FROM ml_shadow_predictions;` - should be > 0
2. Logs should show "[ml] scored asset=X prob=0.56"
3. Engine should generate more signals

## Dependencies

- None - these are configuration fixes only
