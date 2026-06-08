# ✅ ML Performance Fix - Implementation Checklist

## Code Status: COMPLETE ✅
All code fixes are already in place:
- ✅ SQL migration files ready
- ✅ core.py ML logging properly structured  
- ✅ shadow_outcome_worker.py syntax correct
- ✅ stats_manager.py tracking metrics
- ✅ db/models.py has signal_id column

---

## Step 1: Run SQL on Railway PostgreSQL Console

Execute these 3 commands in order:

```sql
-- Fix 1: Add unique constraint to outcomes (enables UPSERT)
ALTER TABLE outcomes ADD CONSTRAINT unique_signal_id UNIQUE (signal_id);

-- Fix 2: Add signal_id to ml_rejected_signals (for ML training)
ALTER TABLE ml_rejected_signals ADD COLUMN IF NOT EXISTS signal_id VARCHAR(36);

-- Fix 3: Add created_at to signal_deliveries (for Pulse reporting)
ALTER TABLE signal_deliveries ADD COLUMN IF NOT EXISTS created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;
```

---

## Step 2: Update .env Configuration

Change/add these values:
```
DEFAULT_CRYPTO_PROVIDER=binance
DEFAULT_FX_PROVIDER=yahoo
DEFAULT_STOCK_PROVIDER=yahoo

# Optional: comment out or reduce Polygon usage
# POLYGON_API_KEY=${POLYGON_API_KEY}  # Only 5/min, use as last resort
```

---

## Step 3: Restart Railway Services

1. **Stop** both "Engine" and "Worker" services
2. **Start** "Engine" service first
3. **Start** "Worker" service
4. Wait 60 seconds for first cycle

---

## Step 4: Verify in Railway Logs

Search for these log entries:

| Entry | Meaning | Status |
|-------|---------|--------|
| `[engine] heartbeat: cycle=1 running` | Engine started | ✅ GOOD |
| `[engine] pipeline: starting asset=` | Scanning assets | ✅ GOOD |
| `Total Scanned: X` | Not zero | ✅ GOOD |
| `[shadow_tracker] started` | Shadow worker running | ✅ GOOD |
| `Delivered: X` | Signals sent | ✅ GOOD |

---

## Expected Results After Fix

- **Total Scanned**: > 0 (engine not paralyzed)
- **Delivered**: > 0 (signals being sent successfully)  
- **Shadow tracked**: > 0 (rejected signals monitored for ML)
- **ML Drift**: Stabilizing as rejected signals feed into training

---

## Troubleshooting If Issues Persist

1. **No heartbeat**: Check engine startup errors
2. **Scanned = 0**: Database connection issue - check credentials
3. **Provider errors**: Check .env provider settings
4. **Rate limits**: Polygon blocked - switch to binance/yahoo

---

*Generated: SignalRankAI ML Fix Summary*
