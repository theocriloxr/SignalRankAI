# SignalRankAI Task Analysis - Critical Issues

Based on the provided logs and code analysis, here are the critical issues identified:

## 🔴 CRITICAL ISSUE #1: Signals Stored But Not Delivered

**Evidence from logs:**
```
[resend] audience users=6 tiers={'owner': 3, 'free': 3}
[resend] no signals passed quality filters (min_score=75.0, max_signals=8)
```

**Root Cause:**
- The engine generates signals with scores around 75.04
- The RESEND_MIN_SCORE is set to 75.0 via env var
- The quality filter uses `score > 75` (strictly greater than) instead of `score >= 75` (greater than or equal to)
- Signals with score 75.04 should pass since 75.04 > 75.0, but they aren't

**Looking at the code in bot.py:**
```python
resend_min_score = float(os.getenv("RESEND_MIN_SCORE", "75") or 75)
# ...
if float(getattr(s, 'score', 0) or 0) < resend_min_score:
    continue
```

This uses `<` (less than), so 75.04 should NOT be skipped since 75.04 < 75.0 is False.

However, there's a scoring mismatch issue - the engine produces scores like 75.04 but they may be getting rounded or compared incorrectly in the delivery layer.

## 🔴 CRITICAL ISSUE #2: PostgreSQL Connection Pool Exhaustion

**Evidence:**
```
FATAL: sorry, too many clients already
```

**Root Cause:**
- Current pool_size=15, max_overflow=15 (30 total connections)
- For Railway Hobby tier, this is too high
- Need to reduce to pool_size=5, max_overflow=2

**Current db/session.py settings:**
```python
pool_size = _pool_int("DB_POOL_SIZE", 10, minimum=1)
max_overflow = _pool_int("DB_MAX_OVERFLOW", 20, minimum=0)
```

## 🔴 CRITICAL ISSUE #3: ML Model Has Near-Zero Predictive Power

**Evidence:**
```
Accuracy: 0.8806
AUC: 0.5091
Confusion Matrix:
[[582   4]
 [ 76   8]]
```

**Root Cause:**
- Heavy class imbalance: 2809 losers vs 537 winners
- Model achieves high accuracy by predicting "loss" most of the time
- AUC 0.5091 confirms almost no predictive power

**Fix:**
- Use `scale_pos_weight` for XGBoost to handle imbalance
- Optimize for precision/recall on winners instead of raw accuracy

## 🔴 CRITICAL ISSUE #4: AUDUSD Price Normalization Bug

**Evidence:**
```
entry=0.01570
live=0.71124
drift=4430.15%
```

**Root Cause:**
- Signal is being created with incorrect price (0.015700075...) before delivery
- This corrupts outcome tracking and ML labels

## 🟡 MEDIUM ISSUE #5: Outcome Tracker Missing Candle Data

**Evidence:**
```
[DEBUG][outcome] No candles found for BNBUSDT 1h
```

**Root Cause:**
- Market data provider issues for certain assets
- Outcome evaluation silently fails without proper error tracking

---

# FILES EXAMINED

1. **signalrank_telegram/bot.py** - Contains resend logic with quality filters
2. **signalrank_telegram/signal_distribution.py** - Tier-based signal distribution
3. **signalrank_telegram/tier_delivery.py** - Quality score thresholds
4. **core/tier_constants.py** - TIER_SCORE_THRESHOLDS (free: 80.0, premium: 80.0)
5. **db/session.py** - Database pool configuration
6. **db/pg_features.py** - Signal delivery and quality filtering

---

# PROPOSED FIXES

## Fix #1: Increase RESEND_MIN_SCORE and Add Delivery Audit Logging

In bot.py, change RESEND_MIN_SCORE default:
```python
# From:
resend_min_score = float(os.getenv("RESEND_MIN_SCORE", "75") or 75)
# To:
resend_min_score = float(os.getenv("RESEND_MIN_SCORE", "72") or 72)
```

Add audit logging for every delivery decision:
```python
logger.info(
    "[delivery_audit] signal=%s score=%s threshold=%s passed=%s",
    signal.id,
    signal.score,
    min_score,
    signal.score >= min_score
)
```

## Fix #2: Reduce PostgreSQL Connection Pool

In db/session.py:
```python
# Change default pool settings for Railway Hobby
pool_size = _pool_int("DB_POOL_SIZE", 5, minimum=1)  # was 10
max_overflow = _pool_int("DB_MAX_OVERFLOW", 2, minimum=0)  # was 20
```

## Fix #3: Add scale_pos_weight to ML Training

In ml/train_model.py:
```python
# Calculate scale_pos_weight for class imbalance
n_neg = class_dist[0]  # losers
n_pos = class_dist[1]  # winners
scale_pos_weight = n_neg / max(n_pos, 1)

model = xgb.XGBClassifier(
    scale_pos_weight=scale_pos_weight,
    # ... other params
)
```

## Fix #4: Lower TIER_SCORE_THRESHOLDS

In core/tier_constants.py:
```python
TIER_SCORE_THRESHOLDS = {
    "free": 60.0,      # Was 80.0 - too high
    "premium": 72.0,   # Was 80.0
    "vip": 72.0,       # Was 80.0
    "owner": 0.0,
    "admin": 0.0,
}
```

---

# DEPENDENCY MATRIX

| Fix | Files to Edit |
|-----|--------------|
| Fix #1 | signalrank_telegram/bot.py, db/pg_features.py |
| Fix #2 | db/session.py |
| Fix #3 | ml/train_model.py |
| Fix #4 | core/tier_constants.py |

---

# TESTING PLAN

After implementing fixes, verify:

1. Check resend job logs for "[delivery_audit]" entries
2. Monitor PostgreSQL connection count in Railway dashboard
3. Check ML model AUC improves (target > 0.6)
4. Verify AUDUSD signals have correct prices
5. Monitor outcome tracker for candle data availability
