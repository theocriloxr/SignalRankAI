# SignalRankAI - Apply All Fixes TODO

## Already Applied ✅
- Issue 1 & 7 - Import Error: `audit_recent_signals` exists in services/gemini_ml.py
- Issue 7 & 8 - Broker Map & Market Hours: utils/market_hours.py exists
- Issue 6 - Dynamic Threshold: returns adjusted value

## To Apply - Implementation Plan

### FIX 1: Fix Import Error (commands.py) ⚠️
- File: signalrank_telegram/commands.py
- Action: Fix import and function call for audit_recent_signals
- Status: NEEDS TO BE DONE

### FIX 2: Max Score 100.0 (core.py) ⚠️
- File: engine/core.py
- Action: 
  - Replace strict inequality (>) with >= 
  - Add safe threshold parsing
  - Calculate real max_scores
- Status: NEEDS TO BE DONE

### FIX 3: /signals Command Status Filter (commands.py) ⚠️
- File: signalrank_telegram/commands.py
- Action: Expand status filter to include "issued", "open"
- Status: NEEDS TO BE DONE

### FIX 4: PostgreSQL Pool Size (session.py) ⚠️
- File: db/session.py
- Action: Limit pool_size=3, max_overflow=5
- Status: NEEDS TO BE DONE

### FIX 5: Rate Limit Semaphore (core.py) ⚠️
- File: engine/core.py
- Action: Implement semaphore waterfall delay
- Status: NEEDS TO BE DONE

## Implementation Steps

- [ ] Step 1: Read signalrank_telegram/commands.py for audit import
- [ ] Step 2: Fix engine/core.py threshold and max_score
- [ ] Step 3: Fix signalrank_telegram/commands.py status filter
- [ ] Step 4: Fix db/session.py pool settings
- [ ] Step 5: Fix engine/core.py semaphore for rate limits

Created: 2025-01-21
Priority: HIGH
