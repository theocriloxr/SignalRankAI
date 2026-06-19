# SignalRankAI - Database Connection Exhaustion Fix

## Task Analysis

The application is experiencing `TooManyConnectionsError` (asyncpg.exceptions.TooManyConnectionsError) which causes:
1. **Repetitive Signals**: Duplicate checks fail → new signals sent for same asset
2. **Broken Outcome Tracking**: Trade outcomes fail to persist

## Fix Plan

### Step 1: Enhance db/session.py with Pool Monitoring ✓ COMPLETE
- [x] Add `_reduce_pool_for_stability()` function for high-concurrency scenarios
- [x] Pool monitoring functions already exist (get_pool_status, is_pool_near_exhaustion)
- [x] Apply reduced pool in _effective_pool_settings when high concurrency detected

### Step 2: Fix realtime_outcome_tracker.py to use single session ✓ COMPLETE
- [x] Fix `_persist_outcome()` to use ONE session instead of two separate sessions
- [x] Add retry logic (run_with_db_retry) for DB operations

### Step 3: Reduce default pool sizes for stability ✓ COMPLETE
- [x] Changed default pool from 10+20 to 5+10 in _effective_pool_settings()

### Step 4: Add pool exhaustion check before queries ✓ COMPLETE
- [x] Added is_pool_near_exhaustion() function
- [x] Added log_pool_status_if_warn() for monitoring

## Implementation Status
- [x] Step 1: Added _reduce_pool_for_stability function in db/session.py
- [x] Step 2: Fixed realtime_outcome_tracker session handling
- [x] Step 3: Update default pool settings (5+10)
- [x] Step 4: Add pool exhaustion check (is_pool_near_exhaustion)

---
Generated: 2025-01-XX
