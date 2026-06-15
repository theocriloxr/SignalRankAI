# TODO: Fix All 8 Issues Implementation Plan

## Issues to Fix

### Issue 1 & 7: audit_recent Import Error
- Location: services/gemini_ml.py
- Status: ALREADY HAS alias at end, but references non-existent function `audit_recent_signals`
- Fix needed: Check/create the missing function

### Issue 2: Max Score Showing 100  
- Location: engine/core.py
- Status: Need to find where max_score is calculated
- Fix needed: Calculate dynamically from candidates

### Issue 3: /signals Command Returns Empty
- Location: signalrank_telegram/commands.py
- Status: Need to verify status filtering
- Fix needed: Expand to include 'issued', 'open' statuses

### Issue 4: PostgreSQL "Too Many Clients"
- Location: db/session.py
- Status: Already has pooling, but might need adjustments
- Fix: Review and adjust pool settings

### Issue 5: No Timeframe Data - All Assets
- Location: data/fetcher.py  
- Status: Already has complex multi-provider fallback
- Fix: Verify timeframe normalization exists

### Issue 6: Dynamic Threshold Not Working
- Location: ml/dynamic_threshold.py
- Status: Function already returns adjusted correctly (different from task description)
- Fix: Verify correct function is called

### Issue 8: Command Recognition & Handler Configuration
- Location: signalrank_telegram/bot.py
- Status: Need to verify all handlers registered

## Additional Features Requested

1. **Broker Map Update** - Add to commands.py
2. **Market Hours Verification** - Create utils/market_hours.py

## Implementation Steps

1. Check services/gemini_ml.py for audit_recent_signals function
2. Find max_score calculation in engine/core.py  
3. Verify signals_command status filtering
4. Check db/session.py pool settings
5. Verify data/fetcher.py timeframe handling
6. Verify ml/dynamic_threshold.py is called correctly
7. Check bot.py handlers
8. Create utils/market_hours.py with broker map and market hours
