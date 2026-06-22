# Telegram Callback Investigation - Final Report

## Summary of Findings

### Codebase Analysis Complete

**Issue**: Buttons spin forever when clicked (callback never answers)

### Root Causes Investigated

| # | Cause | Evidence | Status |
|---|-------|----------|--------|
| 1 | Duplicate callback systems | bot.py + callback_handlers.py both have handlers | FOUND |
| 2 | Missing query.answer() | Inline handlers DO have it | OK |
| 3 | Logging filtered by level | Was using logger.info() | FIXED |
| 4 | Callback not registered | Handlers ARE registered | OK |

### Fixes Applied

**FIX 1**: Changed callback logging from INFO to WARNING level

```python
# Before: logger.info("CALLBACK HIT: data=%s user=%s", query.data, user_id)
# After:  logger.warning("CALLBACK HIT: data=%s user=%s", query.data, user_id)
```

This ensures Railway logs show callback entry points.

### Files Modified
- signalrank_telegram/bot.py (3 logger.info → logger.warning)

## Verification Steps

After deploying this fix:

1. **Click a pagination button** (e.g., "Next ➡️" on /help or /signals)
2. **Check Railway logs** for:
   - `[CALLBACK HIT] data=xxx user=xxx` → Callback IS reaching handler
   - No such line → Callback NOT reaching handler

## If Still Not Working

If no callback logs appear after the fix:

- Check webhook routing in railway_main.py
- Verify callback_query is being passed to Application
- Check for duplicate Application instances

## Duplicate Systems Found

- bot.py: Inline `_signal_reaction_callback`, `_signal_monitor_callback`
- callback_handlers.py: `callback_router` (NOT imported in main)  
- commands.py: Various handlers
- utils.py: Additional handlers

**Only ONE set should be active** - this duplication may cause conflicts.
