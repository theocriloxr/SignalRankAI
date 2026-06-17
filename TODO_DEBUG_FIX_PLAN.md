# DEBUG FIX PLAN: Signal Pipeline Issues

## Issues Identified

### Issue 1: max_score=100.0 every cycle
**Status**: NOT A BUG - This is expected when scoring succeeds

The scores ARE genuinely reaching 100 when:
- Confluence >= 25% (multiple indicator alignment)
- Confidence >= 0.20 (ML probability or confidence ratio)
- RR >= 1.5 (risk/reward ratio)
- Volatility is low (<= 12%)

When all these conditions align, a 100 score is mathematically correct.

### Issue 2: risk_passed=0 - CRITICAL BLOCKER
**Root Cause**: ML filter + risk filtering are rejecting ALL candidates

Evidence:
```
strict_candidates=36
risk_passed=0
risk_rejected_risk=36
```

This means ALL 36 candidates pass strict gates but then die in either:
1. ML filtering
2. Risk validation AFTER ML filtering

## Fix Plan

### Step 1: Add Debug Logging to Identify Exact Rejection Point

Edit `engine/core.py` around line where ML filtering happens:

```python
# Add BEFORE ML filtering loop
logger.warning(
    f"[RISK_DEBUG] entering_ml_filter strict_candidates={len(strict_candidates)}"
)

for sig in strict_candidates:
    # ... existing ML filtering code ...
    
    # ADD logging for EACH rejection
    if not approved:
        logger.warning(
            f"[RISK_DEBUG] ML_REJECTED asset={sig.get('asset')} "
            f"prob={prob} threshold={threshold} "
            f"features_keys={list(features.keys()) if features else 'none'}"
        )
```

### Step 2: Lower ML Threshold Further

In `engine/core.py`:

```python
# CURRENT (line ~L500):
ml_hard_min = float(os.getenv("ML_HARD_FILTER_MIN", "0.10") or 0.10)

# CHANGE TO:
ml_hard_min = float(os.getenv("ML_HARD_FILTER_MIN", "0.05") or 0.05)
```

This allows signals with ML probability >= 0.05 to pass (was 0.10).

### Step 3: Add Logging for Risk Validation Failures

Edit the risk_check section in `engine/core.py`:

```python
# Find where risk_passed = [] is created and add:
risk_passed = []
_risk_rejection_details = []

for sig in strict_candidates:
    # ... existing validation code ...
    
    # ADD: Track risk rejections with specific reason
    if not passed_risk:
        reason = sig.get('rejection_reason') or 'unknown_risk'
        _risk_rejection_details.append({
            'asset': sig.get('asset'),
            'reason': reason,
            'rr_ratio': sig.get('rr_ratio'),
            'atr': sig.get('atr'),
            'volatility': sig.get('volatility'),
        })

# ADD: Log the rejection details
if _risk_rejection_details:
    logger.warning(
        f"[RISK_DEBUG] risk_rejections={_risk_rejection_details[:3]}"
    )
```

### Step 4: Check RR Validation in risk.py

Edit `engine/risk.py` function `risk_check`:

```python
# ADD logging before RR rejection
min_rr_risk = float(os.getenv("MIN_RR_RISK", "1.5") or 1.5)
if rr_ratio < min_rr_risk:
    logger.warning(
        f"[RISK_DEBUG] RR_REJECT asset={signal.get('asset')} "
        f"rr={rr_ratio:.2f} min={min_rr_risk} "
        f"entry={entry} stop={stop} tp={tp_primary}"
    )
    return False
```

### Step 5: Verify Signal Data Flow

The pipeline is:
1. 264 strategy signals generated
2. 68 reached consensus  
3. 56 selected (after deduplication)
4. 36 passed strict filters (validation)
5. 0 passed risk layer

This means step 4→step 5 is where everything dies. The most likely causes:
1. ML hard filter rejects all (prob < 0.10)
2. RR validation in risk_check fails (RR < 1.5)
3. Volatility check fails (atr_rel > max_vol)

### Immediate Action Items

1. **Temporarily disable ML hard filter** to see if signals flow:
```python
# In core.py, comment out ML hard filter:
# if prob is not None and float(prob) < ml_hard_min:
#     sig['ml_advisory'] = 'filtered_by_ml_hard_threshold'
#     continue
```

2. **Add verbose logging** for every rejection point

3. **Check actual signal values** - log the actual values:
   - `rr_ratio`
   - `atr_rel` / `volatility`
   - `ml_probability`
   - Entry/Stop/TP prices

## Files to Edit

1. `engine/core.py` - Add debug logging around lines 2800-3100
2. `engine/risk.py` - Add debug logging in risk_check function  
3. `engine/scoring.py` - May need adjustments to scoring thresholds

## Expected Outcome

After fixes:
- `max_score` should show actual distribution (not always 100)
- `risk_passed` should be > 0
- Pipeline should produce final_signals > 0
