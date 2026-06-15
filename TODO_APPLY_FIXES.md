# SignalRankAI - Comprehensive Fix Implementation Plan

This document outlines all the fixes and improvements to be applied to the SignalRankAI codebase.

---

## Phase 1: Critical Fixes (Immediate Impact)

### 1. Fix audit_recent Import Error (signalrank_telegram/commands.py)
**Status**: PARTIALLY IMPLEMENTED
- `audit_recent_signals` function exists in services/gemini_ml.py
- `audit_recent` alias exists for backward compatibility
- Need to verify `/gemini_audit_command` uses correct import

**Action**: Verify commands.py imports and uses `audit_recent_signals`

---

### 2. Fix Max Score 100.0 (engine/core.py)
**Status**: NEEDS FIX
- Issue: Strict `>` operator blocks perfect scores
- Current: Uses `>` comparison
- Need: Use `>=` operator to let perfect scores through

**Action**: Replace threshold gate in Advanced Filters section:
```python
# Change from:
final_signals = [s for s in scored_signals if s.get('score', 0) > threshold]
# To:
final_signals = [s for s in scored_signals if s.get('score', 0) >= threshold]
```

---

### 3. Fix /signals Command Returning Empty (signalrank_telegram/commands.py)
**Status**: NEEDS FIX
- Issue: Only filters for "active" status
- Database uses "issued" or "open" for fresh trades

**Action**: Expand status filter in `signals_command`:
```python
active_unresolved = [
    s for s in all_signals 
    if str(s.get("status", "")).lower() in ["active", "issued", "open"] 
    and not s.get("resolved", False)
]
```

---

### 4. Fix PostgreSQL "Too Many Clients" (db/session.py)
**Status**: NEEDS FIX
- Current pool_size: 15 (too large)
- Need: pool_size=3, max_overflow=5

**Action**: Update `create_engine()` function:
```python
def create_engine() -> Optional[AsyncEngine]:
    url = get_database_url_or_none()
    if not url: return None

    # Severely limit pool to prevent asyncpg exhaustion
    return create_async_engine(
        url,
        pool_size=3,         # Reduced from 15
        max_overflow=5,      # Reduced from 15
        pool_timeout=30,
        pool_recycle=1800,
        pool_pre_ping=True
    )
```

---

### 5. Fix No Timeframe Data (Rate Limits) (engine/core.py)
**Status**: NEEDS FIX
- Issue: Requests fire simultaneously, causing 429 errors
- Need: Implement semaphore waterfall delay

**Action**: Add semaphore in `_fetch_market_data_for_assets`:
```python
async def _fetch_market_data_for_assets(asset_to_timeframes: Dict[str, List[str]]):
    concurrency = 3  # Strict tollbooth
    sem = asyncio.Semaphore(concurrency)
    import random
    
    async def _one(asset: str, tfs: List[str]):
        async with sem:
            await asyncio.sleep(1.5 + random.uniform(0.1, 0.5))
            try:
                data = await fetch_market_data_cached(asset, tfs)
                return asset, data
            except Exception:
                return asset, {}

    tasks = [_one(a, tfs) for a, tfs in (asset_to_timeframes or {}).items()]
    results = await asyncio.gather(*tasks, return_exceptions=False)
    return {asset: data for asset, data in results if data}
```

---

### 6. Fix Dynamic Threshold (ml/dynamic_threshold.py)
**Status**: PARTIALLY IMPLEMENTED
- Function exists but needs verification

**Action**: Verify function returns adjusted threshold:
```python
def adjust_threshold(base: float, current_auc: float, target: float) -> float:
    if current_auc < target:
        adjusted = base + (target - current_auc) * 0.3
    else:
        adjusted = base - (current_auc - target) * 0.2
        
    adjusted = max(0.35, min(0.85, adjusted))
    
    # FIX: Return the newly calculated 'adjusted' threshold, not 'base'
    return adjusted
```

---

### 7 & 8. Broker Map & Market Hours Support (utils/market_hours.py)
**Status**: ALREADY IMPLEMENTED
- data/market_hours.py has full implementation
- Need to verify imports in engine/core.py

**Action**: Verify `is_market_open` is imported in engine/core.py

---

## Phase 2: ML Stability Improvements

### 1. Add scale_pos_weight to XGBoost (ml/train_model.py)
**Status**: NEEDS IMPLEMENTATION
- Issue: High class imbalance causes model instability

**Action**: Add class imbalance calculation:
```python
# When initializing your XGBoost classifier, calculate the class imbalance:
num_winners = len(y_train[y_train == 1])
num_losers = len(y_train[y_train == 0])

# Prevent division by zero
if num_winners > 0:
    imbalance_ratio = num_losers / num_winners 
else:
    imbalance_ratio = 1.0

model = xgb.XGBClassifier(
    n_estimators=200,
    learning_rate=0.05,
    max_depth=5,
    scale_pos_weight=imbalance_ratio,  # <-- CRITICAL FIX FOR DRIFT
    random_state=42
)
```

---

### 2. EMA Smoothing for Dynamic Threshold (ml/dynamic_threshold.py)
**Status**: NEEDS IMPLEMENTATION
- Issue: Threshold swings violently

