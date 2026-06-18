# Market Data Fix Implementation Plan

## Problem Summary

From the logs:
- `generated_signals=0`
- `strategy_signals=0`
- `normalized=0`
- `consensus=0`
- `selected=0`

Root cause: Market data acquisition is failing BEFORE strategies run.

### Critical Issues:

1. **Binance geo-blocked on Railway**: Returns "Service unavailable from a restricted location"
2. **Commodity provider failures**: BRENT fails on TwelveData and Polygon (429)
3. **No data quality validation**: Empty dataframes passed to strategies

## Implementation Steps

### Step 1: Verify Provider Chains (CRITICAL)

Current `data/fetcher_router.py` already has:
- Crypto: Bybit -> KuCoin -> CryptoCompare -> CoinGecko -> Yahoo -> Binance
- FX: TwelveData -> AlphaVantage -> Yahoo -> Stooq
- Commodities: TwelveData -> Yahoo -> Stooq

**Action**: Verify Bybit connector exists and works

### Step 2: Add Data Quality Gates (HIGH)

In `engine/core.py`, before strategy execution, add:

```python
# Data quality validation
def validate_data_quality(market_data: dict, asset: str) -> tuple[bool, str]:
    """Validate data quality before strategy execution.
    
    Returns: (is_valid, reason)
    """
    # Check minimum candles
    min_candles = 150
    
    # Check NaN ratio
    max_nan_ratio = 0.05
    
    # Check data freshness
    max_age_seconds = {
        '1m': 120,
        '5m': 600,
        '15m': 1800,
        '1h': 7200,
        '4h': 28800,
        '1d': 172800,
    }
    
    for tf, tf_data in market_data.items():
        candles = tf_data.get('candles', [])
        if len(candles) < min_candles:
            return False, f"insufficient_candles:{len(candles)}"
        
        # Check NaN ratio in close prices
        closes = [c.get('close') for c in candles if c.get('close') is not None]
        nan_count = sum(1 for c in closes if c is None or (isinstance(c, float) and np.isnan(c)))
        if len(closes) > 0 and (nan_count / len(closes)) > max_nan_ratio:
            return False, f"high_nan_ratio:{nan_count/len(closes):.2%}"
        
        # Check freshness
        data_age = tf_data.get('data_age_seconds', 0)
        tf_interval = _TF_SECONDS.get(tf, 3600)
        max_age = tf_interval * 2  # 2x timeframe
        if data_age > max_age:
            return False, f"stale_data:{data_age:.0f}s > {max_age:.0f}s"
    
    return True, ""
```

### Step 3: Market Session Quality (HIGH)

In `data/market_hours.py`, add:

```python
def is_tradeable_now(asset: str) -> tuple[bool, str]:
    """Check if asset is tradeable NOW with good liquidity.
    
    Returns: (is_tradeable, reason)
    """
    # Check market open
    if not is_market_session_open(asset):
        return False, "market_closed"
    
    # Check if overnight session (poor liquidity for some assets)
    now = datetime.utcnow()
    hour = now.hour
    
    # XAUUSD: Poor liquidity 20:00-00:00 UTC
    if asset in ('XAUUSD', 'GOLD'):
        if hour >= 20 or hour < 0:
            return False, "poor_overnight_liquidity"
    
    # Commodities: Poor liquidity 22:00-02:00 UTC
    if is_commodity(asset):
        if hour >= 22 or hour < 2:
            return False, "poor_overnight_liquidity"
    
    return True, "tradeable"
```

### Step 4: Asset Ranking for Railway (MEDIUM)

Add auto-ranking based on:
- Liquidity score (volume)
- Volatility score (ATR)
- Trend score  
- Recent signal quality

```python
def rank_assets_for_analysis(assets: list[str], top_n: int = 10) -> list[str]:
    """Rank assets and return top N for analysis.
    
    On Railway, analyze less assets but with better data.
    """
    # Score each asset
    scores = []
    for asset in assets:
        score = (
            liquidity_score(asset) +
            volatility_score(asset) +
            trend_score(asset) +
            recent_signal_quality(asset)
        scores.append((asset, score))
    
    # Sort by score descending
    scores.sort(key=lambda x: x[1], reverse=True)
    
    # Return top N
    return [a for a, _ in scores[:top_n]]
```

## Files to Modify

1. `data/fetcher_router.py` - ✅ Already has good provider chains - verify
2. `engine/core.py` - Add data quality gates before strategy execution  
3. `data/market_hours.py` - Add is_tradeable_now()
4. `data/pair_discovery.py` - Add ranking function

## Testing

After implementation, verify:
1. Logs show provider fallback working
2. Data quality gates reject bad data with clear reason
3. Signals generated > 0
4. Asset analysis limited on Railway

## Monitoring

Add to engine logs:
- `data_quality_rejected`: count of assets rejected by quality gates
- `provider_fallbacks`: count of times each provider used as fallback
- `market_session_quality`: count of assets skipped due to poor liquidity
