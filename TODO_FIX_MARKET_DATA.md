# Market Data Fix Plan - COMPLETED

## Task
Fix the root cause: market data provider chain failure causing strategy_signals=0, stored=0

## Root Cause Analysis

1. **Primary issue**: yfinance ticker format mismatch
   - For assets like AAVEUSDT, ETHUSDT, BNBUSDT - yfinance doesn't recognize the USDT format
   - yfinance expects different formats like "AAVE-USD", "AAVE=X", or just "AAVE"
2. **Fallback was insufficient**: When one ticker format failed, no retry was attempted

## Fix Applied

### 1. Added `_get_yfinance_symbol_variants()` in data/market_data.py
Generates multiple ticker format variants to try:
- For USDT pairs (crypto): tries `BASE-USD`, `BASE=X`, `BASE`, `BASEUSDT`
- For BUSD pairs: tries `BASE-USD`, `BASE=X`, `BASE`
- For USDC pairs: tries `BASE-USD`, `BASE=X`, `BASE`
- For FX pairs: tries `EURUSD=X`, `EUR-USD`, `EURUSD`

### 2. Updated `_fetch_via_yfinance()` in data/market_data.py
Now iterates through all variants until successful data is retrieved:
- Logs each attempt for diagnostics
- Returns first successful result
- Falls back to next variant on empty/exception

## Files Modified
- `data/market_data.py` - Added symbol variants logic + updated fetch function

## Verification
After this fix, you should see logs like:
```
[yfinance] AAVE-USD returned empty for AAVEUSDT, trying next variant
[yfinance] success: AAVEUSDT -> AAVE-USD got 100 candles
```

If this doesn't fully resolve the issue, the next fallback chain will be used:
1. yfinance (with new retry logic)
2. Postgres cache
3. REST providers (Binance/Bybit/CryptoCompare)
