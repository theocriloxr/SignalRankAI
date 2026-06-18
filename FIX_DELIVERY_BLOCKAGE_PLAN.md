# SignalRankAI Critical Fix Plan

## Issues Identified

### Issue #1: Signal Delivery Filter Mismatch (CRITICAL)
**Problem:** Resend job uses min_score=75 but tier_constants expects FREE threshold at 80

**Location:** 
- `signalrank_telegram/bot.py` uses `RESEND_MIN_SCORE=75` (default)
- `core/tier_constants.py` has `TIER_SCORE_THRESHOLDS["free"] = 80.0`

**Evidence from logs:**
```
[resend] no signals passed quality filters (min_score=75.0, max_signals=8)
```

**Fix:** 
- Option A: Change tier_constants.py FREE threshold from 80→75 (match resend)
- Option B: Change RESEND_MIN_SCORE env default from 75→80 (match tier_constants)
- Selected: Option B - Set RESEND_MIN_SCORE=80 to align with tier_constants

### Issue #2: PostgreSQL Pool Exhaustion (CRITICAL)
**Problem:** Pool size 10 + overflow 20 = 30 connections for Railway Hobby

**Logs:**
```
FATAL: sorry, too many clients already
```

**Location:** `db/session.py` - `_effective_pool_settings()`

**Fix:**
- Railway: pool_size=5, max_overflow=2
- Add `pool_recycle=300`, `pool_pre_ping=True`

### Issue #3: Missing Delivery Audit Logs (HIGH)
**Problem:** No logging for why signals are filtered/dropped

**Fix:** Add detailed audit logging for every delivery decision

## Implementation Order

### Step 1: Fix Resend Quality Filter (Immediate)
File: `signalrank_telegram/bot.py` (around line with RESEND_MIN_SCORE)
Change: `RESEND_MIN_SCORE` default from "75" → "80"

### Step 2: Fix PostgreSQL Pool (Immediate)  
File: `db/session.py`
Change: Reduce default pool for Railway

### Step 3: Add Audit Logs (High Priority)
File: `signalrank_telegram/bot.py` - in resend job
Add: Score threshold decision logging

## Files to Modify
1. `signalrank_telegram/bot.py` - resend min_score, audit logs
2. `db/session.py` - pool settings for Railway
