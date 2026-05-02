# SignalRankAI - Signal Generation Issue Fix

## Issue
Engine running but generating 0 signals across all cycles despite having 19 assets and market data.

## Root Cause Analysis
1. Existing strategies (EMA Trend, Supertrend, ADX, RSI Momentum) require strict conditions
2. Debug logging level not capturing WHY signals fail
3. No fallback strategies for weak/mixed market conditions

## Implementation Plan

### Step 1: Add Simple Fallback Strategy (COMPLETE)
- Create `strategies/fallback.py` with relaxed conditions
- Works with basic price action + trend detection
- Generates signals when other strategies fail

### Step 2: Update Strategy Runner to Use Fallback (COMPLETE)
- Modify `strategies/__init__.py` to run fallback strategies
- Fallback runs when main strategy groups produce no signals

### Step 3: Enhance Debug Logging (COMPLETE)
- Add logging when no signals generated
- Log indicator values that failed conditions
- Log regime and market data summary

### Step 4: Test & Verify (PENDING)
- Run engine and verify signals generated
- Check logs for debug output

---
## Implementation Details

### Files Modified:
1. `strategies/fallback.py` - NEW (Simple price action strategies)
2. `strategies/__init__.py` - Updated to use fallback
3. `engine/core.py` - Enhanced debug logging around line 848

### Strategy Conditions:
**Fallback strategies use:**
- Simple price vs SMA comparison (price > sma_20 = LONG)
- Candle direction (green candle = potential LONG)
- Volume confirmation (volume > 20-period average)
- No complex multi-indicator requirements
