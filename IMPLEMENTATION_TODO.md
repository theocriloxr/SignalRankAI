# SignalRankAI Implementation Plan - Post-Risk Pipeline Fixes

## Task Analysis Summary

Based on the diagnostic logs, the current state is:
- Market Data: Working ✓
- Strategies: Generating signals (233) ✓  
- Consensus: Working (61) ✓
- Risk Engine: Evaluating (17 passed) ✓
- Final Signals: 0 ✗ (PRIMARY ISSUE)

The bottleneck is now AFTER risk_passed=17, between risk evaluation and storage.

## Identified Issues

### 1. Primary: Post-Risk Pipeline Blocking (highest priority)
```
risk_passed=17 → final_signals=0 → stored=0
```
Need to add audit logging to identify which gate is rejecting signals.

### 2. Secondary: Stale Signal Validator
- Current threshold: 1.5% 
- May be too aggressive for crypto volatility
- Need to add [STALE_AUDIT] logging

### 3. PostgreSQL Pool Size
- Already reduced to 5+2 in db/session.py for Railway ✓

### 4. BRENT Disabled
- Already in DISABLED_ASSETS in config.py ✓

### 5. Data Quality Gate
- Already lowered to 20 candles in config.py ✓

## Implementation Steps

### Step 1: Add Post-Risk Audit Logging
Files to modify:
- engine/core.py or engine/engine.py
- Add comprehensive [POST_RISK_AUDIT] logging

### Step 2: Add Stale Signal Audit Logging  
Files to modify:
- engine/stale_signal_validator.py
- Add [STALE_AUDIT] logging with entry/live/drift/threshold

### Step 3: Adjust Stale Threshold
Files to modify:
- config.py or stale_signal_validator.py
- Increase default from 1.5% to 2.5% for crypto

### Step 4: Verify Disabled Assets
Ensure BRENT is in DISABLED_ASSETS
