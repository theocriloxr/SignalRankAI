# SignalRankAI Issue Fix Plan - V2

## Issues to Fix (Based on Task Analysis)

### Issue 1 & 7: audit_recent Import Error
**Location:** services/gemini_ml.py and signalrank_telegram/commands.py
**Problem:** Function naming mismatch - needs alias export

### Issue 2: Max Score Hardcoded
**Location:** engine/core.py
**Problem:** max_score and max_score_pre_threshold hardcoded to 100.0

### Issue 3: /signals Returns Empty  
**Location:** signalrank_telegram/commands.py
**Problem:** Query filters strictly for status==active but system uses 'issued'/'open'

### Issue 4: PostgreSQL "Too Many Clients"
**Location:** db/session.py
**Problem:** Connection pooling not optimal

### Issue 5: No Timeframe Data
**Location:** data/providers.py
**Problem:** Missing timeframe formatting mapping

### Issue 6: Dynamic Threshold Not Working
**Location:** ml/dynamic_threshold.py
**Problem:** Returns base instead of adjusted value

### Issue 8: Command Handler Registration
**Location:** signalrank_telegram/bot.py
**Problem:** Missing command registrations

## Additional Requests
- Broker Map Update
- Expanded Asset Classes
- Global Market Hours Verification

---
