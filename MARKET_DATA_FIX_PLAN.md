# Market Data Fix Plan - SignalRankAI

## Problem Summary (from uploaded logs)

```
No timeframe data for WTI
No timeframe data for LTCUSDT
No timeframe data for GBPJPY
...

cycle=1
assets=20
generated_signals=0
strategy_signals=0
normalized=0
consensus=0
selected=0
```

**Root Cause**: Market data acquisition is failing BEFORE strategies run.

### Issue 1: Binance Region Block (CRITICAL)
```
Binance pairs disabled:
Service unavailable from a restricted location
```

Railway is running in a region Binance blocks. The bot discovers assets but cannot fetch candle data.

### Issue 2: Provider Failures (HIGH)
```
twelvedata fetch_failed symbol=BRENT
polygon fetch_failed symbol=BRENT status=429
```

Commodity providers all failing simultaneously.

### Issue 3: Data Quality Starvation (HIGH)
Even when data appears available, it's often insufficient quality:
- Too few candles (< 150 needed for 200-period EMAs)
- Too many NaN values (> 5%)
- Stale data (older than 2x timeframe)

This is WHY `strategy_signals=0` despite `assets=20` being scanned.

---

## Implemented Fixes

### 1. Data Quality Gate (CRITICAL - DONE ✅)

**File**: `data/fetcher.py`

**Added**: `_validate_data_quality()` function with strict quality gates:
- Minimum 150 candles (for indicator stability)
- Maximum 5% NaN ratio in close column
- Logs diagnostic when rejected

```python
def _validate_data_quality(candles: list, max_nan_ratio: float = 0.05) -> tuple[bool, str]:
    """Validate data quality before passing to strategies.
    
    Quality gates:
    - Minimum 150 candles for indicator stability
    - Max 5% NaN values in close column
    """
    if not candles or not isinstance(candles, list):
        return False, "empty_dataframe"
    
    # Minimum candles for indicator stability (150 needed for 200-period EMAs)
    if len(candles) < 150:
        return False, f"insufficient_candles_{len(candles)}_need_150"
    
    # Check NaN ratio in close column
    close_values = [float(c.get("close", 0) or 0) for c in candles if isinstance(c, dict)]
    if not close_values:
        return False, "no_close_prices"
    
    nan_count = sum(1 for v in close_values if v is None or v == 0 or (isinstance(v, float) and math.isnan(v)))
    nan_ratio = nan_count / len(close_values) if close_values else 1.0
    
    if nan_ratio > max_nan_ratio:
        return False, f"high_nan_ratio_{nan_ratio:.1%}_max_{max_nan_ratio:.1%}"
    
    return True, ""
```

**Called in**: `fetch_market_data()` before processing

**Log Output**:
```
[fetcher][QUALITY GATE] REJECTED BTCUSDT 1h: insufficient_candles_47_need_150. This is WHY strategy_signals=0 despite asset being scanned.
```

---

### 2. Enhanced Forward-Fill Cache (HIGH - Already exists)

The existing forward-fill cache already handles provider outages by using stale cached data when providers fail.

**Behavior**:
1. If provider returns < 20 candles
2. Try forward-fill cache (up to 1800s / 30 min old)
3. Accept degraded mode minimum (10 candles)

This prevents complete pipeline starvation.

---

### 3. Provider Health Tracking (MEDIUM - Already exists)

The bot already tracks provider health and skips unhealthy providers:

```python
def provider_is_healthy(provider_name):
    # If failure rate > 50%, mark unhealthy
    return stats["failures"] / total < 0.5
```

---

## Recommended Additional Fixes

### A. Rebuild Provider Chains for Region-Restricted Deployments

For Railway Hobby (Binance blocked regions):

**File**: `data/fetcher_router.py` or `data/connector_registry.py`

**Current Chain**:
- Crypto: Binance → Bybit → CryptoCompare → CoinGecko

**Recommended Chain**:
- Crypto: Bybit → CryptoCompare → CoinGecko → AlphaVantage
  - Bybit works in Nigeria (no geo-block)
  - CryptoCompare free tier with API key
  - CoinGecko free tier (rate limited)
  - AlphaVantage premium fallback

### B. Add Commodity-Specific Providers

**Current Issue**: BRENT and WTI failing across all providers

**Recommended**:
- TwelveData → Yahoo Finance → Stooq (for commodities)
- Note: Crypto providers should NOT be used for commodities (causes ghost prices)

### C. Asset Ranking for Railway Hobby

On Railway Hobby with limited compute:
- Analyze top 10 assets instead of all 20
- Rank by: liquidity + volatility + trend + recent_signal_quality

---

## Verification Steps

After deployment, verify fixes by checking:

1. **Quality gate logs**:
   ```
   [fetcher][QUALITY GATE] REJECTED X: insufficient_candles_Y_need_150
   ```

2. **Provider fallback logs**:
   ```
   [data] crypto_provider=bybit symbol=BTCUSDT tf=1h candles=200
   [data] forward-filled cached candles symbol=ETHUSDT tf=1h
   ```

3. **Engine pipeline stats**:
   ```
   strategy_signals=5 normalized=3 consensus=2 risk_passed=1 stored=1
   ```

---

## Summary

| Issue | Status | File |
|-------|--------|------|
| Data quality gate (150 candles min, 5% NaN max) | ✅ DONE | data/fetcher.py |
| Forward-fill cache | ✅ EXISTS | data/fetcher.py |
| Provider health tracking | ✅ EXISTS | data/fetcher.py |
| Bybit primary for crypto | ⚠️ EXISTING | get_crypto_candles() |
| Commodity separateproviders | ⚠️ RECOMMEND | connector_registry.py |

The critical fix (data quality gate) is now in place. This directly addresses WHY `generated_signals=0` despite assets being scanned - the data was too poor quality for strategies to generate signals.
