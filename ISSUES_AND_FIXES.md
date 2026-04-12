# SignalRankAI - Known Issues & Fixes Reference

**Last Updated**: April 12, 2026  
**Status**: Active Maintenance  
**Severity Levels**: 🔴 Critical | 🟡 High | 🟢 Medium | 🔵 Low

---

## 🔴 CRITICAL ISSUES

### Issue #1: Signals Not Generating After Fresh Deploy

**Symptoms**:
- No `[engine] heartbeat: cycle=X` logs
- No signals in `signals` table after 5+ minutes
- `/signals` command returns "no signals"

**Root Cause**:
- Fresh database missing columns on cold start
- Engine loop starting before schema ready
- Market data provider failures (no API keys)

**Fix**:
```bash
# Set these environment variables:
STARTUP_STRICT_SCHEMA_READY=1      # Wait for schema
STARTUP_OPS_TIMEOUT_SECONDS=180     # Give 3min to complete
AUTO_MIGRATE=1                      # Run migrations auto
DB_POOL_SIZE=1                      # Prevent conn pool issues

# Then restart:
railway redeploy  # or locally: ctrl-c and restart
```

**Verification**:
```bash
# Look for these logs in order:
[startup] DB startup ops begin
[startup] Adding columns to users...
[startup] DB startup ops end
[engine] heartbeat: cycle=1 running    # Should appear every 30s
```

---

### Issue #2: Command Handlers Crashing on Fresh Schema

**Symptoms**:
- `/start` command times out or returns error
- "column users.max_daily_drawdown_pct does not exist"
- "column users.execution_mode does not exist"

**Root Cause**:
- User schema missing new columns
- Migrations not run before worker starts
- Command handlers query all columns including new ones

**Fix**:
```bash
# Option A: Auto-bootstrap on startup (Railway)
STARTUP_SCHEMA_BOOTSTRAP=1          # Create missing columns
STARTUP_STRICT_SCHEMA_READY=1       # Don't start until ready
AUTO_MIGRATE=0                      # Skip full migrations if desired

# Option B: Manually run migrations
python -m alembic upgrade head      # Local
railway run alembic upgrade head    # Railway

# Verify columns exist:
railway conn postgres
SELECT column_name FROM information_schema.columns 
WHERE table_name='users' 
ORDER BY ordinal_position;

# Should include: max_daily_drawdown_pct, execution_mode, auto_signals_daily_limit
```

**Verification**:
```bash
# After fix, test:
/start              # Should respond < 2s
/account            # Should show user info
/status             # Should show stats
```

---

### Issue #3: Webhook Queue Split-Brain (Lost Messages)

**Symptoms**:
- Telegram updates queued but never processed
- Command delays (10+ seconds)
- Redis enqueue succeeds but worker doesn't find messages

**Root Cause**:
- In-process queue fallback on Redis timeout
- Worker only reads Redis, not in-process queue
- Split-brain: updates in two places

**Status**: ✅ FIXED in railway_main.py

**What Was Fixed**:
```python
# Before (broken): Worker only read Redis
await _get_from_redis_queue()

# After (fixed): Worker drains in-process first
while True:
    try:
        # Get pending in-process first
        update = _webhook_dispatch_queue.get_nowait()
        await process_update(update)
    except asyncio.QueueEmpty:
        # Then read from Redis
        update = await _redis_queue.blpop(timeout=5)
        await process_update(update)
```

**Verification**: Already deployed. No action needed.

---

### Issue #4: Event Loop Errors in Railway (Future attached to different loop)

**Symptoms**:
- `asyncpg.exceptions: Future attached to a different loop`
- `RuntimeError: Event loop is closed`
- Database operations fail intermittently

**Root Cause**:
- Multiple `asyncio.run()` calls created multiple event loops
- Connections bound to old loop
- Engine/Worker started in different threads/loops

**Status**: ✅ FIXED in db/session.py

