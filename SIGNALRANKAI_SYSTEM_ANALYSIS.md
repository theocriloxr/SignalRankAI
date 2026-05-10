# SignalRankAI System Analysis and Fixes Needed

## Executive Summary
This document provides a comprehensive analysis of the SignalRankAI codebase and identifies the root causes of why signals aren't generating as expected. Based on analysis of the logs and code, here are the key findings:

### Key Observations from Logs

```
[engine] cycle=1 assets=20 generated_signals=0 max_score=62.68 max_score_pre_threshold=62.68 strategy_signals=120 normalized=120 consensus=64 selected=29 unique=29 strict_candidates=26 risk_passed=26 final_signals=0 stored=0
```

**Critical Issue**: 120 strategy signals → 0 final signals stored!

### Root Cause Analysis

Based on code analysis, here's the exact breakdown:

---

## Issue 1: Expectancy Gate Not Integrated

**Location**: `engine/core.py` (main_loop function, approximately line 850-920)

**Problem**: The `expectancy_gate` function exists in `engine/expectancy_gate.py` but is NEVER CALLED in the pipeline!

The code has:
```python
# Final gates: score + expectancy
min_score_threshold = _current_min_score_threshold()
if sig.get('score', 0) < min_score_threshold:
    sig['rejection_reason'] = f"score {sig.get('score',0)} < {min_score_threshold}"
    _log_decision("skipped", sig, reason=sig['rejection_reason'])
    continue
# Expectancy gate (Phase 3 full impl)
live_exp = float(sig.get('live_expectancy', 0.15))
if live_exp < 0.15:
    sig['rejection_reason'] = f"low expectancy {live_exp:.3f}"
    _log_decision("skipped", sig, reason=sig['rejection_reason'])
    continue
```

But `live_expectancy` is NEVER SET anywhere in the pipeline! The signal dict never has a `live_expectancy` key, so:
- Default is `0.15` (from `sig.get('live_expectancy', 0.15)`)
- This equals the threshold (0.15), which fails the `<` check!

**Expected Behavior**: Either:
1. Call `expectancy_gate()` to compute actual expectancy per asset, OR
2. Use `0.0` as default to allow new assets without history

---

## Issue 2: Score Calculation Returns 0 for Most Signals

**Location**: `engine/scoring.py` - `score_signal()` function

**Problem**: The scoring function has very strict gates that cause most signals to return 0:

1. **Confluence Gate**: Requires `CONFLUENCE_MIN=25%` - signals fail if confluence < 25%
2. **Confidence Gate**: Requires `CONFIDENCE_MIN=0.35` - signals fail if ML confidence < 35%
3. **R/R Gate**: Requires `MIN_RR=1.5` - signals fail if R/R < 1.5

Looking at the scoring logic:
```python
confluence_score = calculate_confluence(signal)
if confluence_score is not None and confluence_score < confluence_min:
    return 0.0  # REJECTS SIGNAL
```

The confluence calculator (`engine/scoring.py:calculate_confluence`) requires multiple indicators that may not be in the signal dict (rsi, macd_trend, volume_ratio, nearest_support, nearest_resistance, adx_trend).

**Evidence from logs**: `max_score=62.68` - signals ARE being scored, but they don't pass ALL gates.

---

## Issue 3: Data Provider Failures (Non-Critical but Affecting Quality)

From logs:
```
[data.providers] [twelvedata] fetch_failed symbol=BRENT msg=You have run out of API credits for the current minute
[data.providers] [polygon] fetch_failed symbol=BRENT status=429
[data.pair_discovery] Binance pairs disabled: Service unavailable from a restricted location
```

This is rate limiting from providers, not a code bug.

---

## Issue 4: SQLAlchemy Connection Pool Warning

```
SAWarning: The garbage collector is trying to clean up non-checked-in connection
```

This is a best-practice warning, not causing signals to fail. However, it should be fixed for production stability.

---

## Issue 5: Provider Switching Logic

The system correctly falls back between providers, but some symbols consistently fail:
- All IDR pairs (USDTIDR, BTCIDR, etc.) - likely exchange restrictions
- Brent crude commodity - provider rate limits

