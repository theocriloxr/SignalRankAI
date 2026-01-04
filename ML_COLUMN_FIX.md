# ML Probability Column Migration Fix

## Issue
Railway PostgreSQL doesn't have the `ml_probability` column yet, causing these errors:
```
UndefinedColumnError: column signals.ml_probability does not exist
```

## Solution (Automatic)

The bot now has **automatic fallback** in startup sequence:

1. **db/auto_ops.py** - Checks if column exists during boot, adds it if missing
2. **db/pg_features.py** - Creates Signal objects gracefully even if column missing

When you restart on Railway, the column will be auto-created.

## Solution (Manual if needed)

If you need to apply immediately without restarting, run in Railway PostgreSQL console:

```sql
ALTER TABLE signals ADD COLUMN IF NOT EXISTS ml_probability FLOAT;
```

Or run the Python fix script:
```bash
python fix_ml_column.py
```

## Expected Behavior After Fix

- ✅ Signals now save `ml_probability` from ML model (0-100%)
- ✅ `/signal`, `/signals`, `/outcome` commands show ML Score
- ✅ No more `UndefinedColumnError` on dispatch
- ✅ Bot logs should show signals being generated and sent

## Verification

Check logs for:
```
[engine] cycle=1 assets_split crypto=5 fx=0
[bot] dispatch reserve failed  <-- Should NOT see this anymore
```
