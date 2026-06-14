# Strategy Fix Plan - Zero Signal Generation

## Problem
Engine generates 0 signals even though 20 assets are processed.

## Root Causes Identified
1. IMP (Institutional Momentum Pulse) strategy has very strict multi-timeframe requirements
2. Fallback strategies may not be properly activated when IMP fails
3. ML probability threshold too high (filtering out valid signals)

## Fixes to Apply

### Fix 1: Force Fallback Strategies Earlier
File: `strategies/__init__.py`
- Ensure fallback runs immediately when IMP returns no signals
- Remove any conditions blocking fallback activation

### Fix 2: Add Ultra-Fallback Emergency Strategy
File: `strategies/fallback.py`
- Add "last resort" strategy that always fires if price has movement
- Uses simplest possible conditions

### Fix 3: Lower ML Threshold
File: `engine/core.py`
- Lower ML_HARD_FILTER_MIN from 0.25 to 0.15
- Ensure fallback threshold kicks in when model is degraded

### Fix 4: Lower Score Threshold  
File: `engine/core.py`
- Lower PREMIUM_SCORE_THRESHOLD from 35 to 25

## Implementation
