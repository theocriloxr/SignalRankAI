# TODO: SignalRankAI Improvements

## Task Summary
1. Fix SQLAlchemy import error on Railway (KeyError: 'sqlalchemy')
2. Auto-adjust confidence thresholds via Gemini/ML over time  
3. Ensure consistent signal generation

## Analysis

### Issue 1: SQLAlchemy KeyError
- railway_main.py has fix at top (try import of PostgreSQL dialect)
- Error shows line 1525 but file is shorter - may be cached old version
- Fix should work - verify deployment has latest code

### Issue 2: Auto-Adjust Thresholds
- FOUND: threshold_optimizer.py already exists with full implementation!
- AdaptiveThresholdOptimizer class adjusts based on win rate, avg R, signal volume
- Need to integrate into engine/core.py and gemini_ml.py
- Need to call analyze_and_adjust() in the main loop periodically

### Issue 3: Consistent Signal Generation  
- engine/core.py main_loop already runs while True 
- Need to ensure it's generating signals every cycle
- Add logging to show signal counts per cycle

## Implementation Plan

### Step 1: Verify railway_main.py SQLAlchemy fix 
- Already in place - verify deployment

### Step 2: Integrate threshold_optimizer into engine
- Import and use threshold_optimizer in engine/core.py
- Call refresh_thresholds() periodically in main_loop
- Use get_current_threshold() when scoring signals

### Step 3: Add signal generation logging
- Show signals generated per cycle in heartbeat
- Verify it's not stopping after one signal

## Status
- [ ] Step 1: Verify SQLAlchemy fix deployed
- [ ] Step 2: Integrate threshold_optimizer  
- [ ] Step 3: Add signal generation logging
