# Implementation Plan: Fix All 8 Issues + Additional Updates

## Summary of Analysis

### Information Gathered:

1. **services/gemini_ml.py**: Contains `async def audit_recent(limit: int = 50)` - function name is correct but needs alias for backward compatibility
2. **signalrank_telegram/commands.py**: Already has broker_map handling with `_chart_symbol_for_broker()` function
3. **ml/dynamic_threshold.py**: The `calculate_dynamic_threshold` function computes adjusted threshold but may return base in certain cases  
4. **data/providers.py**: Has timeframe mapping logic but needs enhancements
5. **db/session.py**: Already has good pool configuration with pool_size=15, max_overflow=15
6. **data/market_hours.py**: Already has comprehensive market hours logic with `is_market_open()` and holiday calendar
7. **signalrank_telegram/bot.py**: Need to verify all handlers are registered

## Plan

### Issue 1 & 7: audit_recent Import Error / /gemini_audit Failing
- **File**: services/gemini_ml.py
- **Fix**: Add backward compatible alias `audit_recent_signals = audit_recent`

### Issue 2: Max Score Showing 100  
- **File**: engine/core.py (need to find exact location)
- **Fix**: Calculate actual max from candidate dictionaries

### Issue 3: /signals Command Returns Empty
- **File**: signalrank_telegram/commands.py
- **Fix**: Ensure query filters for multiple statuses ('issued', 'open', 'active', 'pending')

### Issue 4: PostgreSQL "Too Many Clients"
- **Status**: Already has pool_size=15, max_overflow=15 - check if more tuning needed

### Issue 5: No Timeframe Data
- **File**: data/providers.py
- **Fix**: Add clean_tf_and_symbol helper

### Issue 6: Dynamic Threshold Not Working
- **File**: ml/dynamic_threshold.py  
- **Fix**: Ensure returns adjusted value correctly

### Issue 8: Command Recognition & Handler Configuration  
- **File**: signalrank_telegram/bot.py
- **Fix**: Verify all handlers registered

## Additional Updates:

1. **Broker Map** - Already exists in commands.py via `_chart_symbol_for_broker()`. Review and enhance if needed.

2. **Market Hours Verification**
   - **Status**: data/market_hours.py already has comprehensive logic
   - **Integration**: Add to engine cycle loop

3. **Updated Data Provider Timeframe Mapping**
   - **File**: data/providers.py
   - **Fix**: Add clean_tf_and_symbol() method

## Implementation Order:
1. Fix audit_recent import alias in gemini_ml.py
2. Fix dynamic_threshold return value  
3. Add timeframe cleaning logic to providers.py
4. Add market hours check to engine cycle
5. Test each fix
