# SignalRankAI - Task Fixes Integration Guide

This guide shows how to integrate all 5 task fixes into the system.

---

## Task 1: Fix Monolith Event Loop

**Status**: Already implemented in `railway_main.py` using asyncio.create_task() for concurrent execution of Telegram Bot, Redis Queue Consumer, and Realtime Outcome Tracker.

**Additional Fix**: Create async wrapper for fetcher.py to convert synchronous requests:

```python
# Add to data/fetcher.py or create data/async_fetch.py
import aiohttp

async def async_get_candles(asset, timeframe):
    """Async wrapper using aiohttp."""
    try:
        asset_type = get_asset_type(asset)
        use_multi_provider = os.getenv("USE_MULTI_PROVIDER_DATA", "true").lower() == "true"
        
        if not use_multi_provider:
            return await asyncio.to_thread(get_candles, asset, timeframe)
        
        # Use async providers from connector_registry
        from data.connector_registry import get_async_providers_for_asset
        provs = get_async_providers_for_asset(asset_type)
        
        for name, fetch_fn in provs:
            try:
                candles = await asyncio.wait_for(
                    fetch_fn(asset, timeframe, timeout=2.5),
                    timeout=2.5,
                )
                if candles and len(candles) >= 20:
                    return candles
            except Exception:
                continue
        
        return []
    except Exception:
        return []
```

---

## Task 2: Fix Telegram Inline Buttons (Timeout/Loading Bug)

**File**: `signalrank_telegram/callback_handlers.py`

**Integration** (add to bot.py):

```python
from signalrank_telegram.callback_handlers import create_global_callback_handler

# In run_bot() after building application:
application.add_handler(create_global_callback_handler())
```

---

## Task 3: Fix "Invalid TP Structure" ML Rejections

**File**: `engine/signal_validators.py`

**Integration** (in engine pipeline):

```python
from engine.signal_validators import normalize_signal_for_ml

# In signal validation pipeline, BEFORE ML gate:
def validate_signal_for_ml_pipeline(signal):
    # Normalize TP structure first
    signal = normalize_signal_for_ml(signal)
    
    # Then continue to ML gate...
    # ml_prob = run_ml_inference(signal)
    return signal
```

---

## Task 4: Fix Same-Signal Duplication

**File**: `engine/signal_dedup_strict.py`

**Integration** (in engine/core.py before signal creation):

```python
from engine.signal_dedup_strict import is_signal_duplicate_strict

async def check_duplicate_before_signal(asset, timeframe, direction):
    """Check duplicate before creating signal."""
    is_dup, existing_id = await is_signal_duplicate_strict(
        asset=asset,
        timeframe=timeframe,
        direction=direction,
        lookback_hours=12,  # 12-hour window
    )
    
    if is_dup:
        logger.warning(f"Duplicate signal blocked: {asset} {timeframe} {direction}")
        return True  # Block signal
    
    return False
```

Or for batch processing:

```python
from engine.signal_dedup_strict import dedupe_signals_batch_strict

async def process_signals_deduplicated(signals):
    deduped = await dedupe_signals_batch_strict(signals)
    return deduped
```

---

## Task 5: Fix "Ghost Prices" & Asset Routing

**File**: `data/get_live_price.py`

**Integration** (in realtime_outcome_tracker.py):

```python
from data.get_live_price import get_live_price

# Replace _get_live_price function:
async def _fetch_live_price(symbol: str) -> Optional[float]:
    return await get_live_price(symbol)
```

Or directly in your code:

```python
from data.get_live_price import get_live_price, get_circuit_breaker_status

# Fetch live price with circuit breaker and strict routing
price = await get_live_price("BTCUSDT")

# Check provider health
status = get_circuit_breaker_status()
# Returns: {"binance": {"open": False, "failures": 0, ...}, ...}
```

---

## Quick Summary

| Task | File | Import | Key Function |
|------|------|-------|---------|
| 1 | railway_main.py | (existing) | asyncio.create_task() |
| 2 | callback_handlers.py | create_global_callback_handler() | query.answer() IMMEDIATE |
| 3 | signal_validators.py | normalize_signal_for_ml() | TP list conversion |
| 4 | signal_dedup_strict.py | is_signal_duplicate_strict() | (Asset,TF,Dir) strict |
| 5 | get_live_price.py | get_live_price() | Circuit Breaker + routing |

---

## Testing Each Fix

```python
# Test Task 3 - TP Normalization
from engine.signal_validators import normalize_tp_structure
signal = {"asset": "BTCUSDT", "direction": "long", "entry": 50000, "stop_loss": 49000, "take_profit": 52000}
normalized = normalize_tp_structure(signal)
# take_profit should now be [52000]

# Test Task 4 - Strict Dedup
from engine.signal_dedup_strict import is_signal_duplicate_strict
is_dup, existing = await is_signal_duplicate_strict("BTCUSDT", "1h", "long")
# Returns (bool, signal_id or None)

# Test Task 5 - Price Fetch
from data.get_live_price import get_live_price
price = await get_live_price("BTCUSDT")
# Returns price with correct provider routing

# Check circuit breakers
from data.get_live_price import get_circuit_breaker_status
status = get_circuit_breaker_status()
```

---

## Rollout Order

1. **First**: Deploy Task 3 (TP normalization) - blocks ML rejections
2. **Second**: Deploy Task 4 (dedup strict) - prevents duplicates  
3. **Third**: Deploy Task 5 (price routing) - fixes ghost prices
4. **Fourth**: Deploy Task 2 (callbacks) - fixes button timeouts
5. **Fifth**: Deploy Task 1 (async fetcher) - improves performance

Each task can be deployed independently.
