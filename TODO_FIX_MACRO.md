# Macro Data Fix Plan

## Task
Fix Polygon rate-limiting (429 errors) and TwelveData API configuration that causes strategy_signals=0

## Steps

### Step 1: Fix Polygon Rate-Limiting in _fetch_macro_snapshot()
- Add 2-3 second delay between macro data fetches
- Location: engine/core.py, _fetch_macro_snapshot() function
- Add jittered delay to prevent 429 errors

### Step 2: Fix DXY Ticker Format for TwelveData
- DXY often needs different ticker format in TwelveData
- Try "USDX", "DX-Y", "DXY" formats sequentially

### Step 3: Add Data Fallback Rule
- If global indices fail to fetch, use cached database values
- Cache these in Redis for fallback

## Files to Edit
- engine/core.py (main fix location)
- data/providers.py (if needed for ticker formatting)

## Notes
- This fix will restore strategy_signals from 0 back to active state
- Must verify TwelveData API permissions for index symbols
