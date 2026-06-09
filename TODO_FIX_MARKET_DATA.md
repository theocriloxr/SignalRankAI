# Market Data Fix Plan - PART 2: Market Data Starvation

## Task
Fix the root cause: market data provider chain failure causing strategy_signals=0, stored=0

## Root Cause Analysis

1. **Primary providers failing**: Binance 429, Polygon empty returns, TwelveData errors
2. **Forward-fill cache not aggressive enough**
3. **Pipeline short-circuits when no data available**
4. **Result**: Assets skipped → no signals → stored=0

## Status: IN PROGRESS

### Fixes to Apply

#### Step 1: Aggressive Forward-Fill in data/fetcher.py
- Modify provider fallback to be more aggressive
- Forward-fill ANY cached data when providers fail
- Increase forward-fill TTL for degraded operation

#### Step 2: Enhanced Cache Backfill in data/market_data.py
- Accept 10 candles minimum (vs 20) during degraded mode
- Skip provider chain after 2 failures (not 20!)
- Better error logging for diagnostics

#### Step 3: Emergency Macro Fallback in engine/core.py
- Use last cached macro values when providers fail
- Prevent short-circuit with fallback values

## Files Modified
- data/fetcher.py - Aggressive forward-fill
- data/market_data.py - Enhanced cache fallback
- engine/core.py - Macro fallback enhancement
