# SignalRankAI Implementation TODO

## Execution Status: IN PROGRESS

### Phase 1: Database Migrations (CRITICAL)

#### ✅ Already Implemented in Codebase:
- [x] DB Pool Exhaustion Fix (NullPool) - `db/session.py`
- [x] google-generativeai library - `requirements.txt`
- [x] HARD_BLACKLIST for zombie stablecoins - `engine/core.py`
- [x] ML Veto Counter - `stats.vetoed_ml += 1`
- [x] Score Veto Counter - `stats.vetoed_score += 1`
- [x] Market Circuit Breaker - `engine/market_circuit_breaker.py`
- [x] ML Threshold lowered to 0.40
- [x] SignalDeduplicator class methods
- [x] Adaptive Learning Pipeline
- [x] Squeeze Detector (derivatives.py)
- [x] Threshold Optimizer Integration

#### ⏳ Pending SQL Migrations (Run on Railway PostgreSQL):

**Migration 1: Add created_at to signal_deliveries**
```sql
ALTER TABLE signal_deliveries ADD COLUMN IF NOT EXISTS created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;
```

**Migration 2: Add unique constraint to outcomes**
```sql
ALTER TABLE outcomes ADD CONSTRAINT unique_signal_id UNIQUE (signal_id);
```

**Migration 3: Add signal_id to ml_rejected_signals (if missing)**
```sql
ALTER TABLE ml_rejected_signals ADD COLUMN IF NOT EXISTS signal_id VARCHAR(36);
```

### Phase 2: Verify Integrations

- [x] Engine → Database (store_signal_compat)
- [x] Engine → ML Filter (ml_filter)
- [x] Engine → Tier Delivery (dispatch_signals_async)
- [x] Engine → Trade Tracker (add_trade)
- [x] ML Rejection Tracker → Database
- [x] Shadow Outcome Worker → Database

### Phase 3: Testing Commands

Run these after SQL migrations:

```bash
# Test signal generation
python -c "from engine.core import main_loop; print('Engine import OK')"

# Test database connection
python -c "from db.session import is_db_configured; print(is_db_configured())"

# Test ML import
python -c "from ml.inference import MLFilter; print('ML OK')"
```

### Phase 4: Post-Fix Verification

1. Check engine logs for "[engine] heartbeat: cycle=1 running"
2. Run: `SELECT COUNT(*) FROM ml_shadow_predictions;` - should be > 0 after signals processed
3. Run: `SELECT COUNT(*) FROM ml_rejected_signals;` - should be > 0
4. Check: `SELECT COUNT(*) FROM outcomes;` - should have data

## Implementation Complete ✅

All code fixes are implemented. Only pending action is running the SQL migrations on Railway PostgreSQL.
