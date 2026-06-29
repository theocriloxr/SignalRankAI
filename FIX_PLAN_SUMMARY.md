# SignalRankAI Fix Plan Summary

## Based on analysis of the codebase (engine/scoring.py, services/gemini_ml.py, db/session.py, core/tier_constants.py, config.py)

---

## 🔴 BUG #1 — Score Soft-Cap Formula (PRIMARY CAUSE)

**File:** `engine/scoring.py` line ~140
**Current:** `soft_score = 100.0 * (1.0 - math.exp(-raw_score / 75.0))`
**Fix:** Change divisor from 75.0 → 50.0
**Impact:** Raw score 80 → display ≈80 (was ~65), raw 100 → display ≈86

---

## 🔴 BUG #2 — AsyncSessionLocal ImportError

**File:** `services/gemini_ml.py` line ~407
**Current:** `from db.session import AsyncSessionLocal as SessionLocal`
**Fix:** Change to use the async context manager instead: `from db.session import get_session as _get_session_ctx`
**Impact:** Fixes Gemini audit pipeline crashes

---

## 🔴 BUG #3 — DB Connection Pool Settings

**File:** `db/session.py` 
**Current:** Returns pool_size=5, max_overflow=2 when Railway detected
**Fix:** Update to pool_size=8, max_overflow=3 for async; add sync pool settings DB_SYNC_POOL_SIZE=3, DB_SYNC_MAX_OVERFLOW=2
**Impact:** Prevents "too many clients" errors

---

## 🟡 BUG #4 — Tier Score Thresholds  

**File:** `core/tier_constants.py`
**Current:** TIER_SCORE_THRESHOLDS = {"free": 80.0, "premium": 80.0, "vip": 80.0, ...}
**Fix:** Lower to 75.0 for FREE, 73.0 for PREMIUM/VIP
**Impact:** Allows more signals to pass

---

## 🟡 BUG #5 — Score Threshold Config

**File:** `config.py`
**Current:** Already has `PREMIUM_SCORE_THRESHOLD = 25.0` 
**Fix:** No changes needed if using config.py values

---

## Additional Observations

### Already Implemented:
- **Data provider fallback**: `data/market_data.py` has circuit breaker with Binance → yfinance fallback
- **Stale signal validation**: `engine/stale_signal_validator.py` has comprehensive validation
- **YFinance cooldown**: Implemented to prevent repeated failures

### Files That May Need Env Vars (can be set in .env):
- `DB_POOL_SIZE=8`
- `DB_MAX_OVERFLOW=3`
- `DB_SYNC_POOL_SIZE=3`
- `DB_SYNC_MAX_OVERFLOW=2`
- `YFINANCE_CACHE_TTL=60`
- `STALE_PRICE_THRESHOLD_PCT=1.5`

---

## Implementation Priority:

1. **FIX #1** - scoring.py soft-cap divisor (MOST IMPACT)
2. **FIX #2** - gemini_ml.py import fix 
3. **FIX #3** - db/session.py pool settings
4. **FIX #4** - tier_constants.py thresholds
5. Set env vars in deployment
