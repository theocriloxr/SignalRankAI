# SignalRankAI Implementation Fixes

## Active Task: Fix ML Rejected Signals and Shadow Tracker Tables

### Issues Identified:
1. `persist_rejection()` uses `session.flush()` instead of `session.commit()` - causes silent rollback
2. Missing `signal_id` parameter in `persist_rejection()` 
3. Engine core.py may not be calling persist_rejection correctly
4. Shadow tracker imports may fail if realtime_outcome_tracker functions don't exist

### Fix Plan:

- [ ] Fix 1: Add `await session.commit()` to persist_rejection() in signal_deduplicator.py
- [ ] Fix 2: Add signal_id parameter to persist_rejection()
- [ ] Fix 3: Verify engine core.py calls persist_rejection with correct params
- [ ] Fix 4: Add safety checks in shadow_outcome_worker.py for missing imports

### Completed:
- [x] Analyzed codebase structure
- [x] Reviewed db/models.py for MLRejectedSignal and MLShadowPrediction tables
- [x] Reviewed signal_deduplicator.py for MLRejectionTracker class
- [x] Reviewed shadow_outcome_worker.py
- [x] Reviewed worker/worker.py for worker registration
