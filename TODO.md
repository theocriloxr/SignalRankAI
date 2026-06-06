# SignalRankAI Bug Fixes and Upgrades TODO

## ✅ Completed Tasks

### Bug A: Engine Indentation Error (FIXED)
- Fixed indentation at `pipeline_stats` in engine/core.py
- Now properly indented with 8 spaces

### Bug B: ML Data Leakage (TODO)
- Need to remove `partial_tp_progress_norm` from feature_cols in ml/train_model.py
- This feature leaks the trade outcome into training data

### Major Upgrades (TODO)
- Create engine/news_filter.py (News Killswitch)
- Create services/gemini_ml.py (Gemini Agentic Validator)

## Current Issues Identified

### core.py await Syntax Error
The code has:
```python
_is_allowed = await exposure_manager.is_trade_allowed(...)
```
This is inside a non-async for loop in main_loop(), causing "SyntaxError: 'await' outside async function"

### Fix Required
Need to wrap the async call using run_sync or make it properly async:
```python
_is_allowed = run_sync(
    exposure_manager.is_trade_allowed(
        None,
        _sig_asset_cls,
        _direction,
    )
)
```

## Progress Tracking

- [x] Analyzed codebase
- [ ] Fix Bug A (indentation in core.py)  
- [ ] Fix Bug B (ML data leakage in train_model.py)
- [ ] Create engine/news_filter.py
- [ ] Create services/gemini_ml.py
- [ ] Integrate upgrades into core.py
