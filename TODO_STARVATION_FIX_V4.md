# Data Starvation Fix V4 - Implementation Summary

## Problem Analysis
From logs:
1. Binance geo-blocked on Railway (US-based IPs)
2. Falls back to CryptoCompare
3. CryptoCompare fails to provide enough candles (requires 20+)
4. Engine requires 20 candles minimum → signals = 0

## Implementation Completed

### Step 1: DB Connection Pooling (CRITICAL - COMPLETED ✓)
- [x] Fixed db/session.py to enable connection pooling by default
  - Changed NullPool to only activate when `DB_USE_NULLPOOL=true` explicitly
  - Better default: pool_size=5, max_overflow=3 (unless Railway capped)

### Step 2: Degraded Mode Threshold (CRITICAL - COMPLETED ✓)
- [x] Fixed data/fetcher.py - all providers now use degraded mode threshold
  - Changed minimum from 20 to 5 candles (`_get_degraded_mode_min_candles()`)
  - Applied to: crypto, fx, stock, and async providers
  - Added forward-fill fallback before complete failure

### Step 3: Async Provider Fallback (COMPLETED ✓)
- [x] Fixed async_get_candles function
  - Now uses degraded mode (5 candles instead of 20)
  - Added forward-fill cache fallback as last resort

## What The Fix Does:
1. **Reduces candle requirement from 20 → 5** - Providers now only need 5 candles to succeed
2. **Enables proper DB connection pooling** - Better performance on Railway
3. **Better forward-fill** - Uses cached data as last resort before failure
4. **Short-circuit on 2 failures** - Prevents long waits during outages

## To Deploy:
1. Commit changes to GitHub
2. Railway auto-deploys
3. Watch logs for "Insufficient candles" warnings (should decrease)
4. Verify `generated_signals > 0`

## Related Files Modified:
- db/session.py - Connection pooling fix
- data/fetcher.py - Degraded mode fix (all provider functions)
