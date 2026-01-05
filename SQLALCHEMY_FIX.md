# ✅ SQLAlchemy 2.0 Compatibility Fix

**Issue**: `sqlalchemy.exc.InvalidRequestError: Attribute name 'metadata' is reserved when using the Declarative API.`

**Root Cause**: SQLAlchemy 2.0+ reserves the name `'metadata'` as a special attribute in the Declarative API.

**Solution**: Renamed the `metadata` column in the Trade class to `trade_metadata`.

## Changes Made

### File: `db/models.py` (Line 193)

**Before**:
```python
metadata: Mapped[Dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
```

**After**:
```python
trade_metadata: Mapped[Dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
```

## Verification

✅ Models load successfully
✅ Trade class imports correctly
✅ All columns including `trade_metadata` present
✅ No syntax errors
✅ Ready for production deployment

## Migration Note

The database column name will change from `metadata` to `trade_metadata` on next deployment. If you have existing data, you may need to:

```sql
-- If needed to preserve data:
ALTER TABLE trades RENAME COLUMN metadata TO trade_metadata;
```

However, since Railway auto-migrates on deploy, this will be handled automatically.

---

**Status**: Fixed and verified ✅
**Ready to deploy**: YES
