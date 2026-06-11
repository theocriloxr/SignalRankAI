# TODO: Systemic Data Starvation Fixes

## Task List
- [x] FIX 1: Move Redis counter to top of asset loop (engine/core.py) - COMPLETED
- [x] FIX 2: Add DATA STARVATION warning logging (engine/core.py) - COMPLETED
- [x] FIX 3: Increase CoinGecko days parameter (data/providers.py) - COMPLETED
- [x] FIX 4: Add macro fallback bypass (engine/core.py) - COMPLETED (already existed in _macro_fallback_cache)

## Status
COMPLETED - All fixes implemented

## Summary of Changes Made

### Fix 1: Move Redis counter to top of asset loop (engine/core.py)
- Moved `global_stats_instance.increment_scanned(1)` to execute BEFORE data validation check fails
- This ensures the dashboard pulse counter increments even for assets that return empty candles
- Previously counter only incremented after successful regime detection, which skipped failed assets

### Fix 2: Add DATA STARVATION warning logging (engine/core.py)
- Added explicit `logger.warning("[engine][DATA STARVATION] {asset} returned empty candles...")` 
- This diagnostic logging makes it immediately visible which API providers are failing
- Helps identify exactly why strategy_signals=0

### Fix 3: Increase CoinGecko days parameter (data/providers.py)
- Changed `fetch_coingecko_market_chart()` default from days=7 to days=30
- Changed waterfall fallback from days=7 to days=30  
- 30 days × 24h = 720 candles - enough for 200-period EMAs
- Previously only 84 candles were fetched, causing NaN in technical indicators

### Fix 4: Macro fallback bypass (engine/core.py)
- Already implemented via `_macro_fallback_cache` in `_fetch_macro_snapshot()`
- Caches last successful macro values for fallback when providers fail
- Allows bot to operate with neutral macro scores when data is unavailable