**What Was Fixed**:
```python
# Before (broken): Each call got different engine
engine = create_async_engine(url)  # New engine every time

# After (fixed): Engine cached per event loop
_async_engines: dict[int, AsyncEngine] = {}

def get_engine_for_event_loop() -> AsyncEngine:
    loop_id = id(asyncio.get_running_loop())
    if loop_id not in _async_engines:
        _async_engines[loop_id] = create_async_engine(url, poolclass=NullPool)
    return _async_engines[loop_id]
```

**Verification**: Already deployed. Connection errors should resolve.

---

## 🟡 HIGH PRIORITY ISSUES

### Issue #5: Background Task Crashes Silent (No Logging)

**Symptoms**:
- Engine/Worker task stops but no error in logs
- App continues running (tasks are "done" but exception not retrieved)
- Signal generation stops unexpectedly

**Status**: ✅ FIXED in railway_main.py

**What Was Fixed**:
```python
# Before (broken): Task crashes silently
task = asyncio.create_task(engine_loop())
# Exception stored in task but never logged

# After (fixed): Done callback with exception logging
task.add_done_callback(lambda t: _log_task_failure(t, "engine-loop"))

def _log_task_failure(task, name):
    try:
        if task.cancelled():
            logger.info("[task] %s cancelled", name)
            return
        exc = task.exception()
        if exc is not None:
            logger.error("[task] %s crashed: %s", name, exc,
                         exc_info=(type(exc), exc, exc.__traceback__))
    except Exception as e:
        logger.warning("[task] failed to inspect: %s", e)
```

**Verification**: Restart and monitor logs for any exceptions.

---

### Issue #6: Redis Connection String Resolution

**Symptoms**:
- `webhook_queue_use_redis=False` despite REDIS_URL set
- Logs show "Redis unavailable; using in-process"
- Fallback queue works but slower

**Root Cause**:
- Redis connection test fails silently
- Multiple REDIS_* env var names (REDIS_URL, REDIS_PRIVATE_URL, etc.)
- Railway plugin sets REDIS_PRIVATE_URL, not REDIS_URL

**Fix**:
```bash
# Railway automatically detects these (in order):
REDIS_URL
REDIS_PRIVATE_URL       # ← Railway plugin sets this
REDIS_PUBLIC_URL
REDIS_INTERNAL_URL
REDIS_TLS_URL

# Verify which is set:
railway env | grep -i redis

# If using private URL, verify internal connectivity:
# No action needed - auto-detected
# If want to force retry:
railway redeploy
```

**Fallback Behavior**: In-process queue works perfectly fine, just slightly slower (< 100ms variance)

---

### Issue #7: Market Data Provider Failures Cascade

**Symptoms**:
- First few cycles work, then signals stop
- "Provider unavailable" errors in logs
- Asset fetch returns empty list

**Root Cause**:
- Single provider failure (API key wrong, rate limit, timeout)
- No fallback to next provider
- Entire asset cycle skipped

**Status**: ✅ Partially FIXED

**What to Do**:
```bash
# 1. Add backup API keys
ALPHAVANTAGE_API_KEY=<key1>         # Alternative to Binance
CRYPTOCOMPARE_API_KEY=<key2>        # Backup crypto data
NEWS_API_KEY=<key from newsapi.org> # Must have for sentiment

# 2. Set provider order/fallback
# This is automatic in data/fetcher.py

# 3. Monitor logs
railway logs | grep -i provider
railway logs | grep -i "unavailable\|timeout"

# 4. Increase timeouts if on slow connection
ENGINE_MARKET_FETCH_TIMEOUT_SECONDS=300  # 5 min max wait
```

---

### Issue #8: Memory Exhaustion on Railway Free Tier

**Symptoms**:
- Process killed with `OOMKilled`
- Railway shows "Service Crashed (Out of Memory)"
- Logs abruptly stop

**Root Cause**:
- Railway free tier = 256 MB RAM
- ML model loading (50-100 MB)
- Candle cache accumulation
- Market data buffering

