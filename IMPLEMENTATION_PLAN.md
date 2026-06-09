# SignalRankAI Implementation Plan: Redis GlobalStats & Execution Engine

Based on the diagnostic analysis, this plan addresses three critical issues:

1. **Pulse Showing Zeros** - GlobalStats process isolation bug
2. **VIP Signal Delay** - Silent real-time broadcast failures  
3. **Execution Engine** - Paper trading + MT5 integration

---

## Part 1: Redis-Based GlobalStats (Fix Pulse Zeros)

### Root Cause
The `engine/stats_manager.py` uses Python class attributes which are process-local. When the Engine runs in one worker and Pulse runs in another, they don't share memory.

### Solution
Create a new `RedisGlobalStats` class that syncs to Redis so all workers share the same counters.

### Implementation Steps:

1. **Create `core/redis_global_stats.py`** - New module with Redis-backed stats:
```python
class RedisGlobalStats:
    - Uses Redis for all counter operations
    - Falls back to in-memory if Redis unavailable
    - Methods: increment_scanned(), increment_delivered(), increment_vetoed(), get_stats()
```

2. **Update `engine/admin_pulse.py`** - Use RedisGlobalStats instead of process-local GlobalStats:
```python
- Import RedisGlobalStats 
- Replace `from engine.stats_manager import stats` with `from core.redis_global_stats import global_stats`
- Admin pulse will now read real-time counters from Redis shared state
```

3. **Update `engine/core.py`** - Use RedisGlobalStats in engine loop:
```python  
- Import RedisGlobalStats at top of file
- Replace `from engine.stats_manager import stats` 
- Use same RedisGlobalStats instance for incrementing counters
```

---

## Part 2: Fix VIP Real-Time Broadcast

### Root Cause
The real-time broadcast in engine/core.py `deliver_all()` may fail silently without proper error handling.

### Solution
Add try/except with proper error logging around dispatch calls, and ensure VIP signals are sent immediately.

### Implementation Steps:

1. **Wrap dispatch in try/except in `engine/core.py`**:
```python
# Around dispatch_signals_async call:
try:
    await dispatch_signals_async(user_signals, user_id=user_id)
except Exception as e:
    logger.error(f"[engine] Dispatch failed for user {user_id}: {e}")
    # Try to re-queue or log for retry
```

2. **Add VIP priority flag to signals**:
```python
# In signal dict, mark VIP signals:
signal['priority_delivery'] = True  # for VIP tier
signal['instant_broadcast'] = True  # bypass queue
```

3. **Check TierDeliveryManager for VIP instant path**:
```python
# Ensure VIPs get first access before free tier dispatch
```

---

## Part 3: Execution Engine (Paper Trading + MT5)

### What Already Exists
- `core/trade_tracker.py` has TradeRecord for tracking open trades in Redis
- `config.py` has PAPER_TRADING_START_BALANCE_USD configuration

### What's Missing
- Paper account balance management
- MT5 integration for live trading

### Solution
Create ExecutionManager class that handles paper trading and MT5 execution.

### Implementation Steps:

1. **Create `engine/execution_manager.py`**:
```python
class ExecutionManager:
    def __init__(self, mode="paper"):
        # mode: "paper" or "mt5"
        
    async def execute_signal(self, signal: dict) -> bool:
        # Execute signal based on mode
        if self.mode == "paper":
            return await self._execute_paper(signal)
        else:
            return await self._execute_mt5(signal)
    
    async def _execute_paper(self, signal: dict) -> bool:
        # Check balance
        # Create virtual trade
        # Track in Redis
        
    async def _execute_mt5(self, signal: dict) -> bool:
        # Send to MT5 API bridge
        # Handle response
        
    async def close_trade(self, trade_id: str, outcome: str) -> dict:
        # Close trade, calculate PnL
        # Update balance (paper) or confirm with MT5
```

2. **Create database table for paper trades**:
```sql
CREATE TABLE paper_trades (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    signal_id UUID REFERENCES signals(signal_id),
    user_id INT,
    asset TEXT NOT NULL,
    direction TEXT NOT NULL,  -- 'long' or 'short'
    entry_price DECIMAL NOT NULL,
    exit_price DECIMAL,
    size DECIMAL NOT NULL,
    status TEXT NOT NULL,   -- 'OPEN', 'CLOSED'
    outcome TEXT,           -- 'TP', 'SL', 'PARTIAL_TP'
    pnl_decimal DECIMAL,
    opened_at TIMESTAMP DEFAULT NOW(),
    closed_at TIMESTAMP,
    r_multiple DECIMAL
);

CREATE TABLE paper_accounts (
    user_id INT PRIMARY KEY,
    balance DECIMAL NOT NULL DEFAULT 10000.00,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);
```

3. **Add MT5 integration**:
```python
# Option A: MetaApi bridge (recommended for Railway)
MT5_API_URL = os.getenv("MT5_API_URL", "")
MT5_API_TOKEN = os.getenv("MT5_TOKEN", "")

async def _execute_mt5(self, signal: dict) -> bool:
    # Send order to MT5 bridge
    response = await requests.post(
        f"{MT5_API_URL}/orders",
        json={...},
        headers={"Authorization": f"Bearer {MT5_TOKEN}"}
    )
    return response.ok
```

---

## File Changes Summary

| File | Action | Purpose |
|------|--------|---------|
| `core/redis_global_stats.py` | CREATE | Redis-backed GlobalStats |
| `engine/admin_pulse.py` | UPDATE | Use RedisGlobalStats |
| `engine/core.py` | UPDATE | Use RedisGlobalStats, fix dispatch error handling |
| `engine/execution_manager.py` | CREATE | Paper/MT5 execution |
| `paper_trades.sql` | CREATE | Database schema for paper trading |

---

## Implementation Order

1. ✅ Part 1: RedisGlobalStats (core/redis_global_stats.py)
2. ✅ Part 1: Update admin_pulse.py  
3. ✅ Part 1: Update engine/core.py
4. ✅ Part 2: Fix dispatch error handling
5. ⏳ Part 3: ExecutionManager (optional - requires DB migrations)
6. ⏳ Part 3: Paper trades table (optional)
7. ⏳ Part 3: MT5 integration (optional - requires mt5_token)

---

## Dependencies

- Redis is already configured via REDIS_URL
- MT5 token configuration via MT5_TOKEN env var
- Database migrations require PostgreSQL access
