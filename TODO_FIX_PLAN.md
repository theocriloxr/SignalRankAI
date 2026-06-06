# SignalRankAI Fix Plan

## Issues to Fix Based on User Logs

### Issue 1: Telegram Bot - Unknown Command Errors for /gemini_analyze, /gemini_audit, /gemini_predict

**Root Cause:** The catch-all unknown command handler (`MessageHandler(filters.COMMAND)`) is catching custom commands because either:
- The handlers aren't properly registered before it
- The handlers are registered but lack proper implementation

**Step 1 Fix:** Ensure handler registration order in bot.py:
- gemini_analyze, gemini_audit, gemini_predict handlers must be registered BEFORE the catch-all MessageHandler

### Issue 2: SyntaxError in engine/core.py (line ~1616)

**Root Cause:** The ML logging code has a try: block without a corresponding except: block

**Step 2 Fix:** Add the missing except Exception block in the ML logging section around line 1616

### Issue 3: Railway Database Connection Limits - "too many clients already"

**Root Cause:** SQLAlchemy pool_size is too high (10) for Railway's 20-connection limit when combined with worker threads

**Step 3 Fix:** Reduce pool_size to 3 in db/session.py

---

## Implementation Plan

### Task 1: Verify/Fix bot.py Handler Registration Order
- [x] Read signalrank_telegram/bot.py around handler registration
- [x] Verify gemini_analyze_command, gemini_audit_command, gemini_predict_command are imported
- [x] Verify they are registered BEFORE MessageHandler(filters.COMMAND)
- [x] Handler order is CORRECT - gemini commands are registered before unknown handler in current code

### Task 2: Fix Syntax Error in engine/core.py
- [ ] Locate the try block around line 1616 in engine/core.py
- [ ] Add missing except Exception as e: block with proper logging

### Task 3: Reduce DB Pool Size
- [x] Edit db/session.py 
- [x] Pool settings already capped properly via _effective_pool_settings()
- [x] Override Railway cap via env vars if needed

---

## Files to Modify

1. `signalrank_telegram/bot.py` - Already correct (handler order fixed)
2. `engine/core.py` - Need to add missing except block
3. `db/session.py` - Already configured correctly

---

## Testing After Fix

1. Deploy to Railway
2. Check bot /help shows gemini commands
3. Test /gemini_analyze, /gemini_audit, /gemini_predict
4. Verify engine starts without SyntaxError
5. Monitor database connection count
