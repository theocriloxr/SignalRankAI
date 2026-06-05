# SignalRankAI Critical Fixes Integration Guide

This document describes the 5 critical fixes implemented to resolve the production issues.

---

## Task 1: Fix Event Loop Blocking

**Problem**: Synchronous blocking calls freeze the asyncio event loop.

### Solution Applied in railway_main.py
The existing `railway_main.py` already uses `asyncio.create_task()` for concurrent tasks:
- Engine loop: `_start_engine_loop_in_background()`
- Worker loop: `_start_worker_loop_in_background()`
- Bot webhook: `_start_telegram_bot()`

### Synchronous Request Fix in data/fetcher.py
The `get_candles()` function already uses synchronous `requests.get()` calls.
To fix this, we provide an async wrapper in `data/get_live_price.py`:

```python
# NEW: Use async price fetching
from data.get_live_price import get_live_price

# In async contexts:
price = await get_live_price("BTCUSDT")  # Non-blocking
```

---

## Task 2: Telegram Button Timeout Fix

**Problem**: Buttons show flashing loading icon and fail to execute.

### Solution: Global CallbackQueryHandler

**File**: `signalrank_telegram/callback_handlers.py`

**Integration in bot.py**:
```python
# Add after other handlers in run_bot()
from signalrank_telegram.callback_handlers import create_global_callback_handler
application.add_handler(create_global_callback_handler())
```

**Key fix**: The handler calls `await query.answer()` immediately to stop the loading circle.

---

## Task 3: Invalid TP Structure Fix

**Problem**: ML gates reject valid signals because TP is a single float instead of list.

### Solution: normalize_tp_structure()

**File**: `engine/signal_validators.py`

**How it works**:
1. Converts single float TP → [TP] list
2. Auto-calculates R:R array if TP is missing
3. Validates structure before ML gate

**Integration**:
```python
# In signal pipeline before ML gate
from engine.signal_validators import normalize_signal_for_ml

def process_signal(signal):
    # Normalize TP structure BEFORE ML gate
    signal = normalize_signal_for_ml(signal)
    
    # Now ML gate will accept it
    return signal
```

---

## Task 4: Same-Signal Duplication Fix

**Problem**: Same signal sent multiple times due to entry price differences.

### Solution: Strict Deduplication (Asset + Timeframe + Direction)

**File**: `engine/signal_dedup_strict.py`

**How it works**:
- Ignores entry price and timestamp
- Uses 12-hour lookback window
- Only matches on (Asset, Timeframe, Direction)

**Integration**:
```python
# In signal creation path
from engine.signal_dedup_strict import is_signal_duplicate_strict

async def create_signal_if_valid(signal):
    is_dup, existing = await is_signal_duplicate_strict(
        asset=signal["asset"],
        timeframe=signal["timeframe"],
        direction=signal["direction"],
        lookback_hours=12,  # Fixed 12-hour window
    )
    
    if is_dup:
        logger.warning(f"Duplicate signal blocked: {signal['asset']}")
        return None  # Don't create
    
    return signal  # Proceed with creation
```

---

## Task 5: Ghost Prices & Asset Routing Fix

**Problem**: Crypto routed to Polygon, stocks to Binance → null prices/timeouts.

### Solution: Strict Provider Routing + Circuit Breaker

**File**: `data/get_live_price.py`

**How it works**:
1. **Asset routing by suffix**:
   - `USDT/USDC/BUSD` → Binance/Bybit
   - Others → Yahoo/Polygon
2. **Circuit breaker** for each provider
3. **Automatic failover** on failure

**Integration**:
```python
# Replace direct price fetches with:
from data.get_live_price import get_live_price, get_provider_for_asset

# Get strict provider for asset
provider = get_provider_for_asset("BTCUSDT")  # Returns "binance"
provider = get_provider_for_asset("AAPL")     # Returns "yahoo"

# Get live price (with circuit breaker + failover)
price = await get_live_price("BTCUSDT")  # Returns float or None
```

---

## Summary Checklist

| Task | File | Integration |
|------|------|-------------|
| 1 - Event Loop | `railway_main.py` | Already using asyncio.create_task() |
| 1 - Sync Requests | `data/get_live_price.py` | Use async price functions |
| 2 - Telegram Buttons | `signalrank_telegram/callback_handlers.py` | Add CallbackQueryHandler to bot.py |
| 3 - TP Structure | `engine/signal_validators.py` | Call normalize_signal_for_ml() before ML |
| 4 - Duplication | `engine/signal_dedup_strict.py` | Call is_signal_duplicate_strict() before save |
| 5 - Ghost Prices | `data/get_live_price.py` | Use get_live_price() instead of direct |

---

## Testing Commands

```bash
# Test TP normalization
python -c "
from engine.signal_validators import normalize_signal_for_ml
signal = {'asset': 'BTCUSDT', 'direction': 'long', 'entry': 50000, 'stop_loss': 49000, 'take_profit': 51000}
result = normalize_signal_for_ml(signal)
print('TP normalized:', result.get('take_profit'))
"

# Test strict dedup
python -c "
import asyncio
from engine.signal_dedup_strict import is_signal_duplicate_strict
async def test():
    is_dup, _ = await is_signal_duplicate_strict('BTCUSDT', '1h', 'long')
    print('Is duplicate:', is_dup)
asyncio.run(test())
"

# Test provider routing
python -c "
from data.get_live_price import get_provider_for_asset
print('BTCUSDT ->', get_provider_for_asset('BTCUSDT'))
print('AAPL ->', get_provider_for_asset('AAPL'))
"

# Test live price
python -c "
import asyncio
from data.get_live_price import get_live_price
async def test():
    price = await get_live_price('BTCUSDT')
    print('Price:', price)
asyncio.run(test())
"
```

---

## Rollout Order

1. **Deploy** `data/get_live_price.py` (new circuit breaker + routing)
2. **Deploy** `engine/signal_validators.py` (TP normalization)
3. **Deploy** `engine/signal_dedup_strict.py` (strict dedup)
4. **Deploy** `signalrank_telegram/callback_handlers.py` (button fix)
5. **Update bot.py** to register callback handler
6. **Update signal pipeline** to call normalize_signal_for_ml() before ML gate
7. **Update deduplication** to use is_signal_duplicate_strict() before save
