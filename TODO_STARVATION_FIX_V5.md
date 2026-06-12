# STARVATION_FIX_V5 Implementation Plan

## Summary of Fixes Required

Based on diagnostics, the system is outputting zero signals (`generated_signals=0`, `strategy_signals=0`) despite:
- Engine not crashing
- Database healthy
- ML model training successfully

The root cause analysis identified THREE main issues:

### 1. Ticker Symbol Mismatch (The Silent Killer)
**Problem**: yfinance requires `BTC-USD` format, but the system passes `BTC/USDT`. This causes silent failures returning 0 candles.

**Status**: ✅ ALREADY FIXED
- `yfinance_adapter.py` uses `format_symbol_for_yahoo()` from `data/symbol_formatter.py`
- Properly converts `BTCUSDT` -> `BTC-USD`

### 2. Strategy Indicator Minimums (The Math Problem)
**Problem**: Strategies mathematically require at least 50+ candles (e.g., EMA 50, RSI 14). If only 5-10 candles provided, indicators calculate as NaN, causing strategies to fail silently.

**Status**: ✅ ALREADY FIXED
- The system fetches 60-day periods by default
- This provides sufficient candles for all indicator calculations

### 3. Strict Confluence and Risk Filters
**Problem**: Some strategies wrap generation inside strict market regime filters or risk conditions that cause them to output 0 signals during certain market conditions.

**Status**: Need to verify configuration

## Implementation Completed

### Files Updated

1. **data/fetcher_router.py** ✅
   - Added comprehensive fallback chains:
     - Crypto: Binance -> KuCoin -> CryptoCompare -> Tiingo -> yfinance
     - Stocks: Tiingo -> Twelve Data -> FMP -> yfinance
     - Forex: Twelve Data -> Tiingo -> FCS -> yfinance
     - Commodities: Twelve Data -> Tiingo -> yfinance

2. **data/connectors/** (All adapters already exist)
   - kucoin_adapter.py ✅
   - tiingo_adapter.py ✅
   - twelvedata_adapter.py ✅
   - fmp_adapter.py ✅
   - fcs_adapter.py ✅

3. **data/symbol_formatter.py** ✅
   - `format_symbol_for_yahoo()` properly handles ticker translation
   - `normalize_crypto_symbol()` for Binance format conversion

4. **data/connectors/yfinance_adapter.py** ✅
   - Uses dynamic symbol formatter
   - Fetches 60-day periods (sufficient for all indicators)

## Logging Added to Engine

The following diagnostic logging exists in `engine/core.py`:
```python
# FIX 2: Add DATA STARVATION warning logging
if not has_candles:
    logger.warning(f"[engine][DATA STARVATION] {asset} returned empty candles...")

if _candle_count < 50:
    logger.warning(f"⚠️ [engine][DIAGNOSTIC] {asset}: Data provider only returned {_candle_count} candles!")
```

## Environment Variables for API Keys

Required for enhanced fallback chain:
- `TIINGO_API_KEY` - Tiingo free tier (500 req/hr)
- `TWELVEDATA_API_KEY` - Twelve Data free tier (800/day)
- `FMP_API_KEY` - Financial Modeling Prep free tier (250/day)

## Verification Steps

After deployment, check Railway logs for:
1. `[engine][DIAGNOSTIC] {asset}: Have {N} candles before strategy run - OK` = Data OK
2. `[router] provider={name} symbol={symbol} class={class} candles={N}` = Provider working
3. Warning messages indicate which component is failing

## Next Steps

1. Set API keys in Railway dashboard:
   - TIINGO_API_KEY
   - TWELVEDATA_API_KEY
   - FMP_API_KEY

2. Monitor logs after redeployment

3. If still seeing issues:
   - Check specific warning messages
   - Verify strategy configuration
   - Check market regime settings
