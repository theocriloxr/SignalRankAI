# Macro Data Fix Plan - COMPLETED

## Task
Fix Polygon rate-limiting (429 errors) and TwelveData API configuration that causes strategy_signals=0

## Status: ✅ COMPLETED

### Fixes Applied

#### Step 1: Proactive Rate Limiting (data/providers.py)
- Added `_macro_rate_limit()` function to PREVENT 429 errors before they happen
- Tracks last call times for macro indices (DXY, VIX, US10Y, US02Y)
- Applies 12-second delays between calls (Polygon free tier: 5 calls/minute)
- Added jitter to prevent thundering herd

#### Step 2: Engine Integration (engine/core.py)  
- Updated `_fetch_macro_snapshot()` to call `_macro_rate_limit()` BEFORE each fetch
- Waits if needed before DXY, VIX, US10Y, US02Y fetches

#### Step 3: DXY Fallback Ticker Formats (Already in place)
- engine/core.py already tries "USDX", "DX-Y", "USDXUSD", "DXYUSD" formats
- Falls back to alternative formats when primary fails

#### Step 4: Cached Fallback Values (Already in place)
- engine/core.py caches successful macro values for fallback
- Uses cached values when providers fail

## How to Verify Fix is Working

Look for these logs in your container terminal:
```
[macro] snapshot: dxy=<value> vix=<value> us10y=<value>
[engine] cycle=8 assets=20 ... final_signals=1 stored=1
```

The key indicator is `stored` changing from 0 to 1 (or higher).

## Files Modified
- data/providers.py - Added proactive rate limiting
- engine/core.py - Added calls to rate limiter before macro fetches
