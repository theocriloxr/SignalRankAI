# Scoring Logic Optimization for Maximum Win Rates

## Executive Summary

The scoring logic has been comprehensively enhanced to maximize winning trades by implementing **strict quality gates**, **intelligent multipliers**, and **regime alignment bonuses**. This optimization focuses on fewer, higher-quality signals rather than signal volume.

### Key Metrics Improved:
- ✅ **Quality Gates**: Rejects low-confidence, poor R/R, and high-volatility signals
- ✅ **Win Rate Focus**: All signals scoring ≥65 must have RR≥1.5 and volatility≤0.20
- ✅ **Regime Alignment**: +10-20% bonus for signals aligned with market trends
- ✅ **ML Integration**: 0.8-1.2x boost based on model confidence
- ✅ **Exceptional R/R**: Extra rewards for 2.5:1+ trades

---

## 1. Core Scoring Formula

### Base Score Calculation
```
Base Score = (Confidence × 50%) + (R/R Score × 30%) + (Volatility Score × 20%)
```

### With Multipliers
```
Final Score = Base × Regime Bonus × ML Boost × R/R Bonus
            = Base × (1.0 + Regime×0.2) × (0.8 + ML×0.4) × R/R_Multiplier
```

---

## 2. Quality Gates (Hard Rejection Rules)

Signals are rejected immediately if they fail these gates:

### Gate 1: Confidence Floor
```python
if confidence < 0.3:  # Less than 30% base confidence
    return 0.0  # REJECT
```
**Rationale**: Strategy agreement is the foundation. Weak strategies = unreliable signals.

### Gate 2: Risk/Reward Minimum
```python
if rr < 1.5:  # Risk/reward ratio < 1.5:1
    return 0.0  # REJECT
```
**Rationale**: 1.5:1 RR is the minimum margin of safety for profitability.

### Gate 3: Volatility Ceiling
```python
if vol_component == 0.0:  # Volatility > 0.20 (20%)
    return 0.0  # REJECT
```
**Rationale**: High volatility forces wider stops → squeezed R/R → poor edge.

---

## 3. Component Scoring Details

### Risk/Reward Ratio Scoring
```
RR=1.0:  0.0   (insufficient edge)
RR=1.5:  0.0   (minimum, hard floor)
RR=2.0:  0.33  (acceptable)
RR=2.5:  0.67  (good)
RR=3.0:  1.00  (excellent)
```

**Formula**: 
```python
if rr < 1.5: return 0.0
else: return min((rr - 1.5) / 1.5, 1.0)
```

**Key**: Linear scaling from 1.5→3.0 with hard floor.

---

### Volatility Quality Scoring
```
vol≤0.08:     1.0  (perfect, tight market)
vol=0.12:    0.67  (good, normal conditions)
vol=0.16:    0.33  (acceptable, risky)
vol≥0.20:    0.0   (reject, too volatile)
```

**Formula**:
```python
if vol <= 0.08: return 1.0
elif vol >= 0.20: return 0.0
else: return (0.20 - vol) / (0.20 - 0.08)
```

**Rationale**: 
- BB width ≤ 8% = tight, low noise, best execution
- BB width ≥ 20% = ranging/choppy, poor edge, hard stop rejections

---

### Confidence Scoring
```
Contribution to final = confidence × 50%
```
- Direct 50% weight of strategy agreement
- Already filtered by confidence floor (>0.3)

---

## 4. Bonus Multipliers

### Regime Alignment Bonus (+10-20%)
```python
regime_bonus = 1.0 + (regime_fit × 0.2)
# Range: [1.0, 1.2]
```

**Examples**:
```
regime_fit=0.0: bonus=1.0x  (no alignment bonus)
regime_fit=0.5: bonus=1.1x  (+10% for partial alignment)
regime_fit=1.0: bonus=1.2x  (+20% for perfect alignment)
```

**Rationale**: Trades aligned with market regime have higher win rates.

---

### ML Confidence Boost (0.8-1.2x)
```python
ml_boost = 0.8 + (ml_probability × 0.4)
# Range: [0.8, 1.2]
```

