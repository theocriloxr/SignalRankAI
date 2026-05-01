# SignalRankAI ImportError Fix: cannot import name 'Signal' from 'db.models'

Status: **IN PROGRESS** ✅

## Approved Plan Summary
**Root cause**: ImportError on Signal model definition (PGUUID dialect race in Railway container).

**Files to edit**:
1. `db/models.py` - Add dialect imports + error wrapping
2. `railway_main.py` - Add pre-import dialect check
3. `db/repository.py` - No changes needed

**Follow-up**:
- Test: `uvicorn railway_main:app --reload`
- Deploy to Railway
- Verify Alembic: `alembic upgrade head`
- Test all imports/functions

## Step-by-Step Implementation

### ✅ Step 1: Create this TODO.md [COMPLETE]

### ⏳ Step 2: Edit db/models.py
- Add explicit dialect imports
- Wrap Signal class definition with try/except logging
```
Use edit_file tool with exact diffs
```

### ⏳ Step 3: Edit railway_main.py  
- Add SQLAlchemy PostgreSQL dialect precheck before `from web.app import app`
```
Use edit_file tool with exact diffs
```

### ⏳ Step 4: Test imports locally
```
cd c:/Users/sammm/Desktop/SignalRankAI
python -c "from db.repository import *; print('✅ repository imports OK')"
uvicorn railway_main:app --host 0.0.0.0 --port 8001 --reload
```

### ⏳ Step 5: Verify database schema
```
alembic upgrade head
python verify_system.py
```

### ⬜ Step 6: Deploy & test Railway [PENDING]
```
railway up
Check logs for import success
Test /health endpoint
```

### ⬜ Step 7: Run full tests [PENDING]
```
pytest
python test_all_features.py
python test_all_functions.py
```

### ⬜ Step 8: Mark COMPLETE [PENDING]
```
- Update this TODO.md ✅
- attempt_completion
```

