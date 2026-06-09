# TODO: Fix Telegram Signal Blockage Issue

## Problem Summary
- Max signal score achieved: 59.25
- Current thresholds blocking all signals:
  - `signal_controller.py`: PREMIUM_THRESHOLD = 75 (BLOCKING)
  - `tier_constants.py`: TIER_SCORE_THRESHOLDS = 80 (BLOCKING)
- Engine cannot deliver any signals to Telegram because scores never reach thresholds

## Root Cause Analysis
Signal passes through 3 filtering layers:
1. **config.py** - PREMIUM_SCORE_THRESHOLD = 48 (PASSES 59.25)
2. **signal_controller.py** - PREMIUM_THRESHOLD = 75 (BLOCKS 59.25) <-- MAIN BOTTLENECK
3. **tier_constants.py** - TIER_SCORE_THRESHOLDS = 80 (BLOCKS 59.25) <-- DELIVERY GATE

## Implementation Plan

### Step 1: Lower signal_controller thresholds
- File: `engine/signal_controller.py`
- Change:
  - PREMIUM_THRESHOLD: 75 → 55
  - VIP_THRESHOLD: 85 → 70

### Step 2: Lower tier_constants thresholds  
- File: `core/tier_constants.py`
- Change TIER_SCORE_THRESHOLDS:
  - "free": 80 → 55
  - "premium": 80 → 55
  - "vip": 80 → 55

### Step 3: Verify changes work
- Check engine produces signals at 55+ threshold
- Confirm Telegram delivery works

## Status: NOT STARTED
