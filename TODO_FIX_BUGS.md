# SignalRankAI Bug Fixes - Implementation Plan

## Summary of Analysis:

### Already Fixed (No Action Needed):
1. ✅ Duplicate Trade Bug - Implemented in core.py ~line 1845-1870
2. ✅ API Rate Limits - Implemented in fetcher.py (macro caching with 1hr TTL)
3. ✅ Stats Import - Correct (both core.py and admin_pulse.py import from engine.stats_manager)
4. ✅ ML Veto Counter - Already added (stats.vetoed_ml += 1)
5. ✅ Score Veto Counter - Already added (stats.vetoed_score += 1)

### Need to Execute:
1. ⏳ Run SQL for missing created_at column in signal_deliveries
2. ⏳ Find and add squeeze veto counter (if squeeze filtering is active)

## Implementation Steps:

### Step 1: Run SQL for missing created_at column
```sql
ALTER TABLE signal_deliveries ADD COLUMN IF NOT EXISTS created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;
```

### Step 2: Check for squeeze filtering usage in core.py
The SqueezeDetector is imported but may not be actively used in the main loop.
If active, add stats.vetoed_squeeze += 1 at the appropriate rejection point.

## Status: Ready to Execute
