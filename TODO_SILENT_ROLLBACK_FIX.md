# TODO: Silent Rollback Fix

## Problem Summary
The engine runs and logs "Trade opened" but data vanishes before hitting the database. This is a "Silent Rollback" caused by PostgreSQL rejecting writes due to missing columns that exist in Python models but not in the actual database schema.

## Root Causes

### 1. IndentationError in engine/core.py
- **Location**: Line ~1048 (`while True:` loop)
- **Issue**: `cycle_no += 1` is not properly indented (missing 4-space indent)
- **Impact**: The signal_engine crashes completely on startup (signal_engine=DISABLED)

### 2. Missing Database Columns
- **Missing columns**: `mfe_pct` and `mae_pct` in both `signals` and `trades` tables
- **Issue**: PostgreSQL rejects INSERT/UPDATE with "column does not exist" error
- **Result**: Database rolls back the entire transaction, tables stay empty

---

## Fix Plan

### Phase 1: Fix IndentationError in engine/core.py
**File**: `engine/core.py`
**Location**: Around line 1048

**Current (WRONG)**:
```python
while True:
cycle_no += 1
```

**Correct (FIXED)**:
```python
while True:
    cycle_no += 1
```

### Phase 2: Add Missing Database Columns
**Option A**: Run SQL in Railway Dashboard Query console
- See file: `FIX_MFE_MAE_COLUMNS.sql`

**Option B**: Run Alembic migration
```bash
# Generate migration
alembic revision --autogenerate -m "add_mfe_mae_columns"

# Apply to database
alembic upgrade head
```

### Phase 3: Expose Silent Errors (Best Practice)
**File**: `db/pg_compat.py` or `db/repository.py`

Add explicit logging to catch rollback errors:
```python
import logging
logger = logging.getLogger("Database")

try:
    db_session.add(new_data)
    await db_session.commit()
except Exception as e:
    await db_session.rollback()
    # CRITICAL: This line will tell you exactly which column is missing
    logger.error(f"🚨 CRITICAL DB ROLLBACK: Failed to save to database: {str(e)}")
```

---

## Verification Steps

After applying fixes:
1. Check Railway logs for "Trade opened" being logged
2. Query database tables to confirm data is persisting
3. Verify no "IndentationError" in startup logs

---

## Files Modified
- `engine/core.py` - Fix indentation
- `FIX_MFE_MAE_COLUMNS.sql` - Database schema fix (created)
- `db/models.py` - Already has mfe_pct/mae_pct in Signal and Trade models (verified)
