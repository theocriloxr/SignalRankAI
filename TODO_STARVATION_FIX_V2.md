# TODO: Systemic Data Starvation Fixes V2

## Summary

All key fixes have been implemented to resolve the "generated_signals=0" starvation issue.

## Implementation Status

### Step 1: Aggressive Forward-Fill in data/fetcher.py ✓ COMPLETED
- [x] Short-circuit provider chain after 2 consecutive failures 
- [x] Enhanced error logging with exact error type/message
- [x] Forward-fill TTL at 1800s (30 min) - was already implemented
- [x] Degraded mode min candles = 10 - was already implemented

### Step 2: Enhanced Cache Backfill ✓ COMPLETED
- [x] Short-circuit via fetcher.py changes above
- [x] Enhanced error logging via fetcher.py changes above

### Step 3: Emergency Macro Fallback ✓ ALREADY IMPLEMENTED
- [x] Uses _macro_fallback_cache in engine/core.py

## Changes Made

### data/fetcher.py

Added short-circuit logic to three provider functions:
1. `_fetch_crypto_multi_provider` - tracks consecutive failures, short-circuits after 2
2. `_fetch_fx_multi_provider` - tracks consecutive failures, short-circuits after 2  
3. `_fetch_stock_multi_provider` - tracks consecutive failures, short-circuits after 2

Each function now:
- Tracks `consecutive_failures` counter
- Logs warning with provider name, exact error type, and message
- Breaks out of loop after 2 consecutive failures
- Logs "short-circuited" message for diagnostics

## How This Fixes Starvation

Previously: The engine tried all 20+ provider retries per asset, causing delays and eventual failure

Now: After 2 consecutive provider failures, the system:
1. Short-circuits to fallback cache faster
2. Uses forward-filled cached data (up to 30 min old)
3. Accepts degraded mode (10 candles minimum vs 20)
4. Generates signals instead of starving

This ensures signals are generated even when external APIs rate-limit or fail, preventing the "generated_signals=0" issue.
