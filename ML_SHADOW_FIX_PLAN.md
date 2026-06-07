# ML Shadow Tracker Fix Plan

## Problem Analysis

After analyzing the codebase, I've identified that the `ml_rejected_signals` and `ml_shadow_predictions` tables are not being filled properly due to issues in the data flow between the engine, the rejection tracker, and the shadow worker.

## Current Implementation Issues

### 1. ml_rejected_signals - Issues Identified:

1. **In `engine/core.py`**: The MLRejectionTracker is only called when signals are rejected by:
   - ML filter (soft threshold)
   - ML hard filter 
   - Final score gate
   - Expectancy gate
   - Gemini gate

2. **Problem**: In some cases, the rejection is being tracked via `_log_decision()` but the `persist_rejection()` call may fail silently due to:
   - Missing `await session.commit()` in some paths
   - Exception handling that silently catches errors
   - The rejection may not always have all required fields populated

3. **Key Finding**: Looking at `signal_deduplicator.py`, the `MLRejectionTracker.persist_rejection()` method DOES have proper commit logic, but it requires:
   - `entry_price > 0`
   - `stop_loss > 0`
   - Valid `take_profit_levels`

### 2. ml_shadow_predictions - Issues Identified:

1. **In `engine/shadow_outcome_worker.py`**: The worker is implemented but has a fundamental issue:
   - It queries for `MLRejectedSignal.outcome_tracked_at.is_(None)` 
   - But it only writes to `ml_shadow_predictions` when there's a "hit" outcome
   - This means shadow predictions are only created retroactively, not when signals are initially rejected

2. **Missing**: When a signal is initially rejected by ML, we should immediately create a shadow prediction record with the ML's probability, then update it when the outcome is determined.

## Implementation Plan

### Step 1: Fix ml_rejected_signals population in engine/core.py

The engine should ensure ALL rejections are properly saved. Looking at the code, I see:

1. `_log_decision()` is called for rejections and already attempts to persist rejections via `_ml_rejection_tracker.persist_rejection()`
2. BUT there may be issues with specific rejection paths not calling this

### Step 2: Ensure ml_shadow_predictions is populated at rejection time

**Key Fix**: When a signal is rejected by ML, we should immediately write a shadow prediction record, not wait for the shadow worker to do it later. This ensures:
- We track what the ML model predicted at the time of rejection
- We can compare predictions vs actual outcomes

### Step 3: Fix the shadow_outcome_worker.py to properly track all rejected signals

The worker should:
1. Query all rejected signals without outcome
2. For each, fetch live price and check if SL/TP hit
3. Update the ml_shadow_predictions table with actual outcome

## Required Changes

### 1. In `engine/signal_deduplicator.py` - Enhance MLRejectionTracker:

```python
# Add method to create shadow prediction at rejection time
async def create_shadow_prediction_at_rejection(
    self,
    signal_id: str,
    asset: str,
    timeframe: str,
    direction: str,
    entry: float,
    stop_loss: float,
    take_profit: float,
    ml_probability: float,
    rejection_reason: str,
    features: Dict[str, Any],
) -> Optional[MLShadowPrediction]:
```

### 2. In `engine/core.py` - Ensure all rejections are tracked:

- Add explicit tracking for ALL rejection paths
- Include signal_id in the rejection record

### 3. In `engine/shadow_outcome_worker.py` - Fix outcome tracking:

- Ensure proper connection handling
- Add retry logic for failed operations

## Execution Order

1. First: Verify current state by checking if tables exist and have data
2. Fix MLRejectionTracker to create shadow predictions at rejection time
3. Fix engine/core.py to properly call rejection tracker for ALL rejection paths
4. Fix shadow_outcome_worker.py to properly track and update outcomes
5. Verify the fix works by running the engine and checking tables
