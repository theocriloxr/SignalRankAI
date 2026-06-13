# Signal Generation Fix - Analysis & Plan

## Log Comparison Summary

### BEFORE (Working - June 9)
```
generated_signals=219 normalized=219 consensus=60 selected=51 unique=51 
strict_candidates=28 risk_passed=28 final_signals=0 stored=0 skipped_open_limit_asset=0 ...
```

### AFTER (Broken - June 12)
```
generated_signals=0 max_score=None max_score_pre_threshold=None strategy_signals=0 normalized=0 
consensus=0 selected=0 unique=0 strict_candidates=0 risk_passed=0 final_signals=0 ...
```

---

## Root Cause Analysis

### The engine uses multiple gates/stages:

1. **Candles check** (line ~1070) - Already implemented
2. **Indicators check** (line ~1078) - Already implemented
3. **Strategy generation** - `run_all_strategies()` returns empty
4. **Consensus filter** - Removes all signals
5. **Strict candidates** - Validation failures
6. **Risk/ML gates**
7. **Final scoring**

### Key diagnostic needed:
- The logs show `generated_signals=0` which means strategies returned ZERO outputs
- This happens when: no valid candles OR no valid indicators

---

## Implemented Fixes

### 1. INDICATOR STARVATION Check (LINES 1078-1134)
Already in core.py - checks for RSI, MACD hist, EMA fast/slow validity

### 2. DATA STARVATION Check (LINES ~1070-1080)
Already in core.py - checks for candles

---

## What ISN'T Fixed Yet?

Need to add more diagnostic logging to identify WHICH specific gate is failing:

1. **Provider diagnostics** - Which data provider returned empty/no-data for each asset
2. **Indicator calculation failures** - Whether indicators.py calculate_indicators() is failing silently
3. **Strategy-specific diagnostics** - Which strategy is returning empty and WHY

---

## Action Items

### Step 1: Add Enhanced Provider Diagnostics
Add logging to show WHICH provider succeeded/failed for each asset:

```python
# In _fetch_market_data_for_assets() around line ~650
for asset, data in results:
    providers_used = []
    for tf_name, tf_data in data.items():
        provider = tf_data.get('source', 'unknown')
        if provider:
            providers_used.append(provider)
    logger.info(f"[engine] Asset {asset}: providers={set(providers_used)}")
```

### Step 2: Add Strategy Diagnostics  
Log indicator values BEFORE calling strategies:

```python
# Around line ~1180, before run_all_strategies
ind = (market_data.get(list(market_data.keys())[0]) or {}).get('indicators', {})
logger.info(f"[engine] Pre-strategy indicators for {asset}: {ind}")
```

### Step 3: Add Data Provider Verification
Verify which providers work from environment:

```python
# Check provider status at startup
from data.providers import get_unhealthy_providers
unhealthy = get_unhealthy_providers()
logger.warning(f"[engine] UNHEALTHY PROVIDERS: {unhealthy}")
```

---

## Files to Check

1. **data/providers.py** - Check provider configuration
2. **data/market_data.py** - Check fetch function
3. **data/indicators.py** - Check indicator calculation
4. **strategies/** - Check strategy functions
5. **config.py** - Check environment variables

---

## Questions to Resolve

1. Are any data providers returning empty data for all assets?
2. Are indicators being calculated correctly?  
3. Are strategies receiving valid indicator dictionaries?
4. Has data source changed between June 9 and June 12?
5. Are there any environment variable changes affecting data providers?

---

## Next Steps

1. Run diagnostic script to check provider health
2. Add more verbose logging to engine/core.py
3. Verify data provider URLs haven't changed
