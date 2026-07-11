# Signal Generation Blockage: Root Cause Analysis & Fixes

## Problem Summary
Production logs show:
- Engine cycles completing with 0 stored signals despite candidates reaching final gates
- Example: `strategy_signals=218 → consensus=57 → selected=54 → unique=54 → strict_candidates=32 → risk_passed=32 → final_signals=0 → stored=0`
- Provider outages (DXY out of credits, Polygon 429s, VIX unavailable)
- ML drift detected in 30+ features

## Root Cause: Multiple Final Gate Rejections

Signals are being rejected between `risk_passed` and `final_signals` by one or more of these gates:

### Gate 1: TP/SL Structure Validation (CRITICAL)
**Location:** `engine/core.py:1707`
```
if not tp:
    rejection_reason = 'invalid_tp_structure'
```
**Why it fails:**
- Strategies not providing valid TP/SL pairs
- SL or entry price missing/zero
- TP not matching direction (long: TP > entry, short: TP < entry)
- SL not matching direction (long: SL < entry, short: SL > entry)

**Fix:**
Add detailed logging to identify which signals are failing:
```python
# Patch to engine/core.py at line 1706 (before invalid_tp_structure check)
logger.info(f"[engine] TP/SL validation for {sig.get('asset')} tf={sig.get('timeframe')} "
            f"dir={sig.get('direction')} entry={entry_f} sl={sl} tp={tp}")
```

### Gate 2: Advanced Filters Structure Check (HIGH PRIORITY)
**Location:** `engine/core.py:1576`
```
passed_filters, rejections = advanced_filters.run_all_filters(...)
if not passed_filters:
    rejection_reason = ';'.join(rejections)
```
**Why it fails:**
- Advanced market regime filters rejecting signals
- Slippage control filters too strict
- Entry zone validation too tight

**Fix:**
Temporarily disable or relax advanced filters:
```
ADVANCED_FILTERS_ENABLED=0
or
ADVANCED_FILTERS_MODE=permissive
```

### Gate 3: Score Threshold Gate (CONFIRMED ISSUE)
**Location:** `engine/core.py:1756`
```
min_score_threshold = _current_min_score_threshold()
if sig.get('score', 0) < min_score_threshold:
    rejection_reason = f"score {sig.get('score',0)} < {min_score_threshold}"
```
**Why it fails:**
- `_runtime_min_score_threshold` defaults to 55 (or reads from DB)
- DB threshold optimizer can increase threshold above signal scores
- Expectancy decay multiplies score down if live_expectancy < 0

**Confirmed Fix** (from code analysis):
```bash
PREMIUM_SCORE_THRESHOLD=0
PREMIUM_SCORE_THRESHOLD_FORCE=1  # NEW: prevents DB from overriding
```

### Gate 4: Expectancy Hard Block (OPTIONAL)
**Location:** `engine/core.py:1781`
```
if EXPECTANCY_HARD_BLOCK_ENABLED and live_exp < 0.0:
    rejection_reason = f"low expectancy {live_exp:.3f}"
```
**Fix:**
```bash
EXPECTANCY_HARD_BLOCK_ENABLED=0  # Disable hard block during diagnosis
```

### Gate 5: Gemini LLM Review (OPTIONAL BUT LIKELY)
**Location:** `engine/core.py:1807-1835`
- Calls Gemini API for LLM signal review
- API costs + rate limits + quality variability
- Can reject high-quality signals due to LLM hallucinations

**Fix:**
```bash
GEMINI_SIGNAL_REVIEW_ENABLED=0  # Disable LLM review during diagnosis
```

## Immediate Action Plan (Temporary Diagnostic Mode)

### Step 1: Set These Environment Variables
```bash
# Disable all final gates (permissive mode for diagnosis)
PREMIUM_SCORE_THRESHOLD=0
PREMIUM_SCORE_THRESHOLD_FORCE=1
ML_PROB_THRESHOLD=0.0
ML_HARD_FILTER_MIN=0.0
CONFLUENCE_GATE_MIN=0.0
GEMINI_SIGNAL_REVIEW_ENABLED=0
ULTRA_QUALITY_ENABLED=0
EXPECTANCY_HARD_BLOCK_ENABLED=0

# Enable diagnostics
ENGINE_PIPELINE_DEBUG=1
ENGINE_CYCLE_LOG=1
ENGINE_DIAGNOSTIC_DIR=.diagnostics
```