**Examples**:
```
ML_prob=0.0: boost=0.8x  (-20% when model unsure)
ML_prob=0.5: boost=1.0x  (neutral)
ML_prob=1.0: boost=1.2x  (+20% when model confident)
```

**Rationale**: Trust ML model predictions more when confidence is high.

---

### Exceptional R/R Bonus (2.5:1+)
```python
if rr >= 2.5: score *= 1.20   # +20% for exceptional
elif rr >= 2.0: score *= 1.15 # +15% for excellent
```

**Rationale**: Rare high-probability setups deserve higher ranking.

---

## 5. Scoring Examples

### Example 1: Good Signal
```
Confidence: 0.7 (good strategy agreement)
Entry: 100, Stop: 95, Target: 110
RR = (110-100)/(100-95) = 2.0:1 ✓
Volatility: 0.12 (good conditions)
Regime Fit: 0.5 (moderate alignment)
ML Probability: 0.6

Calculation:
  Base = (0.7×50) + (0.333×30) + (0.667×20) = 35 + 10 + 13.3 = 58.3
  Regime Bonus = 1.0 + (0.5×0.2) = 1.1x
  ML Boost = 0.8 + (0.6×0.4) = 1.04x
  R/R Bonus = 1.15x (2.0:1)
  
  Final = 58.3 × 1.1 × 1.04 × 1.15 = 73.79
```

### Example 2: Excellent Signal
```
Confidence: 0.85
Entry: 100, Stop: 85, Target: 137.5
RR = (137.5-100)/(100-85) = 2.5:1 ✓✓
Volatility: 0.08 (perfect)
Regime Fit: 0.9 (strong alignment)
ML Probability: 0.8

Calculation:
  Base = (0.85×50) + (0.667×30) + (1.0×20) = 42.5 + 20 + 20 = 82.5
  Regime Bonus = 1.0 + (0.9×0.2) = 1.18x
  ML Boost = 0.8 + (0.8×0.4) = 1.12x
  R/R Bonus = 1.20x (2.5:1)
  
  Final = 82.5 × 1.18 × 1.12 × 1.20 = 131.04 [capped at 100.0]
```

### Example 3: Perfect Signal
```
Confidence: 1.0
Entry: 100, Stop: 85, Target: 145
RR = (145-100)/(100-85) = 3.0:1 ✓✓✓
Volatility: 0.08 (perfect)
Regime Fit: 1.0 (perfect alignment)
ML Probability: 0.9

Calculation:
  Base = (1.0×50) + (1.0×30) + (1.0×20) = 100
  Regime Bonus = 1.0 + (1.0×0.2) = 1.2x
  ML Boost = 0.8 + (0.9×0.4) = 1.16x
  
  Final = 100 × 1.2 × 1.16 = 139.2 [capped at 100.0]
```

---

## 6. Dispatch Thresholds

### Delivery Decision
```
MIN_SCORE_THRESHOLD = 65  (from 55)
```

**Distribution by Tier**:
- **FREE**: 2 signals/day (delayed), score ≥ 65
- **PREMIUM**: 10 signals/day (real-time), score ≥ 65
- **VIP**: 30 signals/day (real-time), score ≥ 65
- **ADMIN/OWNER**: Unlimited, score ≥ 55

**Consensus Filter**:
```
CONSENSUS_MIN_SCORE = 1.0
```
- Requires strategy agreement (single strategy at 1.0+ confidence OR 2 strategies at 0.5+ each)

---

## 7. Win Rate Optimization Strategy

### Fewer, Better Signals
Instead of maximizing signal volume, the system now focuses on **quality over quantity**:

| Metric | Impact |
|--------|--------|
| Confidence Floor (0.3) | Rejects unreliable strategies |
| R/R Minimum (1.5:1) | Ensures mathematical edge |
| Volatility Ceiling (0.20) | Avoids choppy markets |
| Regime Bonus | Trades aligned with trend |
| ML Boost | Adds predictive intelligence |

