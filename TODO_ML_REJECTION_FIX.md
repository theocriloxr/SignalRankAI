# TODO: ML Rejected Signals & Shadow Tracker Fix

## Summary
The ML Rejected Signals and ML Shadow Tracker systems need to be properly connected to start filling the empty tables.

## What Was Working (Preserved)
1. **MLRejectedSignal model** - Already defined in `db/models.py`
2. **MLShadowPrediction model** - Already defined in `db/models.py`  
3. **ShadowOutcomeWorker** - Already implemented in `engine/shadow_outcome_worker.py`
4. **Worker integration** - Shadow tracker starts via `worker/worker.py`

## What Was Fixed
1. **signal_deduplicator.py** - Fixed `_load_runtime_int` method signature
2. **persist_rejection exception handling** - Added proper rollback handling

## What Still Needs Fixing (Structural Issue)

### The Core Problem: Methods Outside Class
In `engine/signal_deduplicator.py`, the following methods are incorrectly defined OUTSIDE the `MLRejectionTracker` class but reference `self`:
- `persist_rejection` - should be `MLRejectionTracker.persist_rejection`
- `_load_runtime_int` - should be `MLRejectionTracker._load_runtime_int`
- `_save_runtime_int` - should be `MLRejectionTracker._save_runtime_int`

### Fix Required
Wrap these as proper class methods inside `MLRejectionTracker`:

```python
class MLRejectionTracker:
    # ... existing __init__ ...
    
    async def persist_rejection(self, ...):
        """Store rejection for future outcome tracking."""
        ...
        
    async def _load_runtime_int(self, key: str, default: int = 0) -> int:
        ...
        
    async def _save_runtime_int(self, key: str, value: int) -> None:
        ...
        
    # ... rest of class methods ...
```

## Engine Integration (Confirmed Working)
The engine in `engine/core.py` already calls:
- `_ml_rejection_tracker.persist_rejection()` on ML rejection
- Decision logging with `_log_decision()`

The calls pass through `run_sync()` correctly, so rejections SHOULD be saved IF the method is callable.

## Shadow Tracker (Already Implemented)
The `ShadowOutcomeWorker` in `engine/shadow_outcome_worker.py`:
- Queries `ml_rejected_signals` with `outcome_tracked_at=None`
- Fetches live prices via `_get_live_price()` 
- Calculates outcomes and writes to `ml_shadow_predictions`
- Updates `actual_outcome` and `outcome_tracked_at` on rejections

This is fully functional - no code changes needed!

## Verification Steps After Class Fix
1. Restart the engine and worker
2. Wait for ML rejections to occur
3. Check: `SELECT COUNT(*) FROM ml_rejected_signals;` - should have rows
4. Wait for shadow tracker cycle (60s default)
5. Check: `SELECT COUNT(*) FROM ml_shadow_predictions;` - should have rows

## If Still Empty After Class Fix
Check logs for:
- "persist_rejection" errors - method not found
- "shadow_tracker" iteration failures - no data to process
- Database connection issues
