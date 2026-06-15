# TODO: Fix All 8 Issues Implementation Plan

## Issues to Fix (from comprehensive guide)

### Issue 1 & 7: audit_recent Import Error
- Location: services/gemini_ml.py + signalrank_telegram/commands.py
- Problem: Function named audit_recent_signals but commands.py imports audit_recent
- Fix: Add alias export in gemini_ml.py

### Issue 2: Max Score Showing 100
- Location: engine/core.py
- Problem: max_score hardcoded to 100.0
- Fix: Calculate dynamic max values from candidates

### Issue 3: /signals Command Returns Empty
- Location: signalrank_telegram/commands.py
- Problem: Filters only for "active" status
- Fix: Include "issued", "open" statuses

### Issue 4: PostgreSQL "Too Many Clients" Errors
- Location: db/session.py
- Problem: Connection pool exhaustion
- Fix: Implement bounded pooling

### Issue 5: No Timeframe Data
- Location: data/providers.py
- Problem: Timeframe mapping issues
- Fix: Add clean_tf_and_symbol mapping

### Issue 6: Dynamic Threshold Not Working
- Location: ml/dynamic_threshold.py
- Problem: Returns base instead of adjusted
- Fix: Return adjusted value

### Issue 8: Command Handler Registration
- Location: signalrank_telegram/bot.py
- Problem: Missing command handlers
- Fix: Register all handlers

## Additional Features Requested
- Broker Map Update (in commands.py)
- Market Hours Verification (already in data/market_hours.py - verify)

## Implementation Order
1. Fix import alias in gemini_ml.py
2. Update commands.py imports and broker map
3. Fix db/session.py pooling
4. Fix providers.py timeframe mapping
5. Verify/fix dynamic_threshold.py
6. Check engine/core.py for max_score
7. Verify market_hours.py integration
8. Check bot.py handlers
