# SignalRankAI - Database Connection Exhaustion Fix

## Task Analysis

The application is experiencing `TooManyConnectionsError` (asyncpg.exceptions.TooManyConnectionsError) which causes:
1. **Repetitive Signals**: Duplicate checks fail → new signals sent for same asset
2. **Broken Outcome Tracking**: Trade outcomes fail to persist

## Fix Plan

### Step 1: Enhance db/session.py with Pool Monitoring
- Add `is_pool_near_exhaustion()` check function
- Add warning threshold env var
- Add pool status logging

### Step 2: Update db/pg_features.py with Retry Logic  
- Wrap deduplication queries in retry logic for connection errors
- Log when connection errors cause dedupe bypass

### Step 3: Update core/trade_tracker.py with Error Handling
- Wrap DB operations in try/except
- Add graceful fallback

## Implementation Status
- [ ] Step 1: Enhanced pool monitoring in db/session.py
- [ ] Step 2: Retry logic in db/pg_features.py  
- [ ] Step 3: Error handling in core/trade_tracker.py

---
Generated: 2025-01-XX