### Expected Outcomes
- **Signal Volume**: Decreased (fewer but better trades)
- **Win Rate**: Increased (stricter quality gates)
- **Average R/R**: Maintained at 2.0-2.5:1
- **Profit Factor**: Improved (better risk/reward management)

---

## 8. Consensus Logic

### Multi-Strategy Agreement
Signals are grouped by `(asset, timeframe, direction)`:

```python
# Same pair, same direction
grouped_signal_count = len(strategies_with_same_direction)
consensus_confidence = sum(strategy_confidences)

if consensus_confidence >= CONSENSUS_MIN_SCORE (1.0):
    approve_signal()
```

### Examples
```
Single Strategy at 0.7 confidence: ✗ (0.7 < 1.0)
Single Strategy at 1.0 confidence: ✓ (1.0 >= 1.0)
Two Strategies at 0.55 each:        ✓ (1.1 >= 1.0)
Three Strategies at 0.4 each:       ✓ (1.2 >= 1.0)
```

---

## 9. Testing & Validation

### All Tests Passing
```
test_all_functions.py   11 passed ✓
test_core.py             4 passed ✓
test_scoring_validation 5 passed ✓
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Total                   20 passed ✓
```

### Component Validation
- ✅ RR Scoring: 1.5→3.0 maps to 0.0→1.0 correctly
- ✅ Volatility Scoring: 0.08→0.20 maps to 1.0→0.0 correctly
- ✅ Quality Gates: Low confidence, poor RR, high vol all rejected
- ✅ Multipliers: Regime and ML bonuses applied correctly
- ✅ Final Scores: Range 0-100 with proper capping

---

## 10. Production Configuration

### Environment Variables
```bash
# Core thresholds
PREMIUM_SCORE_THRESHOLD=65        # Dispatch threshold (was 55, now 65)
CONSENSUS_MIN_SCORE=1.0           # Consensus gate (was 0.6, now 1.0)
CONSENSUS_ENABLED=true            # Enable consensus filtering

# Risk limits
MAX_SIGNAL_VOLATILITY=0.20         # Max BB width
MAX_ACCOUNT_DRAWDOWN=0.20          # Max account drawdown

# ML activation
ML_ENABLED=1                       # Activate ML model
ML_PROB_THRESHOLD=0.6              # ML gate

# Tier limits
FREE_DAILY_LIMIT=2                 # Free users (2/day)
PREMIUM_DAILY_LIMIT=10             # Premium (10/day)
VIP_DAILY_LIMIT=30                 # VIP (30/day)
```

### Recommended Tuning
```
If Too Few Signals:     Lower PREMIUM_SCORE_THRESHOLD to 60
If Too Many Losses:     Raise PREMIUM_SCORE_THRESHOLD to 70
If ML Underperforms:    Lower ML_PROB_THRESHOLD to 0.5
If ML Overperforms:     Raise ML_PROB_THRESHOLD to 0.7
```

---

## 11. Expected Results

### Signal Quality Metrics
- **Average Score**: 75-85 (high quality)
- **Average R/R**: 2.0-2.5:1 (well-rewarded)
- **Average Volatility**: 0.08-0.12 (tight markets)
- **Regime Alignment**: 70%+ signals aligned with regime

### Trading Performance
- **Win Rate**: Target 55-65% (from quality gates)
- **Profit Factor**: Target 1.8-2.2x (revenue/drawdown)
- **Sharpe Ratio**: Improved via consistent R/R enforcement
- **Max Drawdown**: Reduced via volatility limits

---

## Summary

The enhanced scoring logic transforms signal generation from a volume-focused approach to a **quality-focused approach**. Each signal must pass rigorous quality gates and achieve high scores through:

1. **Strong base strategy agreement** (confidence ≥ 0.3)
2. **Excellent risk/reward** (RR ≥ 1.5, bonus at 2.5+)
3. **Favorable market conditions** (volatility ≤ 0.20)
4. **Regime alignment** (bonus up to +20%)
5. **ML confirmation** (boost up to +20%)

This results in **fewer but significantly better trading signals** with higher win rates and more consistent profitability.