### Step 2: Redeploy (Railway CLI)
```bash
railway variables set PREMIUM_SCORE_THRESHOLD 0
railway variables set PREMIUM_SCORE_THRESHOLD_FORCE 1
railway variables set ML_PROB_THRESHOLD 0.0
railway variables set ML_HARD_FILTER_MIN 0.0
railway variables set CONFLUENCE_GATE_MIN 0.0
railway variables set GEMINI_SIGNAL_REVIEW_ENABLED 0
railway variables set ULTRA_QUALITY_ENABLED 0
railway variables set EXPECTANCY_HARD_BLOCK_ENABLED 0
railway variables set ENGINE_PIPELINE_DEBUG 1
railway variables set ENGINE_CYCLE_LOG 1

railway up
```

### Step 3: Wait 2-3 Engine Cycles
Watch logs for:
- `[engine] cycle=N ... final_signals=X stored=Y` (should increase)
- `[engine][diagnostic_heatmap]` entries in logs

### Step 4: Fetch Diagnostics
```bash
# Via Railway CLI
railway run -- bash -c "cat .diagnostics/heatmap_log.jsonl | head -200"

# Or via web UI: run shell command in Railway environment
```

### Step 5: Run Diagnostic Parser Locally
```bash
python parse_diagnostics.py .diagnostics/heatmap_log.jsonl
```
This will show top rejecting gates and per-asset breakdown.

### Step 6: Interpret Results
- If `final_signals > 0` after relaxing gates → storage/delivery issue downstream
- If `final_signals` still = 0 → provider/data issue (DXY/VIX missing)
- If specific gates show high counts → that's your culprit

## Selective Re-Enable Protocol (After Diagnosis)

Once signals start flowing:
1. Re-enable gates ONE AT A TIME
2. Watch for signal count drop
3. The gate causing the drop is the problem

Example:
```bash
# Round 1: enable score gate only
PREMIUM_SCORE_THRESHOLD=55

# Round 2: add ML filter
ML_HARD_FILTER_MIN=0.55

# Round 3: add Gemini (but at low rate)
GEMINI_SIGNAL_REVIEW_ENABLED=1
GEMINI_SIGNAL_REVIEW_ENABLED_SAMPLE_RATE=0.25  # Only 25% of signals

# Continue until signal count drops significantly
```

## Provider Issues (Secondary)

Your production logs show:
- **DXY**: "out of API credits" (twelvedata) → macro features missing
- **VIX**: Polygon 429 rate limit
- **US10Y/US02Y**: Polygon 429 rate limit
- **Binance**: "restricted location" (geoblock)

**Impact:** Without macro features (DXY trend, VIX trend, US10Y trend), ML model predictions may be incorrect or drift detected.

**Quick fix:** Add macro feature fallback defaults in `engine/core.py`:
```python
# In _fetch_macro_snapshot()
dxy = {...} or {"trend": 0.0, "last": 0.0}  # Default if fetch fails
vix = {...} or {"trend": 0.0, "last": 0.0}
us10y = {...} or {"trend": 0.0, "last": 0.0}
```

## Expected Outcome

After applying the diagnostic vars + redeploy:
1. First cycle: `final_signals=0` → `final_signals=15-20` (if gates were the issue)
2. Logs show `[engine][diagnostic_heatmap]` with gate counts
3. Run parser to see dominant rejecting gates
4. Re-enable gates selectively to pinpoint culprit
5. Once root cause identified, apply targeted fix

## Files to Monitor

- **Engine logs**: watch for `[engine] cycle=N ... final_signals=X`
- **Diagnostics file**: `.diagnostics/heatmap_log.jsonl` (created after 3+ empty cycles per asset)
- **Parser output**: `python parse_diagnostics.py` summary

---

**Next Step:** Apply diagnostic env vars and let me know once you have the heatmap output.
