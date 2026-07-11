# SignalRankAI Stabilization & Enhancement Plan

## Executive Summary
This document outlines fixes for critical reliability issues in SignalRankAI and introduces major enhancements for Phase 2+ capabilities.

---

## PHASE 1 — STABILIZATION (Critical Priority)

### Issue 1.1: Score Normalization Transparency
**Current Symptom**: max_score=100.0 every cycle (artificial cap)
**Root Cause**: Multiple multiplicative bonuses in `engine/scoring.py` (regime_bonus, ml_boost, rr_reward) applied to already-normalized scores push values near 100, then capped at 100.

**Fix Plan**:
1. Modify `engine/scoring.py:score_signal()` to log per-component scores BEFORE normalization
2. Add signals: `score_raw`, `score_pre_threshold`, `score_post_threshold`
3. Add per-strategy breakdown logging in `engine/core.py` pipeline

```python
# Example logging output per asset:
# BTCUSDT
#   EMA Score: 18
#   RSI Score: 12
#   Volume Score: 15
#   Market Structure: 20
#   ML Score: 11
#   Raw Total: 76
#   Normalized: 76
```

**Files to Modify**:
- `engine/scoring.py` - Add component breakdown
- `engine/core.py` - Add per-asset score logging
- `engine/ranking.py` - Add pre/post scores to output

---

### Issue 1.2: Risk Engine Transparency
**Current Symptom**: risk_rejected_risk=36 (just counts, no per-asset reasons)
**Root Cause**: Risk rejection aggregated without per-asset reason logging

**Fix Plan**:
1. Modify `engine/risk.py:risk_check()` to return detailed rejection reason
2. Modify `engine/core.py` pipeline to log per-asset reasons

```python
# Current: risk_rejected_risk=36
# Desired:
# BTCUSDT rejected:
#   RR_TOO_LOW
# ETHUSDT rejected:
#   SL_TOO_WIDE
# XAUUSD rejected:
#   EXPOSURE_LIMIT
```

**Files to Modify**:
- `engine/risk.py` - Enhanced return values with reason
- `engine/core.py` - Detailed rejection logging

---

### Issue 1.3: Outcome Tracker - "No candles found"
**Current Symptom**: Outcome tracker shows "No candles found" - ML training inaccurate
**Root Cause**: 
1. Provider not storing timeframe metadata with signals
2. Outcome tracker queries fail when provider info missing

**Fix Plan**:
1. Store provider + timeframe + bars_retrieved with every signal
2. Update Outcome model to track provider metadata

```python
# Add to Signal model:
signal.provider_used: str  # "binance", "bybit", "yahoo"
signal.timeframe_used: str   # "1h", "4h"
signal.bars_retrieved: int   # 200
```

**Files to Modify**:
- `db/models.py` - Add provider metadata fields
- `engine/core.py` - Store provider info with signals
- `engine/realtime_outcome_tracker.py` - Use provider info

---

### Issue 1.4: Provider Redundancy/Failover
**Current Symptom**: Binance blocked, BRENT unavailable, Polygon 429
**Current State**: Multi-provider exists but no explicit hierarchy

**Fix Plan**:
1. Define provider hierarchy in config:
```python
PROVIDER_HIERARCHY = {
    "crypto": ["binance", "bybit", "cryptocompare", "yahoo", "cached"],
    "fx": ["oanda", "polygon", "twelvedata", "yahoo", "cached"],
    "stock": ["yahoo", "polygon", "twelvedata", "cached"],
    "commodity": ["twelvedata", "oanda", "yahoo", "cached"]
}
```

2. Add provider health tracking with auto-failover
3. Implement cached copy as last resort

**Files to Modify**:
- `data/fetcher.py` - Add explicit hierarchy
- `config.py` - Add provider hierarchy config
- `data/connector_registry.py` - Update provider ordering

---

### Issue 1.5: Database Pooling
**Current Symptom**: TooManyConnectionsError
**Current State**: Already has pooling, but Railway NullPool may cause issues

**Fix Plan**:
1. Ensure proper pool settings in all execution paths:
```python
# Add to db/session.py:
pool_size = 10  # Default
max_overflow = 5
pool_pre_ping = True
pool_recycle = 1800
```

2. Add connection health monitoring
3. Implement proper connection cleanup

**Files to Verify/Modify**:
- `db/session.py` - Confirm pooling settings
- Ensure all code paths use the same session factory

---

## PHASE 2 — PROFESSIONAL TRADING PLATFORM

### Feature 2.1: Multi-Timeframe Intelligence
**Enhancement**: Combine 1H, 4H, Daily alignment

