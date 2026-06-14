# Market Data Fix - Detailed Implementation Plan

## Problem Statement
The SignalRankAI engine is generating `generated_signals=0` and `stored=0` because all market data providers are returning empty candle data.

```
[DEBUG][outcome] Evaluating signal f72af6ed-5e99-447e-83f1-d0b9d8002426 AAVEUSDT 1h long
[DEBUG][outcome] No candles found for AAVEUSDT 1h
[DEBUG][outcome] Evaluating signal c8e96f54-7439-46d4-a5ad-879147012a0d ETHUSDT 1h long
[DEBUG][outcome] No candles found for ETHUSDT 1h
... repeated for all 20 assets
```

## Root Cause
**ALL data providers are failing silently without proper error diagnostics.** The multi-provider fallback chain returns empty lists, which causes:
1. No candles → No indicators → No strategy signals → 0 signals stored

## Solution Overview
Add aggressive diagnostic logging + emergency fallback + ticker format fixes + retry logic.

## Implementation Steps

### Step 1: Fix Ticker Format Mismatches (data/market_data.py)
CRITICAL: Many providers fail because ticker format is wrong. Add format conversion:

```python
# Add to _fetch_via_yfinance():
# BTCUSDT → BTC-USD (for crypto on yfinance)
# ETHUSDT → ETH-USD
# AAVEUSDT → AAVE-USD
```

### Step 2: Add Aggressive YFinance Fallback (data/market_data.py)
YFinance is the most reliable free provider. Make it primary fallback:

```python
# Enhance yfinance with more aggressive retries
# Add delay between requests to avoid rate limits
# Try multiple ticker formats
```

### Step 3: Add Comprehensive Diagnostic Logging (data/fetcher.py)
Add error tracking to diagnose provider failures:

```python
# Log EVERY provider call with success/failure
# Log specific error messages (429, timeout, empty)
# Track which provider is "winning" per asset
```

### Step 4: Add Emergency Cache Forward-Fill (data/fetcher.py)
Make forward-fill cache work even in emergency mode:

```python
# FIX: Accept ANY cached data as last resort
# Even 1 candle is better than 0
# Just log warning, don't fail silently
```

### Step 5: Add Scheduled Data Warmup (worker/worker.py) 
Add a background job to pre-fetch data every 5 minutes:

```python
# Prefetch common pairs (BTC, ETH, etc.)
# Keep 1h candles warm in Postgres cache
# This prevents cold-start starvation
```

## Files to Modify

1. **data/market_data.py** - YFinance ticker format + fallback improvements
2. **data/fetcher.py** - Diagnostic logging + emergency forward-fill  
3. **worker/worker.py** - Add data warmup job
4. **engine/core.py** - Add verbose diagnostic for empty market data

## Implementation Order

1. First: Add ticker format fix (quick win)
2. Second: Add diagnostic logging (critical)
3. Third: Emergency fallback improvements
4. Fourth: Test and validate

## Verification

Check logs for:
- `[data] crypto_provider=xxx` successful logs
- `[data] fx_provider=xxx` successful logs
- `[fetcher] Insufficient candles` warnings reduced

Expected result after fix:
- `generated_signals > 0` per cycle
- `max_score > 0` in output
- `stored > 0` signals persisted

## Side Note: ML Training Log Level
The ML module outputs training metrics at ERROR level:
```
[ml.train_model] Confusion Matrix ...
[ml.train_model] Accuracy=83.7%
```
This should be INFO level instead - add to logging config.
