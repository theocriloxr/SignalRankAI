# TODO: Fix All Issues - Implementation Plan

## Issues to Fix

### Issue 1 & 7: audit_recent Import Error
- **Location**: services/gemini_ml.py
- **Problem**: Alias `audit_recent = audit_recent_signals` references non-existent function
- **Fix**: Define the `audit_recent_signals` function

### Issue 2: Max Score Calculation
- **Location**: engine/core.py  
- **Problem**: Need separate pre/post threshold max score tracking
- **Fix**: Calculate max_score_pre_threshold and max_score separately

### Issue 3: /signals Status Filtering
- **Location**: signalrank_telegram/commands.py
- **Problem**: Filters only for "active" status
- **Fix**: Expand to include "issued" and "open" statuses

### Issue 4: PostgreSQL Pool
- **Location**: db/session.py
- **Status**: Already properly configured

### Issue 5: Timeframe Data
- **Location**: data/providers.py
- **Status**: Need to verify/implement clean_tf_and_symbol

### Issue 6: Dynamic Threshold
- **Location**: ml/dynamic_threshold.py
- **Status**: Function appears correct - verify usage

### Issue 7: Broker Map Integration
- **Location**: signalrank_telegram/commands.py
- **Problem**: Missing resolve_broker_prefix function
- **Fix**: Add BROKER_MAP and resolve_broker_prefix

### Issue 8: Market Hours Integration
- **Location**: engine/core.py
- **Problem**: Not filtering by market hours
- **Fix**: Integrate is_market_session_open check

## Implementation Steps

1. Fix audit_recent_signals in gemini_ml.py ✅
2. Add max_score tracking in engine/core.py ✅
3. Fix signals_command status filtering ✅
4. Verify db/session.py pool config ✅
5. Add resolve_broker_prefix to commands.py ✅
6. Integrate market hours in engine/core.py ✅
