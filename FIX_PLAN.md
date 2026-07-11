# SignalRankAI - Golden Loop Stabilization & Performance Fixes

## Executive Summary
This document outlines the critical bug fixes and performance improvements needed to stabilize the Golden Loop engine after it successfully entered the live trading environment.

## Issues Identified

### 1. Macro Data API Rate Limits (HTTP 429)
**Problem**: 
- Logs show: `WARNI [data.providers] [polygon] fetch_failed symbol=US10Y status=429`
- The engine loops every ~60 seconds, but free API tiers only allow a few requests per minute
- Macro indicators (US10Y, VIX, DXY) don't change by the minute - they should be cached

**Solution**:
- Implement in-memory cache using cachetools TTLCache for macro data
- Set TTL to 3600 seconds (1 hour) for macro indicators
- Cache location: data/fetcher.py

### 2. The "Over-Trading" Bug (Duplicate Trades)
**Problem**:
- Logs show: Multiple ETHUSDT longs opened in 3-minute span
- The Correlation Guard works (skipped_portfolio_exposure=16)
- But no check for existing open positions on the same asset

**Solution**:
- Add duplicate trade check in engine/core.py before execution
- Fetch active positions and skip if asset already in trade
- Add logic: `if asset in active_assets: continue`

### 3. aiohttp Memory Leak (Unclosed Client Sessions)
**Problem**:
- Logs show: `ERROR asyncio: Unclosed client session`
- This happens when HTTP requests are made without proper cleanup
- Will cause OOM crash over time

**Solution**:
- Ensure all API calls use async with blocks
- Use context managers for aiohttp sessions
- Check data/providers.py for async implementations

### 4. Missing created_at Column
**Problem**:
- Log shows: `WARNING engine.admin_pulse: created_at column missing in signal_deliveries`

**Solution**:
- Run SQL: `ALTER TABLE signal_deliveries ADD COLUMN IF NOT EXISTS created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;`

### 5. Database Connection Pooling (NullPool Issue)
**Problem**:
- Logs show: `Using NullPool - connection pooling disabled`
- Opens/closes TCP connection on every query → massive latency

**Solution**:
- In db/session.py, enable QueuePool instead of NullPool
- Keep connections alive and reuse them

### 6. Graceful Shutdown
**Problem**:
- `while True:` loops block clean shutdown
- Railway deployments may corrupt in-flight trades

**Solution**:
- Use threading.Event for shutdown signal
- Catch SIGTERM and finish current loop before exiting

---

## Implementation Plan

### Phase 1: Critical Fixes (Must Do First)

#### 1.1 Add Macro Data Caching (data/fetcher.py)
```python
from cachetools import TTLCache, cached

# Cache macro data for 1 hour
_MACRO_CACHE = TTLCache(maxsize=10, ttl=3600)

@cached(cache=_MACRO_CACHE)
def get_macro_data(symbol):
    # Existing API call logic
    pass
```

#### 1.2 Fix Duplicate Trade Check (engine/core.py)
```python
# Before execute_trade in the main loop:
open_trades = await db.get_open_trades()
active_assets = [trade.asset for trade in open_trades]

if asset in active_assets:
    logger.info(f"Skipping {asset}: Position already open.")
    continue
```

#### 1.3 Fix aiohttp Memory Leak
- Ensure all async HTTP calls use `async with aiohttp.ClientSession()`
- Add proper session.close() in finally blocks

### Phase 2: Database Fixes

#### 2.1 Add created_at Column
File: fix_created_at_column.sql
```sql
ALTER TABLE signal_deliveries ADD COLUMN IF NOT EXISTS created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;
```

#### 2.2 Enable Connection Pooling
In db/session.py:
```python
# Change from NullPool to QueuePool
poolclass=pool.QueuePool,
pool_size=5,
max_overflow=10,
```

### Phase 3: Infrastructure

#### 3.1 Graceful Shutdown
```python
import signal
shutdown_event = threading.Event()

def handle_sigterm(*args):
    shutdown_event.set()

signal.signal(signal.SIGTERM, handle_sigterm)

# In main loop:
while not shutdown_event.is_set():
    # ... trading logic
```

---

## Files to Modify

1. **data/fetcher.py** - Add macro caching
2. **engine/core.py** - Add duplicate trade check, graceful shutdown
3. **db/session.py** - Enable connection pooling
4. **Create fix_created_at_column.sql** - Database migration

---

## Execution Order

1. First: Add macro data caching (fixes 429 errors)
2. Second: Add duplicate trade check (stops over-trading)
3. Third: Fix aiohttp memory leak
4. Fourth: Run database migration
5. Fifth: Enable connection pooling
6. Sixth: Add graceful shutdown

---

## Testing Checklist

- [ ] Macro data cached for 1 hour (check logs for 429 errors stop)
- [ ] No duplicate trades on same asset
- [ ] No "Unclosed client session" errors
- [ ] created_at column exists
- [ ] Using QueuePool (not NullPool)
- [ ] Graceful shutdown works on SIGTERM