**Fix**:
```bash
# Disable heavy features
CRYPTO_WS_ENABLED=false             # WebSocket expensive
ML_TRAIN_ENABLED=false              # Training uses memory
ENABLE_NEWS=false                   # News processing
XGB_NTHREAD=1                       # Model threading

# Reduce cycling
CYCLE_BATCH_SIZE=5                  # Instead of 20
ENGINE_UNIVERSE_CAP=5               # Instead of 20
MARKET_DATA_CACHE_TTL_SECONDS=30    # Shorter TTL

# Reduce pool size
DB_POOL_SIZE=1
DB_MAX_OVERFLOW=0

# If still issues: upgrade Railway to paid tier
```

**Verification**:
```bash
# Check memory usage
railway logs | grep -i "memory\|process"

# Check if stable after 1 hour
railway logs -f --since 1h
```

---

## 🟢 MEDIUM PRIORITY ISSUES

### Issue #9: Duplicate APScheduler Job Keys

**Symptoms**:
- Logs: `Duplicate key 'apscheduler_jobs_pkey'`
- Jobs not running on restart
- Startup takes longer than expected

**Root Cause**:
- Old Railway account had lingering apscheduler records
- Fresh account starts clean (shouldn't happen)

**Fix** (if appears):
```bash
# Railway/Fresh account: Clean database first
# Old account: Clear old job records
DELETE FROM apscheduler_jobs;

# Set replace_existing=True in all scheduler.add_job calls
# Already done in current code
```

**Verification**: Should not appear on fresh account. If does, check if old DB was reused.

---

### Issue #10: Signal Expiry Not Cleaning Up (Disk Space)

**Symptoms**:
- `signals` table grows unbounded
- Database size increases 100+ MB/week
- Queries slow down over time

**Root Cause**:
- Expired signals not archived/deleted
- Soft-delete via `archived_at` but not actually removed
- 12-hour expiry: ~2880 signals/day * 7 = 20k/week

**Fix** (Future):
```sql
-- Automatic cleanup (implement as scheduled job)
DELETE FROM signals 
WHERE archived_at IS NOT NULL 
AND archived_at < NOW() - INTERVAL '30 days';

-- Or archive to separate table
INSERT INTO signals_archived SELECT * FROM signals WHERE archived_at IS NOT NULL;
DELETE FROM signals WHERE archived_at IS NOT NULL;
```

**For Now**: Database grows ~2-3 GB/year. Acceptable for small deployments.

---

### Issue #11: Tier Delivery Rate Limiting

**Symptoms**:
- FREE tier users get 1-3 signals/day but sometimes 0
- PREMIUM users get 5-10 but inconsistent

**Root Cause**:
- Daily limit counter resets at UTC midnight
- User in different timezone sees "used up" limit

**Status**: ⚠️ Design Decision

**Current Behavior**:
```python
# Limit resets at UTC midnight
if signal_count_today >= user.daily_limit:
    skip_delivery()

# Counts signals delivered since TODAY_UTC_START
```

**If You Want**: Per-user timezone reset:
```python
user_tz = user.timezone or 'UTC'  # Add timezone field to users table
local_midnight = datetime.now(pytz.timezone(user_tz)).replace(hour=0, minute=0, second=0)
daily_reset_time = local_midnight.astimezone(pytz.UTC)
```

---

## 🔵 LOW PRIORITY / COSMETIC ISSUES

### Issue #12: Outcome Notification Delays (VIP Users)

**Symptoms**:
- TP1 hit takes 10-30s to notify
- SL hit slower than live trading
- User sees price hit but notification delayed

**Root Cause**:
- Outcome check interval = 10s (configurable)
- Notification processing in queue
- Telegram API latency (1-3s)

**Current**: ~2-5 seconds typical, 10-15s worst case

**If You Want Faster**: Lower polling frequency
```bash
OUTCOME_CHECK_INTERVAL_SECONDS=5  # Check every 5s instead of 10s
# Costs: slightly higher CPU, faster notifications
```

---

### Issue #13: ML Model Not Updating

**Symptoms**:
- Same model used for days/weeks
- Training log appears but model.json unchanged

**Root Cause**:
- ML retraining disabled by default (`ML_TRAIN_ENABLED=false`)
- Or training completes but model not copied to production

**Fix**:
```bash
ML_TRAIN_ENABLED=true
ML_TRAIN_INTERVAL_SECONDS=86400  # Retrain daily (1am UTC)

# Verify:
railway logs | grep -i "ml_train\|retrain"

# Should see daily logs like:
[ml_train] Beginning model retraining...
[ml_train] Completed: trained on 5000 samples
[ml_train] New model accuracy: 0.623
```

---

### Issue #14: Sentiment Always Neutral (No Sentiment Data)

**Symptoms**:
- Signals always show "Sentiment: Neutral"
- No fear/greed index in signal details

**Root Cause**:
- NewsAPI key not configured
- Or free tier has 100 req/day limit (runs out)

**Fix**:
```bash
# Get key from newsapi.org (free: 100 req/day)
NEWS_API_KEY=<your-key>

# Verify working:
/market              # Should show "Fear/Greed" index

# If still neutral:
ENABLE_NEWS=false    # Disable to reduce requests
# Sentiment optional; signals work without it
```

---

### Issue #15: Broker Connection (MT5) Not Linking

**Symptoms**:
- `/mt5_link` command times out
- "Broker validation failed"

**Root Cause**:
- META_API_TOKEN not configured
- Or MetaAPI.cloud service unavailable

**Status**: Optional feature (not critical)

**Fix**:
```bash
# If want automatic execution:
META_API_TOKEN=<from metaapi.cloud>
META_API_ACCOUNT_ID=<account id>

# Otherwise, VIP users can trade manually
# Signal → User → Manual execution still works
```

---

## 📋 Issue Checklist

Use this to verify your deployment is healthy:

- [ ] No `CRITICAL` issues (all marked as FIXED or N/A)
- [ ] Signals generating: `[engine] heartbeat:` every 30s
- [ ] Commands responsive: `/help` < 2s
- [ ] No database errors: `grep -i "database\|asyncpg"`
- [ ] No webhook errors: `grep -i "webhook\|telegram"`
- [ ] Memory stable: No OOMKilled
- [ ] Outcomes detecting: `[outcome]` logs present if signals active

If any issues remain, file them in this document with:
1. Symptoms
2. Reproduction steps
3. Root cause analysis
4. Proposed fix

---

## 🚀 How to Report New Issues

1. Check if issue appears in logs: `railway logs | grep -i "<error>"`
2. Identify issue type: Signal-related? Database? Telegram?
3. Get reproduction steps
4. Add to this document with:
   - **Symptoms**: What user sees
   - **Root Cause**: Why it happens
   - **Fix**: Solution or workaround
   - **Verification**: How to test fix

---

## ✅ Status Summary

| Issue | Status | Impact | Action |
|-------|--------|--------|--------|
| Signals not generating | 🟢 Fixed | 🔴 Critical | Deployed |
| Command handler crashes | 🟢 Fixed | 🔴 Critical | Deployed |
| Webhook split-brain | 🟢 Fixed | 🟡 High | Deployed |
| Event loop errors | 🟢 Fixed | 🔴 Critical | Deployed |
| Task crashes silent | 🟢 Fixed | 🟡 High | Deployed |
| Redis detection | 🟢 Works | 🔵 Low | Fallback OK |
| Provider fallback | 🟡 Partial | 🟡 High | Add API keys |
| Memory exhaustion | 🟢 Mitigated | 🟡 High | Disable features |
| APScheduler duplicate | 🟢 Fixed | 🟢 Medium | Deploy fresh |
| Signal expiry cleanup | 🟡 Pending | 🔵 Low | Future feature |
| Tier rate limiting | 🟢 Works | 🔵 Low | UTC-based |
| Outcome notifications | 🟢 Works | 🔵 Low | < 5s latency |
| ML model updates | 🟢 Optional | 🔵 Low | Enable if needed |
| Sentiment data | 🟢 Optional | 🔵 Low | Add API key |
| MT5 linking | 🟢 Optional | 🔵 Low | Manual trading OK |