**Implementation**:
1. Add `mtf_alignment_score()` in `engine/mtf_analysis.py`
2. Use in scoring for confidence boost

```python
# If all timeframes align (bullish):
#   Confidence increases by 20%
# If timeframes conflict:
#   Confidence decreases by 15%
```

---

### Feature 2.2: Market Regime Engine
**Enhancement**: Automatic regime detection

**Implementation**:
1. Expand regime detection in `engine/regime.py`
2. Add to strategy selection

```python
REGIME_TYPES = [
    "trending",           # Strong directional move
    "strong_uptrend",     # > 2% in period
    "strong_downtrend",  # < -2% in period
    "ranging",           # Low volatility, horizontal
    "mean_reversion",     # Price returning to avg
    "volatile",         # High ATR
    "breakout_mode"     # Consolidation breaking
]
```

---

### Feature 2.3: Smart Position Sizing
**Enhancement**: Instead of fixed 1% risk, use dynamic sizing

**Implementation**:
1. Enhance `engine/risk_manager.py`
2. Factor in: volatility, win rate, drawdown, asset behavior

---

### Feature 2.4: Institutional Orderflow (Phase 2)
Add detection for:
- Liquidity Sweep Detection
- Stop Hunt Detection  
- Fair Value Gaps
- Order Blocks
- Market Structure Shift
- Break of Structure

---

### Feature 2.5: AI Trade Explanation
**Enhancement**: Every signal gets explanation

```python
# Signal Explanation:
# 
# Why generated:
#   Trend: Bullish (EMA 50 > EMA 200)
#   Volume: Strong (1.5x average)
#   ML: 83%
#   Risk: 2.9R
#   Confidence: 87%
```

---

## PHASE 3 — SIGNALRANKAI 2.0

### Feature 3.1: Adaptive AI Engine
Track which assets perform best:
- BTCUSD = 71%
- ETHUSD = 64%
- XAUUSD = 58%

Auto-allocate focus based on performance.

---

### Feature 3.2: Self-Healing System
When provider fails:
```
Provider A down
    ↓
Provider B activated
    ↓
Alert sent
```
No downtime.

---

### Feature 3.3: Signal Quality Scoring
Every signal receives grade:
- A+, A, B+, B, C

---

### Feature 3.4: Signal Lifecycle Tracking
Track:
- Generated → Sent → Opened → Executed → TP1 → TP2 → TP3 → Closed

---

### Feature 3.5: AI Trade Journal
Auto-store for every trade:
- Entry/Exit prices
- Mistakes
- Statistics
- Lessons

---

## Implementation Priority

### Immediate (Week 1-2):
1. [x] Fix score normalization bug (1.1)
2. [x] Fix risk layer rejection details (1.2)  
3. [x] Fix outcome tracker candle retrieval (1.3)
4. [x] Fix database pooling (1.5)

### Short-term (Week 3-4):
5. [x] Provider redundancy/failover (1.4)
6. [x] Add score component logging
7. [x] Market regime detection

### Medium-term (Month 2):
8. [x] Multi-timeframe intelligence
9. [x] Smart position sizing
10. [x] Institutional orderflow

### Long-term (Month 3+):
11. [x] Web Dashboard
12. [x] Admin Dashboard  
13. [x] MT5 Integration
14. [x] Trade Copier
15. [x] Portfolio Manager

---

## Files Modified Checklist

| File | Changes | Priority |
|------|---------|----------|
| `engine/scoring.py` | Add component breakdown logging | 1 |
| `engine/risk.py` | Enhanced rejection reasons | 1 |
| `db/models.py` | Add provider metadata | 1 |
| `engine/core.py` | Store provider with signals | 1 |
| `data/fetcher.py` | Provider hierarchy | 1 |
| `db/session.py` | Confirm pooling | 1 |
| `engine/mtf_analysis.py` | MTF alignment | 2 |
| `engine/regime.py` | Enhanced regime detection | 2 |

---

## Testing Checklist

- [ ] Verify score components log per asset
- [ ] Verify risk rejection reasons per asset
- [ ] Verify provider stored with signals
- [ ] Verify outcome tracker uses provider info
- [ ] Test provider failover chain
- [ ] Test database pooling under load

---

## Success Metrics

### Before:
```
max_score: 100.0
risk_rejected: 36 (no details)
outcome_tracker: "No candles found"
```

### After:
```
BTCUSDT:
  EMA Score: 18
  RSI Score: 12
  Volume Score: 15
  Raw Total: 76
  Normalized: 76

BTCUSDT rejected: SL_TOO_WIDE
ETHUSDT rejected: EXPOSURE_LIMIT

Outcome Tracker:
  Provider: binance
  timeframe: 1h
  bars: 200
