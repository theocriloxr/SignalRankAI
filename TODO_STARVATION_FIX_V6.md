# TODO: Fix Exception Swallowing in Data Fetchers (STARVATION_FIX_V6)

## Problem
The data fetcher is encountering errors but swallowing them without logging the actual error details (traceback). This causes `strategy_signals=0` because the engine receives no data but there are no logs explaining why.

## Solution
Add detailed exception logging with `traceback.format_exc()` to expose the exact line of code that's failing.

## Files to Edit

### 1. data/fetcher_router.py
Need to fix:
- All provider adapter wrapper methods (`_get_bybit_candles`, `_get_binance_candles`, `_get_kucoin_candles`, etc.) - replace `except Exception: pass` with proper logging
- The `fetch_price` method - add traceback logging

### 2. data/fetcher.py  
Need to fix:
- `_fetch_crypto_multi_provider` - add traceback logging
- `_fetch_fx_multi_provider` - add traceback logging  
- `_fetch_stock_multi_provider` - add traceback logging

## Implementation Steps

Step 1: Add import for traceback to fetcher_router.py
Step 2: Fix each provider adapter method to log exceptions with traceback
Step 3: Fix fetch_price method to log full traceback
Step 4: Fix multi-provider functions in fetcher.py

## Expected Result
After deployment, logs will show:
```
❌ FATAL CRASH in binance adapter for BTCUSDT!
... (full traceback showing exact line that failed)
```

This will let us see exactly which adapter is broken and fix it quickly.
