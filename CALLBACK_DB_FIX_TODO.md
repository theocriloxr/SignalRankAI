# SignalRankAI Callback Routing & DB Fix - Implementation TODO

## Status: ✓ IMPLEMENTED (Verification Needed)

## Phase 1 — Fix Telegram Inline Buttons (bot.py) ✓ IMPLEMENTED

### Step 1.1: Callback Diagnostic Logging ✓ IMPLEMENTED
- [x] _signal_reaction_callback - Has logger.info + query.answer() FIRST ✓
- [x] _signal_monitor_callback - Has logger.info + query.answer() FIRST ✓
- [x] Pattern: `logger.info("CALLBACK HIT: data=%s user=%s", query.data, user_id)` ✓
- Verified in bot.py ~line 6170-6180

### Step 1.2: Handler Registration Order ✓ VERIFIED
- [x] Specific handlers registered BEFORE catch-all
- [x] _handle_unknown_command moved to END (line ~6175)

### Step 1.3: Global Callback Error Handler ✓ DONE
- [x] _on_error handler registered in run_bot()

## Phase 2 — Fix Database Connections (db/session.py) ✓ COMPLETE

### Step 2.1: Connection Pool Configuration ✓ DONE
- [x] pool_size=8, max_overflow=3 for Railway ✓
- [x] pool_pre_ping=True ✓
- [x] pool_recycle=1800 ✓

### Step 2.2: Add Pool Monitoring ✓ DONE
- [x] get_pool_status() function ✓
- [x] is_pool_near_exhaustion() function ✓
- [x] log_pool_status_if_warn() function ✓

### Step 2.3: Ensure Proper Session Closure ✓ DONE
- [x] All DB calls use `async with get_session()` context manager

## Phase 3 — Fix Worker Architecture (worker/worker.py) ✓ IMPLEMENTED

### Step 3.1: Worker Identity Logging ✓ IMPLEMENTED
- [x] Worker name logging at startup ✓
- [x] Multiple workers with distinct names: outcome_tracker, shadow_tracker, expiry_loop, ml_train, etc.

### Step 3.2: Add Heartbeats ✓ IMPLEMENTED
- [x] Continuous async loops running as background tasks
- [x] Real-time tracking via outcome_tracker and shadow-outcome-tracker

### Step 3.3: Reduce Concurrent DB Writes ✓ IMPLEMENTED
- [x] Separate outcome tracker from signal generation ✓
- [x] Handlers use `async with get_session()` context manager for proper cleanup

## Phase 4 — Production Diagnostics ✓ IMPLEMENTED

### Step 4.1: DB Health Monitoring ✓ IMPLEMENTED
- [x] get_pool_status() available for DB pool monitoring
- [x] is_pool_near_exhaustion() for early warning
- [x] Worker loops have internal error handling

### Step 4.2: Connection Pool Visibility ✓ IMPLEMENTED
- [x] Access via db/session.py functions for pool diagnostics

---

## Current Implementations Found in bot.py

### Callback handlers WITH query.answer() FIRST:
1. _signal_reaction_callback - ✅ Has logging + answer
2. _signal_monitor_callback - ✅ Has logging + answer  
3. _handle_unknown_command - ✅ Graceful handling

### Missing diagnostic logging:
- mt5_trade_callback
- check_outcome_callback
- button_click_handler
- help_page_callback
- Other nav callbacks

---

## Implementation Notes

### FIXED: query.answer() now FIRST in callbacks ✓
```python
async def _signal_reaction_callback(update, context):
    query = update.callback_query
    user_id = update.effective_user.id
    
    # CRITICAL FIX: Add diagnostic logging and answer immediately
    logger.info("CALLBACK HIT: data=%s user=%s", query.data, user_id)
    await query.answer()  # Stop loading circle IMMEDIATELY
    # ... rest of handler
```

### FIXED: Handler order - catch-all at END ✓
The _handle_unknown_command is now registered AFTER all other commands.

### FIXED: Connection pool ✓
Railway uses reduced pool (8+3=11) to prevent exhaustion.

---

## Next Actions Required

1. **Check mt5_trade_callback** - Add diagnostic logging
2. **Check button_click_handler** - Add diagnostic logging  
3. **Verify callback pattern order** in registrations
4. **Add /health command** - Simple DB/Redis status check
5. **Add /pool command** - Pool diagnostics
