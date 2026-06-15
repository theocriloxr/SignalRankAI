# TODO: Fix All Issues - FINAL Implementation Plan

## Summary of Issues and Fixes

### Issue 1 & 7: audit_recent Import Error
**Location**: services/gemini_ml.py
**Problem**: `audit_recent = audit_recent_signals` alias but function doesn't exist
**Fix**: Add the `audit_recent_signals` async function

### Issue 2: Max Score 100.0
**Location**: engine/core.py
**Problem**: Need separate pre/post threshold max score calculation
**Fix**: Calculate both max_score_pre_threshold and max_score from candidates

### Issue 3: /signals Command Returns Empty
**Location**: signalrank_telegram/commands.py - signals_command
**Problem**: Filters only for status=="active"
**Fix**: Expand to include "issued" and "open" statuses

### Issue 4: PostgreSQL "Too Many Clients"
**Location**: db/session.py
**Status**: Already properly configured ✅

### Issue 5: No Timeframe Data
**Location**: data/providers.py  
**Status**: Need to check clean_tf_and_symbol

### Issue 6: Dynamic Threshold
**Location**: ml/dynamic_threshold.py
**Status**: Already correct ✅

### Issue 7: Broker Map
**Location**: signalrank_telegram/commands.py
**Status**: Need resolve_broker_prefix function

### Issue 8: Market Hours
**Location**: engine/core.py
**Status**: Need is_market_session_open check

## Implementation Steps

### Step 1: Fix gemini_ml.py - Add audit_recent_signals function
Add after line ~500 (after other functions):
```python
async def audit_recent_signals(session, limit: int = 10) -> dict:
    """Audit recent losses and rejections for analysis."""
    # Implementation here
```

### Step 2: Fix commands.py - signals_command status filtering
Expand status filter in signals_command:
```python
active_unresolved = [
    s for s in all_signals 
    if str(s.get("status", "")).lower() in ["active", "issued", "open"] 
    and not s.get("resolved", False)
]
```

### Step 3: Add resolve_broker_prefix function
Add BROKER_MAP and resolve_broker_prefix to commands.py

### Step 4: Integrate market hours in engine
Add is_market_session_open check in engine/core.py
