# SignalRankAI Callback Routing & DB Fix Plan

## Status: IN PROGRESS

## Phase 1 — Fix Telegram Inline Buttons (bot.py) ✓ IN PROGRESS

### Step 1.1: Add Callback Diagnostic Logging
- [ ] Add logger.info at top of every callback handler
- [ ] Add `await query.answer()` IMMEDIATELY before any DB call
- [ ] Pattern: `logger.info("CALLBACK HIT: data=%s user=%s", query.data, user_id)`

### Step 1.2: Verify Handler Registration Order
- [ ] Specific CallbackQueryHandlers FIRST
- [ ] Catch-all handler LAST

### Step 1.3: Add Global Callback Error Handler
- [ ] Add application.add_error_handler for callback errors

## Phase 2 — Fix Database Connections (db/session.py)

### Step 2.1: Connection Pool Configuration
- [ ] Verify pool_size=8, max_overflow=3 for Railway
- [ ] Add pool_pre_ping=True
- [ ] Add pool_recycle=1800

### Step 2.2: Add Pool Monitoring
- [ ] Log pool status at startup
- [ ] Add periodic pool status logging

### Step 2.3: Ensure Proper Session Closure
- [ ] All DB calls use `async with get_session()`

## Phase 3 — Fix Worker Architecture (worker/worker.py)

### Step 3.1: Add Worker Identity Logging
- [ ] Log worker name at startup

### Step 3.2: Add Heartbeats
- [ ] Log heartbeat every 60 seconds

### Step 3.3: Reduce Concurrent DB Writes
- [ ] Batch non-critical DB operations
- [ ] Separate outcome tracker from signal generation

## Phase 4 — Production Diagnostics

### Step 4.1: Add /health Command
- [ ] DB Connected
- [ ] Pool Used: X/20
- [ ] Redis Connected
- [ ] Workers Alive

### Step 4.2: Add /pool Command
- [ ] DB Pool Usage
- [ ] Callback Errors Today

---

## Implementation Notes

### Critical Fix: query.answer() must be FIRST
Every callback handler should begin with:
```python
await query.answer()  # Stop loading circle immediately
```

### Critical Fix: Add diagnostic logging
```python
logger.info("CALLBACK HIT: data=%s user=%s", query.data, user_id)
```

### Critical Fix: Handler Order
Specific handlers MUST come before catch-all:
```python
# FIRST: Specific handlers
application.add_handler(CallbackQueryHandler(track_outcome_callback, pattern="^track:"))
application.add_handler(CallbackQueryHandler(analysis_callback, pattern="^analysis:"))
# ...

# LAST: Catch-all
application.add_handler(CallbackQueryHandler(callback_router))
