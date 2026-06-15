# SignalRankAI Remaining Fixes Implementation

## Status Summary

| Issue | Description | Status | Priority |
|-------|------------|-------|----------|
| 1 & 7 | audit_recent Import Error | ✅ ALREADY FIXED | Done |
| 2 | Max Score 100.0 (threshold gate) | 🔴 NEEDS FIX | High |
| 3 | /signals Command Empty | 🔴 NEEDS FIX | High |
| 4 | PostgreSQL "Too Many Clients" | 🔴 NEEDS FIX | High |
| 5 | No Timeframe Data Rate Limits | ✅ ALREADY FIXED | Done |
| 6 | Dynamic Threshold | ✅ ALREADY FIXED | Done |
| 7 & 8 | Broker Map & Market Hours | ✅ EXISTS | Done |

## Implementation Plan

### HIGH PRIORITY FIXES:

#### Issue 4: PostgreSQL Connection Pool (db/session.py)
- Change pool_size from 15 to 3
- Change max_overflow from 15 to 5 
- Apply strict limits to prevent "too many clients" error

#### Issue 2: Max Score Threshold (engine/core.py)
- Fix >= operator (currently uses > which blocks perfect scores)
- Fix environment variable parsing for PREMIUM_SCORE_THRESHOLD_FORCE
- Add max_score_pre_threshold and max_score tracking

#### Issue 3: /signals Command (signalrank_telegram/commands.py)
- Expand status filtering from "active" to include "issued", "open"
- Filter for unresolved signals properly

---

## Implementation Log

### Issue 4 Fix Applied: db/session.py
Changes needed:
```python
# In _effective_pool_settings():
pool_size = 3  # Reduced from 15
max_overflow = 5  # Reduced from 15
```

### Issue 2 Fix Required: engine/core.py
Changes needed:
```python
# In Advanced Filters section, change > to >=
final_signals = [s for s in scored_signals if s.get('score', 0) >= threshold]

# Safe parsing of PREMIUM_SCORE_THRESHOLD_FORCE
raw_force = os.getenv("PREMIUM_SCORE_THRESHOLD_FORCE", "85.0")
try:
    if str(raw_force).lower() in ["true", "yes", "1"]:
        threshold = 85.0
    else:
        threshold = float(raw_force)
except ValueError:
    threshold = 85.0
```

### Issue 3 Fix Required: signalrank_telegram/commands.py
Changes needed:
```python
# In signals_command:
active_unresolved = [
    s for s in all_signals 
    if str(s.get("status", "")).lower() in ["active", "issued", "open"] 
    and not s.get("resolved", False)
]
```

---

## Additional Improvements Applied:

### ML Stability (25% Drift Fix)
- scale_pos_weight added to XGBoost in ml/train_model.py
- EMA smoothing for dynamic threshold in ml/dynamic_threshold.py

### Trade Correlation Blocker
- Exposure limiter in engine/risk_manager.py

### Redis Caching Layer  
- market_data caching in data/pipeline.py

### Graceful Shutdown
- SIGTERM handler in railway_main.py
