# ML Performance Fix Plan

Based on the analysis of the codebase and logs, here are the steps to fix the ML performance issues:

## Summary of Findings

The codebase already has most fixes in place:
1. ✅ SQL files created: add_signal_id_to_ml_rejected_signals.sql, fix_created_at_column.sql, fix_outcomes_constraint.sql
2. ✅ ML logging in core.py is properly structured 
3. ✅ shadow_outcome_worker.py syntax is correct
4. ✅ stats_manager.py properly tracks engine metrics
5. ✅ db/models.py already has signal_id in MLRejectedSignal

## What needs to be done

### 1. Database Migrations (Run on Railway)

Execute these SQL commands in Railway PostgreSQL console:

```sql
-- Add unique constraint to outcomes table
ALTER TABLE outcomes ADD CONSTRAINT unique_signal_id UNIQUE (signal_id);

-- Add signal_id to ml_rejected_signals table
ALTER TABLE ml_rejected_signals ADD COLUMN IF NOT EXISTS signal_id VARCHAR(36);

-- Add created_at to signal_deliveries
ALTER TABLE signal_deliveries ADD COLUMN IF NOT EXISTS created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;
```

### 2. Update .env for Better Provider Fallback

Ensure proper provider priority in .env:
```
DEFAULT_CRYPTO_PROVIDER=binance
DEFAULT_FX_PROVIDER=yahoo
DEFAULT_STOCK_PROVIDER=yahoo
POLYGON_API_KEY=  # Only use if needed, rate limits are strict
```

### 3. Restart Services on Railway

After SQL fixes:
1. Restart "Engine" service
2. Restart "Worker" service
3. Check logs for "[engine] heartbeat: cycle=1 running"

### 4. Verify Shadow Tracker

Check that shadow_outcome_worker is running:
- Should see logs like "[shadow_tracker] started"
- Should see "[shadow_tracker] Wrote ml_shadow_predictions"

## Expected Results After Fix

- Total Scanned: > 0 (engine not paralyzed)
- Delivered: > 0 (signals being sent)
- Shadow tracked: > 0 (rejected signals being monitored)
- ML Drift: Stabilizing as rejected signals feed back into training

## Troubleshooting

If still seeing issues:
1. Check engine logs for "cycle=1 running" - if missing, engine not starting
2. Check for database connection errors
3. Verify provider rate limits not triggered