---

## Pipeline Flow (How Signals Should Work)

```
1. Fetch Market Data (data/fetcher.py → data/market_data.py)
   ↓
2. Calculate Indicators (data/indicators.py)
   ↓
3. Run Strategies (strategies/*.py) → strategy_signals
   ↓
4. Normalize/Dedupe (engine/signal_controller.py) → normalized
   ↓
5. Consensus Filter (engine/consensus.py) → consensus_signals
   ↓
6. Pick Best Direction (controller.pick_best_direction_per_pair) → selected
   ↓
7. Compute Fingerprints → unique_signals
   ↓
8. Validate Structure (engine/signal_validator.py) → strict_candidates
   ↓
9. ML Filter (ml/inference.py) → risk_passed
   ↓
10. Score & Advanced Filters → final_signals
    ↓
11. Store in DB → stored_signals
    ↓
12. Deliver to Users → dispatched
```

---

## Solution Plan

### Fix 1: Integrate Expectancy Gate
**File**: `engine/core.py`
**Change**: Call `expectancy_gate()` OR use default of `0.0` instead of `0.15`

```python
# Option A: Call expectancy gate
from engine.expectancy_gate import expectancy_gate
exp_passed = await expectancy_gate(sig)
if not exp_passed:
    sig['rejection_reason'] = 'expectancy_gate_failed'
    continue

# Option B: Use 0.0 default for new assets
live_exp = float(sig.get('live_expectancy', 0.0))  # Changed from 0.15
if live_exp < 0.0:  # Changed from 0.15
    sig['rejection_reason'] = f"low expectancy {live_exp:.3f}"
    continue
```

### Fix 2: Make Scoring More Lenient (Temporary)
**File**: `engine/scoring.py`
**Change**: Lower gates to allow more signals through

```python
confluence_min = _env_float("CONFLUENCE_MIN", 0.0)  # Was 25.0
confidence_min = _env_float("CONFIDENCE_MIN", 0.0)  # Was 0.35
# OR make these environment variables so they can be adjusted without code changes
```

### Fix 3: Add Logging for Each Gate
**File**: `engine/core.py`
**Change**: Log WHY each signal is rejected at each stage

```python
# After each gate, log:
logger.info(f"[engine] gate_rejected: asset={asset} gate=expectancy reason={sig.get('rejection_reason')}")
```

---

## Files to Modify

1. `engine/core.py` - Main engine loop
2. `engine/scoring.py` - Signal scoring
3. `engine/expectancy_gate.py` - Expectancy calculations
4. `db/session.py` - Connection management

---

## Configuration Adjustments Needed

These environment variables should be tuned:

| Variable | Current | Recommended | Purpose |
|----------|---------|-------------|---------|
| CONFLUENCE_MIN | 25.0 | 0.0 | Confluence gate |
| CONFIDENCE_MIN | 0.35 | 0.0 | ML confidence gate |
| ML_PROB_THRESHOLD | 0.55 | 0.5 | ML filter threshold |
| PREMIUM_SCORE_THRESHOLD | 70 | 65 | Minimum score to store |
| EXPECTANCY_MIN | 0.15 | 0.0 | Minimum expectancy |

---

## Verification Steps

After fixes, redeploy and check:
1. `final_signals > 0` in logs
2. `stored > 0` in delivery summary
3. Check `/health` endpoint responds
4. Check Telegram bot responds to /start

---

## Additional Observations

### What's Working Correctly:
- ✅ Redis webhook queue
- ✅ Telegram webhook registration
- ✅ PostgreSQL database connection
- ✅ APScheduler jobs running
- ✅ Strategy signals being generated (120 signals)
- ✅ Normalization working (120→120)
- ✅ Consensus filter working (120→64)
- ✅ Selection and deduplication (64→29 unique)

### What's NOT Working:
- ❌ Expectancy gate (not integrated)
- ❌ Final signal output (0 signals stored)
- ❌ Some data providers rate-limited

---

*Analysis Date: 2026-05-07*
*SignalRankAI Version: v1.0.0*
