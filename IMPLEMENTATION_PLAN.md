# SignalRankAI - Adaptive Threshold & Signal Generation Implementation Plan

## Task Summary
Based on user's requirements:
1. Auto-adjust confidence thresholds via Gemini and ML over time
2. Increase signal accuracy, win rate, ROI, and risk-reward ratio
3. Ensure continuous signal generation (not stopping after one signal)
4. Fix KeyError: 'sqlalchemy' startup crash

---

## Phase 1: Fix KeyError: 'sqlalchemy' (CRITICAL)

### Current State
The fix is already implemented in `railway_main.py` lines 19-25:
```python
try:
    from sqlalchemy.dialects.postgresql import UUID
    _SQLALCHEMY_POSTGRES_DIALECT_LOADED = True
except ImportError as _e:
    raise ImportError(f"SQLAlchemy PostgreSQL dialect required...")
```

### Additional Safeguards Needed
We need to ensure db/models.py handles this gracefully when imported elsewhere.

**Files to edit**: `db/models.py`

---

## Phase 2: Integrate Adaptive Threshold Optimizer

### Current State
- `engine/threshold_optimizer.py` exists with `AdaptiveThresholdOptimizer` class
- Engine imports it but doesn't actively use it

### Implementation Required

#### Step 1: Update engine/core.py to use threshold optimizer
**Changes**:
1. Initialize optimizer at engine start
2. Refresh thresholds every N cycles
3. Use adaptive threshold in ML filtering

#### Step 2: Connect Gemini ML recommendations to threshold
**Changes**:
1. Modify `services/gemini_ml.py` to include threshold suggestions
2. Parse and apply suggestions in threshold optimizer

#### Step 3: Add threshold bounds and safety limits
**Changes**:
1. Clamp threshold to min/max bounds
2. Add hysteresis to prevent thrashing
3. Log all changes

---

## Phase 3: Ensure Continuous Signal Generation

### Current State
- Engine runs in infinite loop with batch processing
- Signal generation happens once per asset per cycle

### Issues Identified
1. Engine may stop generating signals after finding one strong signal
2. Threshold refresh happens but isn't used in real-time

### Implementation Required

#### Step 1: Continuous threshold-aware signal generation
**Changes**:
1. Get current adaptive threshold BEFORE generating signals
2. Apply threshold in strategy generation loop
3. Track signals generated per cycle

#### Step 2: Signal generation metrics
**Changes**:
1. Log signals generated per cycle
2. Alert on zero-signal cycles
3. Track threshold vs signals generated correlation

---

## Phase 4: Performance Optimization Loop

### Metrics to Track
- Win rate (target: 60%+)
- Average R (target: 1.5R+)
- Signal volume (target: 3+ per cycle)
- Threshold vs outcomes correlation

### Gemini ML Review Integration
- Already collects aggregate performance
- Need to add threshold recommendations
- Parse and apply suggestions

---

## Implementation Order

### Step 1: db/models.py fix (Priority: CRITICAL)
File: `db/models.py`
- Wrap sqlalchemy.dialects import in try-except
- Graceful fallback

### Step 2: Engine threshold integration (Priority: HIGH)
File: `engine/core.py`
- Import threshold optimizer
- Add periodic refresh
- Use in ML filtering

### Step 3: Gemini threshold loop (Priority: HIGH)
File: `services/gemini_ml.py`
- Add threshold recommendations
- Store in runtime_state

### Step 4: Signal generation continuity (Priority: HIGH)
Files: `engine/core.py`, `engine/loop.py`
- Continuous asset processing
- Per-cycle threshold refresh
- Metrics logging

---

## Testing Checklist

- [ ] Startup crash fixed (no KeyError)
- [ ] Threshold adapts weekly based on performance
- [ ] Signals generated every cycle
- [ ] Win rate improves over time
- [ ] Average R improves over time
- [ ] Alert on zero-signal cycles
- [ ] Threshold bounds enforced
- [ ] Gemini recommendations applied

---

## Files Modified

1. `db/models.py` - SQLAlchemy import fix
2. `engine/core.py` - Threshold integration + continuity  
3. `engine/loop.py` - Threshold awareness
4. `services/gemini_ml.py` - Threshold recommendations
5. `engine/threshold_optimizer.py` - Gemini integration