**Action**: Add EMA smoothing:
```python
# Smooth the threshold transitions so it doesn't violently swing your signal output
def adjust_threshold(base: float, current_auc: float, target: float, previous_threshold: float = None) -> float:
    # Calculate raw adjustment
    if current_auc < target:
        raw_adjusted = base + (target - current_auc) * 0.3
    else:
        raw_adjusted = base - (current_auc - target) * 0.2
        
    raw_adjusted = max(0.35, min(0.85, raw_adjusted))
    
    # If we have a previous threshold, apply a 30% EMA smoothing
    if previous_threshold is not None:
        smoothed_adjusted = (raw_adjusted * 0.3) + (previous_threshold * 0.7)
    else:
        smoothed_adjusted = raw_adjusted
        
    return smoothed_adjusted
```

---

## Phase 3: Trade Protection Features

### 1. Trade Correlation & Over-Exposure Blocker
**Status**: NEEDS IMPLEMENTATION

**Action**: Add to engine/core.py or engine/risk_manager.py:
```python
def check_portfolio_exposure(new_symbol: str, active_signals: list[dict], max_per_currency: int = 2) -> bool:
    """Prevents taking too many trades on the same base or quote currency."""
    
    # Extract base/quote (e.g. 'EUR' and 'USD' from 'EURUSD')
    if len(new_symbol) == 6:
        base, quote = new_symbol[:3], new_symbol[3:]
    else:
        return True # Skip non-FX for now, or adapt for crypto
        
    currency_counts = {base: 1, quote: 1}
    
    for sig in active_signals:
        sym = sig.get('asset', '')
        if len(sym) == 6:
            active_base, active_quote = sym[:3], sym[3:]
            currency_counts[active_base] = currency_counts.get(active_base, 0) + 1
            currency_counts[active_quote] = currency_counts.get(active_quote, 0) + 1
            
    # Reject if we already have too much exposure to either currency
    if currency_counts[base] > max_per_currency or currency_counts[quote] > max_per_currency:
        return False
        
    return True
```

---

### 2. Redis Market Data Caching Layer
**Status**: NEEDS IMPLEMENTATION

**Action**: Add to data/pipeline.py or market data fetcher:
```python
import json
# Use existing Redis instance

async def fetch_market_data_cached(symbol: str, timeframes: list[str]) -> dict:
    cache_key = f"market_data:{symbol}:{'-'.join(timeframes)}"
    
    # 1. Try to get from Redis first
    cached_data = await redis_global_stats.redis.get(cache_key)
    if cached_data:
        return json.loads(cached_data)
        
    # 2. If missing, fetch from API
    data = await actual_api_fetch_function(symbol, timeframes)
    
    # 3. Save to Redis with a TTL (Time To Live)
    if data:
        # Cache 1h/4h data for 15 minutes (900 seconds)
        await redis_global_stats.redis.setex(cache_key, 900, json.dumps(data))
        
    return data
```

---

## Phase 4: Infrastructure Improvements

### Railway Graceful Shutdown
**Status**: NEEDS IMPLEMENTATION

**Action**: Add to railway_main.py:
```python
import signal
import asyncio
import sys
from db.session import engine

async def graceful_shutdown(sig, loop):
    logger.warning(f"🛑 Received exit signal {sig.name}...")
    
    # 1. Stop Telegram Webhooks/Polling
    logger.info("Stopping Telegram Bot...")
    # await bot_application.stop()
    
    # 2. Close Database Connection Pool gracefully
    logger.info("Closing Database Engine connections...")
    if engine is not None:
        await engine.dispose()
        
    logger.info("Cleanup complete. Exiting.")
    loop.stop()
    sys.exit(0)

# Add this near the top of your main execution block
loop = asyncio.get_event_loop()
for sig in (signal.SIGINT, signal.SIGTERM):
    loop.add_signal_handler(sig, lambda s=sig: asyncio.create_task(graceful_shutdown(s, loop)))
```

---

## Implementation Order

1. **Immediate**: Issues 1-8 (Phase 1)
2. **Week 1**: ML Stability (Phase 2)  
3. **Week 2**: Trade Protection (Phase 3)
4. **Week 3**: Infrastructure (Phase 4)

---

## Files to Modify

1. `signalrank_telegram/commands.py` - Issues 1, 3
2. `engine/core.py` - Issues 2, 5, 7, 8
3. `db/session.py` - Issue 4
4. `ml/dynamic_threshold.py` - Issue 6, Phase 2
5. `ml/train_model.py` - Phase 2
6. `engine/risk_manager.py` - Phase 3
7. `data/pipeline.py` - Phase 3
8. `railway_main.py` - Phase 4
9. `data/market_hours.py` - Verify Issue 7&8
10. `services/gemini_ml.py` - Verify Issue 1

---

## Testing Checklist

- [ ] Import test for audit_recent_signals
- [ ] Score threshold accepts 100.0
- [ ] /signals shows issued/open signals
- [ ] DB pool doesn't exceed limits
- [ ] No 429 rate limit errors
- [ ] Dynamic threshold smoothly adjusts
- [ ] Market hours block closed markets
- [ ] ML model stable with scale_pos_weight
- [ ] Threshold uses EMA smoothing
- [ ] Portfolio exposure limited
- [ ] Redis cache reduces API calls
- [ ] Graceful shutdown on SIGTERM
