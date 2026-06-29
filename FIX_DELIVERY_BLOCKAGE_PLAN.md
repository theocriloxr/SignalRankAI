# FIX DELIVERY BLOCKAGE PLAN

## Problem Summary

Users are NOT receiving signals despite:
- generated_signals=5 
- stored=5
- resend showing: "no signals passed quality filters (min_score=75.0, max_signals=8)"

### Root Causes Identified:

#### 1. CRITICAL: Signal Delivery Filtering Mismatch (ALREADY FIXED IN CODE, CHECK DEPLOYMENT)
**Location**: signalrank_telegram/bot.py (line ~147)
- Code shows: `resend_min_score = float(os.getenv("RESEND_MIN_SCORE", "70") or 70)` ✅
- BUT logs still show min_score=75.0 - indicates OLD CODE is running
- **Action**: Ensure the latest bot.py code is deployed

**Verification Needed**:
```bash
# Check Railway deployment for latest code
grep -n "RESEND_MIN_SCORE" signalrank_telegram/bot.py | head -5
```

#### 2. CRITICAL: PostgreSQL Connection Pool Still Too High
**Location**: db/session.py with pool_size=10, max_overflow=20

**Error Log**: "FATAL: sorry, too many clients already"

**Problem**: 
- Current: pool_size=10, max_overflow=20 (30 total connections)
- Railway Hobby Limit: ~20 connections max
- Fix NOT applied

**Fix Required**:
```python
# In db/session.py, change _effective_pool_settings():
def _effective_pool_settings() -> tuple[int, int]:
    # FIX: Use smaller pool for Railway
    if _is_railway_runtime():
        # Railway hobby: max 20 connections
        return 5, 2  # 7 total (was 30!)
    return 10, 20  # Default (was 30!)
```

#### 3. CRITICAL: ML Model Class Imbalance Not Fixed
**Location**: ml/train_model.py

**Problem**: 
- Accuracy: 0.88 (high because mostly predicting "loss")
- AUC: 0.5091 (essentially random)
- Dataset: 2809 losers vs 537 winners (5.2:1 imbalance)
- No scale_pos_weight being used

**Fix Required**:
```python
# In train_model.py, train_model() function:
# Add scale_pos_weight for XGBoost:
loss_count = (y_train == 0).sum()
win_count = (y_train == 1).sum()
scale_pos_weight = loss_count / max(1, win_count)

model = xgb.XGBClassifier(
    n_estimators=100,
    max_depth=5,
    learning_rate=0.1,
    subsample=0.8,
    colsample_bytree=0.8,
    objective='binary:logistic',
    scale_pos_weight=scale_pos_weight,  # ADD THIS
    random_state=42,
    verbosity=1,
)
```

#### 4. MEDIUM: Dynamic Threshold Still Spamming Logs
**Location**: ml/dynamic_threshold.py (FIXED in file, but engine may be calling wrong function)

**Problem**: Logs still show: "adjusted=0.40 clamped=0.40" hundreds of times

**Investigation**:
- dynamic_threshold.py HAS the fix (cooldown, persistence)
- BUT the engine might be calling old implementation

**Fix Required**:
- Ensure engine uses `get_dynamic_ml_threshold()` instead of inline calculation
- Verify Redis persistence is working

#### 5. HIGH: AUDUSD Price Normalization Bug
**Location**: data/symbol_formatter.py or signal creation

**Problem**:
```
entry=0.01570
live=0.71124
drift=4430%
```

**Fix Required**:
- Add FX pair normalization check in signal creation
- Validate entry price < 1.0 for non-crypto pairs

#### 6. MEDIUM: Outcome Tracker Missing candles
**Location**: worker/outcome_tracker.py

**Problem**: "No candles found for XXX" - outcome evaluation failing

**Fix Required**:
- Add fallback to yfinance when primary provider fails
- Add outcome_failed_no_data counter to track issues

## Implementation Order:

### Step 1: Apply DB Pool Reduction (CRITICAL)
**File**: db/session.py
```python
def _effective_pool_settings() -> tuple[int, int]:
    # Add Railway detection
    if _is_railway_runtime():
        return 5, 2  # 7 total connections max
    return 10, 20
```
Also add pool_recycle and pool_pre_ping to prevent stale connections.

### Step 2: Apply ML scale_pos_weight Fix (CRITICAL)
**File**: ml/train_model.py
- Add: scale_pos_weight = loss_count / max(1, win_count)
- Pass to XGBClassifier

### Step 3: Verify Delivery Threshold Fixed (CRITICAL)
**File**: signalrank_telegram/bot.py
- Verify RESEND_MIN_SCORE is using 70 (not 75!)
- Set env var on Railway: RESEND_MIN_SCORE=70

### Step 4: Add Audit Logging (HIGH)
**File**: signalrank_telegram/bot.py
- Add delivery audit logs every decision:
```python
logger.info(
    "[delivery_audit] signal=%s score=%s threshold=%s passed=%s",
    signal.id,
    signal.score,
    min_score,
    signal.score >= min_score
)
```

### Step 5: Fix AUDUSD Normalization (HIGH)
**File**: data/symbol_formatter.py or signal creation code
- Add FX validation

### Step 6: Add Outcome Tracker Missing Data Counter (MEDIUM)
**File**: worker/outcome_tracker.py
- Track: outcome_failed_no_data

## Expected Outcome After Fixes:
- Users receive stored signals immediately  
- Connection exhaustion eliminated (max 7 connections)
- ML model has predictive power (AUC > 0.65 with scale_pos_weight)
- Clean logs without threshold spam
- price normalization bug fixed

## Verification Commands:
```bash
# Check PostgreSQL connections
SELECT count(*) FROM pg_stat_activity WHERE datname = 'railway';

# Check stored signals
SELECT signal_id, score, created_at FROM signals ORDER BY created_at DESC LIMIT 10;

# Check ML model AUC
redis-cli get ml:model:auc
```

## TODO.md Creation:
Create a TODO.md with each step as a checkable item.
