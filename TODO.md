# SignalRankAI Implementation Plan

## Current Analysis (from codebase exploration)

### Already Working ✅
1. `MLRejectedSignal` table - populated when signals are rejected (score gate, ML filter, expectancy, etc.)
2. `DecisionLog` table - tracks engine decisions
3. Signal delivery via Telegram with inline buttons
4. RealtimeOutcomeTracker for TP/SL notifications
5. ML scoring via `ml/inference.py` (MLFilter.ml_filter())

### Issues to Fix ❌
1. `MLShadowPrediction` table exists but NOT populated after ML scoring
2. `MLPastTrainingData` table exists but NOT populated when trades close
3. Bot menu registration can be improved
4. Rich signal formatting can be enhanced

## Implementation Plan

### Phase 1: ML Prediction Logging (Priority: HIGH)
**File:** `engine/core.py` or new `engine/ml_logger.py`

Add explicit logging after ML scoring:

```python
# After ml_filter returns probability, log to MLShadowPrediction
async def log_ml_prediction(session, signal_id, asset, timeframe, direction, 
                        ml_probability, features):
    """Save ML prediction to database for drift analysis."""
    # Implementation needed
```

### Phase 2: ML Training Data from Outcomes (Priority: HIGH)  
**File:** `engine/realtime_outcome_tracker.py` or `engine/shadow_outcome_worker.py`

When trade closes (TP/SL hit), write to `MLPastTrainingData`:

```python
# When outcome is determined, populate training data
async def log_trade_outcome(session, signal, outcome_status, pnl, features):
    """Save closed trade to ML training table for model retraining."""
    # Implementation needed
```

### Phase 3: Bot Menu Commands (Priority: MEDIUM)
**File:** `signalrank_telegram/bot.py`

Ensure commands are properly registered - most already exist:
- `/portfolio` ✅ exists
- `/dashboard` ✅ exists  
- `/leaderboard` ✅ exists
- `/mt5` ✅ exists

### Phase 4: Rich Signal Formatting (Priority: MEDIUM)
**File:** `signalrank_telegram/formatter.py`

Enhance signal display with:
- Asset class emojis (crypto 📱, FX 💱, etc.)
- ML confidence display
- Confluence indicators

---

## Files to Modify

1. **engine/core.py** - Add ML prediction logging after scoring
2. **engine/realtime_outcome_tracker.py** - Add training data logging on trade close  
3. **engine/shadow_outcome_worker.py** - New file for async outcome logging
4. **signalrank_telegram/formatter.py** - Enhanced formatting

## Database Tables Used

| Table | Status | Usage |
|-------|--------|-------|
| MLShadowPrediction | EMPTY | Log predictions after ML scoring |
| MLPastTrainingData | EMPTY | Log outcomes when trades close |
| MLRejectedSignal | POPULATED ✅ | Already working |
| DecisionLog | POPULATED ✅ | Already working |

## Implementation Order

1. Create `engine/ml_logger.py` for prediction logging
2. Update `engine/shadow_outcome_worker.py` for outcome → training data
3. Update `engine/core.py` to call ml_logger
4. Test with small signal batch
