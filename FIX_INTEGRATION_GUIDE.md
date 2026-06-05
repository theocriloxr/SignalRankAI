# SignalRankAI - Critical Fixes Integration Guide

This document explains how to integrate the 5 critical fixes implemented in this update.

## Files Created/Modified

### Task 1: Event Loop & Unblock System
- ✅ Already handled by existing `railway_main.py` - uses `asyncio.create_task()`

### Task 2: Telegram Inline Buttons (Timeout/Loading Bug)
**File**: `signalrank_telegram/callback_handlers.py`

**Integration**:
In `signalrank_telegram/bot.py`, add the handler:

```python
from signalrank_telegram.callback_handlers import create_global_callback_handler

# Add BEFORE other callback handlers
application.add_handler(create_global_callback_handler())
```

### Task 3: TP Structure (Single Float → List)
**File**: `engine/signal_validators.py`

**Integration**:
In the ML pipeline or signal generation, call normalize before ML gate:

```python
from engine.signal_validators import normalize_signal_for_ml

# Before passing to ML/Expectancy gates
signal = normalize_signal_for_ml(signal)
```

### Task 4: Same-Signal Duplication (12-hour strict dedup)
**File**: `engine/signal_dedup_strict.py`

**Integration**:
Replace or enhance existing dedup logic:

```python
from engine.signal_dedup_strict import is_signal_duplicate_strict

# Before creating signal
is_dup, existing_id = await is_signal_duplicate_strict(
    asset, timeframe, direction
)
if is_dup:
    # Skip signal creation
    return None
```

### Task 5: Ghost Prices & Asset Routing
**File**: `data/get_live_price.py`

**Integration**:
Use in realtime_outcome_tracker or price fetching:

```python
from data.get_live_price import get_live_price

# In outcome tracker
price = await get_live_price(symbol)
if price is None:
    # Try fallback or skip
    pass
```

---

## Quick Integration Commands

### 1. Add callback handler to bot.py (~line 4800 in run_bot):

After:
```python
application.add_handler(_CQH(_signal_reaction_callback, pattern=r"^signal_reaction_"))
```

Add:
```python
from signalrank_telegram.callback_handlers import create_global_callback_handler
application.add_handler(create_global_callback_handler())
```

### 2. Add validator to signal generation (~in engine/core.py):

Before signal enters ML pipeline:
```python
from engine.signal_validators import normalize_signal_for_ml
signal = normalize_signal_for_ml(signal)
```

### 3. Add strict dedup to signal creation (~in engine/core.py):

```python
from engine.signal_dedup_strict import is_signal_duplicate_strict
is_dup, _ = await is_signal_duplicate_strict(asset, timeframe, direction)
if is_dup:
    continue  # Skip
```

### 4. Update outcome tracker price fetch (~in engine/realtime_outcome_tracker.py):

Replace:
```python
price = await _get_live_price(symbol)
```

With:
```python
from data.get_live_price import get_live_price
price = await get_live_price(symbol)
```

---

## Testing

After integration, test each fix:

1. **Event Loop**: Monitor for blocking - should see concurrent tasks
2. **Buttons**: Click inline buttons - should respond immediately without loading circle
3. **TP Structure**: Send signal with single TP - should auto-convert to [TP1, TP2, TP3]
4. **Duplication**: Send same asset/timeframe/direction within 12h - second should be blocked
5. **Ghost Prices**: Request crypto price - should route to Binance not Polygon

---

## Rollback Plan

If issues occur:
- Task 2: Remove callback handler - revert to existing handlers
- Task 3: Comment out normalize_tp_structure() call
- Task 4: Use original dedup logic
- Task 5: Revert to original price fetch
