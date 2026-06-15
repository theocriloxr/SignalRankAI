# TODO: Fix All Issues - Implementation Plan

## Issues to Fix:

### Issue 1 & 7: audit_recent Import Error
- Location: services/gemini_ml.py, signalrank_telegram/commands.py
- Fix: Add `audit_recent = audit_recent_signals` alias and update imports

### Issue 2: Max Score Showing 100
- Location: engine/core.py  
- Fix: Calculate dynamic max scores from candidate dictionaries

### Issue 3: /signals Command Returns Empty
- Location: signalrank_telegram/commands.py
- Fix: Expand status filters to include 'issued', 'open', 'active'

### Issue 4: PostgreSQL "Too Many Clients" Errors
- Location: db/session.py
- Fix: Ensure proper pooling config with pool_size=15, max_overflow=5

### Issue 5: No Timeframe Data
- Location: data/providers.py
- Fix: Add clean_tf_and_symbol method for proper formatting

### Issue 6: Dynamic Threshold Not Working
- Location: ml/dynamic_threshold.py
- Fix: Change return statement from `return base` to `return adjusted`

### Issue 8: Command Handler Registration
- Location: signalrank_telegram/bot.py
- Fix: Ensure all commands are properly registered

## Additional Updates Requested:
1. Broker Map Update - Add BROKER_MAP and resolve_broker_prefix in commands.py
2. Market Hours Verification Engine - Add is_market_session_open in data/market_hours.py or engine/core.py

## Implementation Steps:
1. [ ] Fix Issue 1 & 7 - audit_recent alias
2. [ ] Fix Issue 2 - dynamic max score calculation
3. [ ] Fix Issue 3 - expanded status filters
4. [ ] Fix Issue 4 - connection pooling
5. [ ] Fix Issue 5 - timeframe formatting
6. [ ] Fix Issue 6 - dynamic threshold return
7. [ ] Fix Issue 8 - command registration (verify existing)
8. [ ] Implement Broker Map
9. [ ] Implement Market Hours Verification
