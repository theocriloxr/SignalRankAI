# TODO: Fix Pulse Report - State Synchronization Disconnect

## Issue
- Trade opened: FILUSDT long - but Engine Pulse says "Total Scanned: 0"
- Engine is working (opening trades) but Reporter sees empty variables
- Database tables not filling due to missing commit() + new Vetoes

## 4-Phase Fix Plan

### Phase 1: Create GlobalStats class (engine/stats_manager.py) ✅ IN PROGRESS
- GlobalStats class to track scanned/vetoed/delivered across app
- Import stats in core.py process_assets loop
- Increment counters at each stage

### Phase 2: Fix Commit Issue (repository.py) ⏳
- Add db.commit() to persist_decision_log()
- Ensure data persists with NullPool

### Phase 3: Update Pulse Report (admin_pulse.py) ⏳
- Pull from GlobalStats instead of empty DB
- Add DB fallback for backward compatibility

### Phase 4: Add Circuit Breaker Debug Logging (core.py) ⏳
- Log market health check result
- Explain why Scanned = 0 if health check fails
