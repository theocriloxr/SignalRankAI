# TODO: SignalRankAI Delivery & Infrastructure Fixes

## Priority 1: CRITICAL - Signal Delivery (Done ✅)

**Status**: Already fixed in bot.py
- Changed `RESEND_MIN_SCORE` from 75 to 70
- Allows ~75 score signals to pass quality filters

Files: `signalrank_telegram/bot.py`

---

## Priority 2: CRITICAL - PostgreSQL Connection Pool

**Problem**: Railway detection not working - logs show pool_size=15, max_overflow=15 instead of 5+2=7

**Root Cause**: 
- `_is_railway_runtime()` function exists but may not detect correctly
- Even with detection, the fallback pool of 10+20=30 is too high

**Fix Required**:
1. Force Railway pool settings at engine creation
2. Add explicit Railway env var check as backup

Files: `db/session.py`

**Changes Needed**:
- Line ~67-82: Strengthen Railway detection logic
- Ensure pool_size=5, max_overflow=2 for Railway
- Add `pool_recycle=300` and `pool_pre_ping=True`

---

## Priority 3: HIGH - ML Class Imbalance

**Problem**: 
- Training accuracy 88% is fake (mostly predicting 0/losers)
- AUC 0.5091 = random predictions
- Dataset: 2809 losers vs 537 winners

**Fix Required**:
1. Add `scale_pos_weight` parameter to XGBoost
2. Calculate: scale_pos_weight = negative_count / positive_count

Files: `ml/train_model.py`

**Changes Needed**:
- Line ~280: Add scale_pos_weight calculation
- Add to XGBClassifier parameters

---

## Priority 4: MEDIUM - Dynamic Threshold Spam

**Problem**: 
- Logs show "adjusted=0.40 clamped=0.40" hundreds of times
- Recalculates on every signal instead of periodically

**Fix Required**:
1. Track outcome count in Redis
2. Recalculate only every 100 outcomes
3. Log only when threshold actually changes

Files: `ml/dynamic_threshold.py` or `core/redis_state.py`

---

## Priority 5: MEDIUM - Delivery Audit Logging

**Problem**: No visibility into why signals fail delivery filters

**Fix Required**:
1. Add audit log for every delivery decision
2. Log: signal_id, score, threshold, passed=True/False

Files: `signalrank_telegram/bot.py`

---

## Priority 6: LOW - AUDUSD Price Normalization

**Problem**: entry=0.01570 but live=0.71124 (invalid price)

**Fix Required**: Add FX pair price validation before signal creation

Files: `data/symbol_formatter.py` or signal creation code

---

## Implementation Order

1. ✅ Signal delivery (DONE - 75→70)
2. PostgreSQL pool fix (IMMEDIATE)
3. ML class imbalance (IMMEDIATE)  
4. Delivery audit logs (SOON)
5. Dynamic threshold (NEXT SPRINT)
6. AUDUSD normalization (NEXT SPRINT)

## Test Commands

After fixes deployed:
```bash
# Check pool settings
grep "pool_size" engine_stderr.log | head -1

# Check ML AUC
redis-cli get ml:model:auc

# Check delivery passes
grep "no signals passed quality" bot_stdout.log | wc -l
