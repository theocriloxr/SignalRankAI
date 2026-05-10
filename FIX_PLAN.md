# SignalRankAI Fix Plan

## Issues to Fix

### 1. CRITICAL: Score Threshold Too High
**Problem**: Signals score ~62.68 max, but PREMIUM_SCORE_THRESHOLD defaults to 70
**Affected**: All signals blocked at final gate

**Fix**: 
- Lower threshold to 55 (closer to ML_PROB_THRESHOLD default of 0.55)
- Or make it dynamic based on market conditions

### 2. DB Connection Leak
**Problem**: SAWarning about non-checked-in connection
**Location**: engine/core.py around line 2160

**Fix**: Ensure context managers or explicit close()

### 3. Provider Fallbacks
**Problem**: Binance disabled, TwelveData/Polygon rate limited

**Fix**: 
- Ensure CryptoCompare works as fallback
- Add Yahoo Finance fallback

## Implementation Steps

### Step 1: Adjust Score Threshold
File: `engine/core.py`
- Change DEFAULT_MIN_SCORE_THRESHOLD from 70 to 55
- Or adjust dynamically based on average signal quality

### Step 2: Fix DB Connection Leak
File: `engine/core.py`
- Wrap DB operations in proper context managers
- Use async with get_session() properly

### Step 3: Provider Fallbacks
File: `data/fetcher.py`
- Ensure CryptoCompare is primary fallback
- Add more robust error handling

## Files to Modify
1. engine/core.py - Score threshold
2. engine/core.py - DB connection handling
3. data/fetcher.py - Provider fallbacks
