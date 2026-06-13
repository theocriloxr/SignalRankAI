# Fix Zero Signals Issue

## Problem
The engine generates 0 signals despite loading 20 assets and calculating indicators.

Logs show:
```
[engine] cycle=1 assets=20 generated_signals=0 max_score=None ... strategy_signals=0
```

## Root Cause
1. SignalGenerator requires strict score >= 70 threshold
2. Many strategies depend on specific indicators that may not be available
3. No fallback strategies used when main strategies return empty

## Plan

### 1. Lower score threshold in SignalGenerator
- File: `engine/strategies/signal_generator.py`
- Change score threshold from 70 to 60

### 2. Add fallback strategy invocation in engine/core.py  
- When `run_all_strategies` returns empty, invoke fallback strategies
- File: `engine/core.py` - in the strategy_signals section

### 3. Add defensive handling for missing indicators
- Update signal_generator.py to use default values when indicators are missing

## Implementation Steps
- [ ] 1. Lower score threshold in signal_generator.py
- [ ] 2. Add fallback strategy import in core.py
- [ ] 3. Add fallback invocation when strategy_signals is empty
- [ ] 4. Add diagnostic logging for fallback signals

## Followup
- Test by checking logs for generated_signals > 0
- Monitor fallback strategy usage rate
