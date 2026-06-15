# SignalRankAI - Apply All Fixes Plan

## Executive Summary

This document outlines all fixes to be applied based on the comprehensive analysis of the SignalRankAI codebase. The fixes address:
1. Import/command errors
2. Engine scoring issues  
3. Database connection exhaustion
4. API rate limiting
5. Market hours/broker mapping
6. ML model stability
7. Trade correlation/exposure
8. Redis caching
9. Graceful shutdown

---

## Fix Status Analysis

### ✅ Already Applied (Verified)
1. **Fix #1 - audit_recent Import**: `services/gemini_ml.py` has `audit_recent = audit_recent_signals` alias
2. **Fix #6 - Dynamic Threshold**: `ml/dynamic_threshold.py` returns calculated threshold
3. **Partial Fix #5 - Rate Limiting**: `_fetch_market_data_for_assets` has semaphore and delays

### ❌ Not Applied (Needs Implementation)
1. **Fix #2 - Max Score 100.0** 
2. **Fix #3 - /signals status filtering**
3. **Fix #4 - PostgreSQL pool limit** (current default: 15/15, needs: 3/5)
4. **Fix #7 & #8 - Market Hours utils**
5. **ML Stability (scale_pos_weight, EMA)**
6. **Trade Correlation**
7. **Redis Caching**
8. **Graceful Shutdown**

---

## Implementation Plan

### Phase 1: Critical Fixes (Database + Import)

#### Fix #4: PostgreSQL Pool Limit
**File:** `db/session.py`
**Current:** Default pool_size=15, max_overflow=15
**Target:** pool_size=3, max_overflow=5
**Action:** Update `_effective_pool_settings()` to have stricter defaults

#### Fix #1 Verify: Import Check
**File:** `signalrank_telegram/commands.py`  
**Current:** Uses `audit_recent` which maps to `audit_recent_signals`
**Status:** ✅ Already has alias

---

### Phase 2: Engine Scoring Fixes

#### Fix #2: Max Score 100.0 + >= operator
**File:** `engine/core.py`
**Location:** Advanced Filters section in main_loop
**Changes:**
1. Change `>` to `>=` for threshold comparison
2. Add safe parsing of PREMIUM_SCORE_THRESHOLD_FORCE env var
3. Calculate and log max_scores pre/post threshold

#### Fix #3: /signals Status Expansion
**File:** `signalrank_telegram/commands.py`
**Location:** `signals_command` function
**Changes:** Expand status filter to include "issued", "open" statuses

---

### Phase 3: Market Hours & Broker Mapping

#### Fix #7 & #8: Create utils/market_hours.py
**New File:** `utils/market_hours.py`
**Functions:**
- BROKER_MAP dictionary
- resolve_broker(symbol) -> broker
- is_market_open(symbol) -> bool

**Integration:** Import into engine/core.py and filter target_asset_universe

---

### Phase 4: ML Stability

#### Fix #9: scale_pos_weight
**File:** `ml/train_model.py`
**Changes:** Calculate class imbalance ratio and apply scale_pos_weight

#### Fix #10: EMA Threshold Smoothing  
**File:** `ml/dynamic_threshold.py`
**Changes:** Add previous_threshold parameter and 30% EMA smoothing

---

### Phase 5: Trading Improvements

#### Fix #11: Trade Correlation
**File:** `engine/risk_manager.py` or `engine/core.py`
**Changes:** Add check_portfolio_exposure function

---

### Phase 6: Infrastructure

#### Fix #12: Redis Caching
**File:** `data/pipeline.py` or `fetch_market_data_cached`
**Changes:** Add Redis cache with TTL

#### Fix #13: Graceful Shutdown
**File:** `railway_main.py` or entry point
**Changes:** Add signal handlers for SIGTERM/SIGINT

---

## Execution Order

1. Apply Fix #4 (Database pool) - CRITICAL
2. Verify Fix #1 (Import) - DONE
3. Apply Fix #2 (Max Score) 
4. Apply Fix #3 (/signals)
5. Create Fix #7 & #8 (Market Hours)
6. Apply Fix #9 (ML scale_pos_weight)
7. Apply Fix #10 (EMA smoothing)
8. Apply Fix #11 (Correlation)
9. Apply Fix #12 (Redis caching)
10. Apply Fix #13 (Graceful shutdown)

---

## Testing Recommendations

After applying fixes:
1. Run test_imports.py to verify no import errors
2. Run test_engine_diag.py for engine health
3. Check database connection stability
4. Verify signal generation works

---

*Last Updated: Auto-generated*
*Plan Version: 1.0*
