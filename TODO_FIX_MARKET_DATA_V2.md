# Market Data Fix - Comprehensive Analysis

## Problem Summary
The engine reports generated_signals=0 and logs "No candles found for [symbol] [timeframe]". This means the market data fetching pipeline is not returning any price data.

## Root Cause Analysis (Based on Code Analysis)

### 1. Database Timeouts (FIX APPLIED)
- **Location**: db/session.py
- **Issue**: Default DB timeouts too short (15s connect, 45s command) for ML training
- **Fix Applied**: Increased to 60s connect, 120s command via environment variables

### 2. Market Data Fetching Chain
The data fetching works as follows:
1. **Entry Point**: `engine/core.py` → `_fetch_market_data_for_assets()`
2. **Data Fetch**: `data/market_data.py` → `fetch_market_data_cached()`  
3. **Provider Chain**: `data/fetcher.py` → `get_candles()` → multi-provider fallback
4. **Connectors**: `data/connectors/` → binance_adapter, yfinance_adapter, etc.
5. **Cache**: `db/market_cache.py` → PostgreSQL candle storage

### 3. Provider Priority (from data/fetcher.py)
- **Crypto**: Binance connector → Bybit → CryptoCompare → CoinGecko
- **FX**: OANDA → Yahoo → Polygon → TwelveData → TradingView
- **Stocks**: TwelveData → Polygon → Yahoo → AlphaVantage

### 4. Log Message Source
The debug message comes from data/fetcher.py around line 300+, which logs when all providers fail:
```
logger.warning("[data] crypto_fetched=none symbol=%s tf=%s (all providers failed)")
```

## Verification Steps

### Step 1: Check If Providers Are Responding
Test individual providers manually:
```bash
# Test Binance directly
curl "https://api.binance.com/api/v3/klines?symbol=BTCUSDT&interval=1h&limit=5"

# Test yfinance in Python
python -c "import yfinance; print(yfinance.Ticker('BTC-USD').history(period='1d'))"
```

### Step 2: Check Environment Variables
Ensure these are set:
- `USE_MULTI_PROVIDER_DATA=true`
- `YFINANCE_ENABLED=true` (fallback)
- `CRYPTOCOMPARE_API_KEY` (if using CryptoCompare)

### Step 3: Check Logs for Specific Errors
Look for these patterns in logs:
- `429` → Rate limited by provider
- `403` → Forbidden/IP blocked
- `connection refused` → Network issue
- `timeout` → Provider slow/unresponsive

## Proposed Fixes

### Fix 1: Enhanced Forward-Fill (Already Implemented)
- Location: data/fetcher.py
- Increased _get_forward_fill_ttl_seconds() to 1800s (30 min)
- Decreased _get_degraded_mode_min_candles() to 5 (was 20)

### Fix 2: More Aggressive Retry Logic
Add retry to provider chain after failures:

```python
# In data/fetcher.py - add near top of get_candles()
def get_candles(asset, timeframe):
    # Add early retry with exponential backoff
    for attempt in range(3):
        try:
            # existing code...
            return candles
        except Exception as e:
            if attempt < 2:
                wait = 2 ** attempt  # 1s, 2s
                time.sleep(wait)
                continue
    return []  # All attempts failed
```

### Fix 3: Better Error Messages
Add more diagnostic logging:

```python
# In data/fetcher.py - before returning empty
logger.error("[data] FATAL: All providers failed for %s %s. Errors: %s", 
    asset, timeframe, provider_errors)
```

### Fix 4: Environment Variables for Testing
Add to .env for faster debugging:
```
DEBUG_MARKET_DATA=true
YFINANCE_ENABLED=true
USE_MULTI_PROVIDER_DATA=true
MARKET_CACHE_MIN_CANDLES=10
DEGRADED_MODE_MIN_CANDLES=5
```

## Files Modified
- db/session.py ✓ (timeouts increased)
- data/fetcher.py (degraded mode already present)
- data/market_data.py (cache fallback already present)

## Next Steps
1. Apply additional fixes above
2. Test with isolated provider
3. Monitor logs for specific provider errors
4. Consider adding more fallback providers
