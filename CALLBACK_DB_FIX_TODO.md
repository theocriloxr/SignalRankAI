# SignalRankAI Callback Routing & DB Fix - Implementation TODO

## Status: IN PROGRESS

## Phase 1 — Fix Telegram Inline Buttons (bot.py) ✓ IN PROGRESS

### Step 1.1: Add Callback Diagnostic Logging ⚠️ PARTIAL
- [x] _signal_reaction_callback - Has logger.info ✓
- [x] _signal_monitor_callback - Has logger.info ✓
- [ ] Check other callbacks: mt5_trade_callback, check_outcome_callback
- [ ] Pattern: `logger.info("CALLBACK HIT: data=%s user=%s", query.data, user_id)`

### Step 1.2: Verify Handler Registration Order ⚠️ NEEDS VERIFICATION
- [ ] Verify specific CallbackQueryHandlers are registered BEFORE catch-all
- [ ] View: bot.py line ~6200+ for callback registrations

### Step 1.3: Add Global Callback Error Handler ✓ DONE
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

## Phase 3 — Fix Worker Architecture (worker/worker.py) ⚠️ PARTIAL

### Step 3.1: Add Worker Identity Logging
- [x] Worker name logging at startup ✓
- [ ] Add detailed worker startup logging

### Step 3.2: Add Heartbeats ⚠️ NEEDS CHECK
- [ ] Log heartbeat every 60 seconds

### Step 3.3: Reduce Concurrent DB Writes
- [x] Separate outcome tracker from signal generation ✓
- [ ] Batch non-critical DB operations

## Phase 4 — Production Diagnostics ⚠️ PARTIAL

### Step 4.1: Add /health Command
- [ ] DB Connected status
- [ ] Pool Used: X/20
- [ ] Redis Connected
- [ ] Workers Alive

### Step 4.2: Add /pool Command
- [ ] DB Pool Usage
- [ ] Callback Errors Today

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
