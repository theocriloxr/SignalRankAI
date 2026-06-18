# SignalRankAI - Comprehensive Fix Implementation Plan

This plan addresses the critical issues identified from logs analysis.

## Issue Analysis & Root Causes

### 1. DYNAMIC THRESHOLD BUG - HIGH PRIORITY ✅ IDENTIFIED

**Log Symptom:**
```
[ml] Dynamic threshold:
base=0.50
current_auc=0.51
target=0.85
-> adjusted=0.40
(clamped to 0.40)
```

**Root Cause:** 
- `calculate_dynamic_threshold()` called every cycle, never persisted
- Hard-coded floor at 0.40 blocks all threshold adjustments
- AUC 0.51 = model is guessing (coin flip)
- Logs are noisy - same value repeated every cycle

**Affected Files:**
- `ml/dynamic_threshold.py` - hard clamp at 0.40
- `engine/core.py` _current_ml_prob_threshold() - no persistence

### 2. AUDUSD PRICING BUG (4430% drift) - CRITICAL ✅ IDENTIFIED

**Log Symptom:**
```
Signal INVALIDATED for AUDUSD:
entry=0.01570
live=0.71124
drift=4430.15%
```

**Root Cause:** FX price scaling error - 0.71124 becoming 0.01570

**Affected Files:**
- data providers (normalization)
- signal formatter

### 3. SIGNAL STATUS MISMATCH - HIGH PRIORITY ✅ IDENTIFIED

**Log Symptom:**
```
"No active unresolved signals in your range right now"
while signals clearly exist (trade opened: AUDUSD, SOLUSDT...)
```

**Root Cause:** Status definition mismatch
- Engine stores: `status = 'issued'`
- Command queries: `status = 'active'`

**Affected Files:**
- signalrank_telegram/commands.py - query logic
- signalrank_telegram/signal_commands.py

### 4. BRENT PROVIDER FAILURES - MEDIUM PRIORITY

**Log Symptom:**
```
No timeframe data for BRENT
twelvedata fetch_failed
polygon 429
```

**Root Cause:** No fallback chain, rate limits hit

### 5. SIGNAL LOSS AFTER RISK - MEDIUM PRIORITY

**Log Symptom:**
```
risk_passed=16
final_signals=14
stored=5
dropped=11
```

**Root Cause:** Multiple gates (cooldown, duplicate, portfolio exposure)

---

## Implementation Plan

### Phase 1: DYNAMIC THRESHOLD FIX (Critical)

#### Step 1.1: Remove Hard Floor Clamp
File: `ml/dynamic_threshold.py`

Current code:
```python
# HARD CLAMP: Prevent threshold from climbing too high when model degrades
final_threshold = min(final_threshold, 0.40)
```

Change to: Allow dynamic adjustment with proper bounds
- MIN_THRESHOLD = 0.10
- MAX_THRESHOLD = 0.85
- Remove hard clamp

#### Step 1.2: Add Persistence
File: `engine/threshold_optimizer.py`

Add Redis persistence for thresholds by asset class:
```
ml:threshold:crypto
ml:threshold:fx
ml:threshold:stocks
ml:threshold:commodities
```

#### Step 1.3: Add Cooldown
Only recalculate every:
- 100 outcomes OR
- 6 hours

Add hysteresis: MIN_CHANGE = 0.03 before threshold changes

#### Step 1.4: Fix Logging
Only log at INFO when threshold CHANGES
Otherwise log at DEBUG

#### Step 1.5: Disable When Model is Bad
If AUC < 0.60, disable dynamic adaptation
Focus on data quality first

---

### Phase 2: AUDUSD PRICING FIX (Critical)

#### Step 2.1: Find Root Cause
Search for:
- pip_value
- point_value  
- pip conversion
- decimal normalization around FX

#### Step 2.2: Fix Normalization
Ensure 0.71124 stays 0.71124
Never scale by 10000 or pips

#### Step 2.3: Add Validation
Before storing signal, verify:
- price within 50% of live price
- else reject/rebuild

---

### Phase 3: SIGNAL STATUS FIX (High Priority)

#### Step 3.1: Unify Status Definition
Create shared constant:
```python
ACTIVE_STATUSES = {"issued", "active", "open"}
```

Use everywhere, not hard-coded strings

#### Step 3.2: Fix /signals Query
File: `signalrank_telegram/signal_commands.py`

Query using ACTIVE_STATUSES instead of fixed values

#### Step 3.3: Add Command Audit
At startup, verify all help commands have handlers

---

### Phase 4: BRENT FALLBACK FIX

#### Step 4.1: Add Yahoo Fallback
In provider chain for commodities

#### Step 4.2: Add Cache Fallback
Use last known good price

#### Step 4.3: Mark Asset Health
Redis: asset_health["BRENT"] = "DEGRADED"

---

### Phase 5: SIGNAL LOSS TELEMETRY

#### Step 5.1: Log Rejection Reasons
Add to pipeline_stats:
```
dropped_after_risk=11
rejection_reasons={
    "cooldown": 5,
    "duplicate": 2,
    "portfolio_exposure": 4
}
```

#### Step 5.2: Add /diag Command
Admin only, shows full pipeline breakdown

---

## Verification Checklist

### Dynamic Threshold
- [ ] No more "clamped to 0.40" spam
- [ ] Threshold persists across restarts
- [ ] Logs only when value changes
- [ ] Per-asset-class thresholds work

### AUDUSD
- [ ] No more 4430% drift
- [ ] Entry price matches live

### Signals Command
- [ ] /signals shows active signals
- [ ] Commands in /help all work

### BRENT
- [ ] Data available
- [ ] Fallback works

---

## Files to Modify

1. `ml/dynamic_threshold.py` - Remove hard clamp, add persistence
2. `engine/core.py` - Use persisted thresholds
3. `engine/threshold_optimizer.py` - Add Redis persistence
4. `signalrank_telegram/signal_commands.py` - Fix status query
5. `signalrank_telegram/commands.py` - Add status constants
6. Data providers - Fix AUDUSD normalization

---

## Implementation Order

1. Dynamic Threshold Persistence (Biggest Impact)
2. Status Fix (User-Facing)
3. AUDUSD (Data Quality)
4. BRENT Fallback (Reliability)
5. Telemetry (Observability)
