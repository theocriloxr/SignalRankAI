# PHASE 1 Implementation - Quick Reference Guide
## Exact File Locations and Line Numbers

---

## FILE 1: engine/scoring.py

### CHANGE 1: RR Hard Gate (Lines 35-91)
**Location:** Function `score_signal(signal)` - START of function  
**What:** Moved RR calculation to beginning, added hard rejection before scoring  
**Key Code:**
```python
# Line 52-91: Calculate RR and hard-reject if < 1.5
if rr < min_rr:
    logger.info(f"[scoring][rr_hard_gate] {signal.get('asset')} {signal.get('direction')} RR={rr:.2f} < MIN_RR={min_rr} - REJECTED")
    return 0.0
```

### CHANGE 2: Confluence Graduated Weight (Lines 98-114)
**Location:** After RR check, before confidence check  
**What:** Changed from hard rejection to graduated weight formula  
**Key Code:**
```python
confluence_weight = 1.0
if confluence_score is not None and confluence_score < confluence_min:
    confluence_weight = max(0.0, confluence_score / 50.0)
```

### CHANGE 3: Apply Confluence Weight (Line 149)
**Location:** After base score calculation  
**What:** Multiply base score by confluence_weight  
**Key Code:**
```python
score = score * confluence_weight
```

### CHANGE 4: ML Scoring Simplification (Lines 161-181)
**Location:** After regime bonus, before RR bonus  
**What:** Removed ML from components, kept only multiply method  
**Key Code:**
```python
# ONLY method now: multiply
ml_val = resolve_ml_probability(signal)
ml_boost = 1.0
if ml_val is not None:
    ml_val = min(max(float(ml_val), 0.0), 1.0)
    ml_boost = ml_boost_min + (ml_val * ml_boost_range)
    score = score * ml_boost
    # Debug logging added
```

### CHANGE 5: Enhanced Component Logging (Lines 195-240)
**Location:** After soft-cap, before return  
**What:** Comprehensive signal breakdown logging  
**Key Code:**
```python
# Lines 207-217: Enhanced score_components dict
signal["score_components"] = {
    "rr": rr_component,
    "rr_ratio": round(rr, 2),
    "vol": vol_component,
    "confidence": confidence,
    "ml_confidence": ml_val,
    "confluence": confluence_score,
    "confluence_weight": confluence_weight,
    "regime_bonus": regime_bonus,
    "ml_boost": ml_boost,
    "rr_bonus": rr_bonus,
}

# Lines 225-232: INFO level logging with all signal details
logger.info(
    f"[scoring][components] asset={signal.get('asset')} direction={signal.get('direction')} "
    f"entry={entry:.2f} stop_loss={stop:.2f} tp_1={tp_1} tp_2={tp_2} tp_3={tp_3} | "
    f"entry_logic={entry_logic_used} confluence={confluence_score:.1f}% rr={rr:.2f} "
    f"ml_confidence={ml_val if ml_val else 'None'} regime={signal.get('regime', 'unknown')} | "
    f"final_score={display_score:.2f} (raw={raw_score:.2f})"
)
```

---

## FILE 2: strategies/trend.py

### CHANGE: Add 24-Hour Stale Data Check (Lines 190-213)
**Location:** Function `trend_strategies(asset, timeframe, market_data)` - START  
**What:** Added timestamp validation before running strategies  
**Key Code:**
```python
def trend_strategies(asset, timeframe, market_data):
    """Run all trend strategies with stale data consistency check."""
    # PHASE 1 FIX #4: Stale Data Consistency - 24-hour check
    if not market_data or 'candles' not in market_data or 'indicators' not in market_data:
        return []
    
    candles = market_data.get('candles', [])
    if not candles or len(candles) < 20:
        return []
    
    # Check data freshness - reject if older than 24 hours
    try:
        from datetime import datetime, timedelta, timezone
        last_ts = candles[-1].get('timestamp', 0)
        if last_ts > 0:
            last_time = datetime.fromtimestamp(last_ts / 1000, tz=timezone.utc)
            if datetime.now(timezone.utc) - last_time > timedelta(hours=24):
                return []
    except Exception:
        pass
    
    strategies = [EMATrendStrategy(), ...]
```

---

## FILE 3: strategies/volatility.py

### CHANGE: Add 24-Hour Stale Data Check (Lines 84-106)
**Location:** Function `volatility_strategies(asset, timeframe, market_data)` - START  
**What:** Identical stale data check as trend.py  
**Pattern:** Same 24-hour freshness validation

---

## FILE 4: strategies/structure.py

### CHANGE: Add 24-Hour Stale Data Check (Lines 1-23)
**Location:** Function `structure_strategy(asset, timeframe, market_data)` - START  
**What:** Identical stale data check, with function renamed pattern  
**Pattern:** Same 24-hour freshness validation

---

## FILE 5: strategies/imp.py

### CHANGE: Add 24-Hour Stale Data Check (Lines 214-250)
**Location:** Function `institutional_momentum_pulse_strategies(asset, market_data)` - After initial dict check  
**What:** Enhanced check that validates BOTH 4h and 1h timeframe data freshness  
**Key Code:**
```python
# PHASE 1 FIX #4: Stale Data Consistency - Check both H4 and H1 data freshness
for tf_name, candles in [("4h", h4_candles), ("1h", h1_candles)]:
    if candles and len(candles) > 0:
        try:
            from datetime import datetime, timedelta, timezone
            last_ts = candles[-1].get('timestamp', 0)
            if last_ts > 0:
                last_time = datetime.fromtimestamp(last_ts / 1000, tz=timezone.utc)
                age = datetime.now(timezone.utc) - last_time
                if age > timedelta(hours=24):
                    logging.getLogger(__name__).debug(
                        f"[imp] Stale data for {asset} {tf_name}: {age.total_seconds()/3600:.1f} hours old"
                    )
                    return []
        except Exception:
            pass
```

---

## FILE 6: strategies/fibonacci_confluence.py

### CHANGE: Add 24-Hour Stale Data Check (Lines 122-152)
**Location:** Function `fibonacci_confluence_strategies(asset, market_data)` - After candle length check  
**What:** Identical stale data check as other strategies  
**Key Code:**
```python
# PHASE 1 FIX #4: Stale Data Consistency - Check data freshness
try:
    from datetime import datetime, timedelta, timezone
    last_ts = candles[-1].get('timestamp', 0)
    if last_ts > 0:
        last_time = datetime.fromtimestamp(last_ts / 1000, tz=timezone.utc)
        age = datetime.now(timezone.utc) - last_time
        if age > timedelta(hours=24):
            logger.debug(
                f"[fibonacci] Stale data for {asset} {exec_tf}: {age.total_seconds()/3600:.1f} hours old"
            )
            return []
except Exception:
    pass
```

---

## Environment Variables to Configure

```bash
# RR Hard Gate
export MIN_RR=1.5              # Minimum risk/reward ratio (default: 1.5)

# ML Scoring
export ML_SCORE_BOOST_MIN=0.8  # Minimum ML boost (default: 0.8)
export ML_SCORE_BOOST_RANGE=0.4 # ML boost range (default: 0.4, gives 0.8-1.2x)

# Confluence
export CONFLUENCE_MIN=25.0     # Minimum confluence % (default: 25.0)

# Logging (Python logging)
export LOG_LEVEL=DEBUG         # Set to DEBUG for detailed component logs
```

---

## Verification Checklist

- [ ] All 6 files modified show no syntax errors
- [ ] `pytest tests/test_scoring_validation.py` passes
- [ ] Engine generates signals with new logging
- [ ] No signals pass with RR < 1.5
- [ ] Low-confluence signals get reduced score, not rejected
- [ ] Stale data (>24h) produces no signals
- [ ] Score components logged for all signals
- [ ] Both momentum.py stale check verified still working

---

## Quick Deploy

```bash
# 1. Backup original files
git stash  # Or: cp -r strategies/ strategies.backup/

# 2. Verify changes
python -m py_compile engine/scoring.py strategies/*.py

# 3. Run unit tests
pytest tests/ -v -k scoring

# 4. Deploy to production
git push origin main  # After testing

# 5. Monitor logs for new logging patterns
tail -f engine.log | grep "scoring\|stale\|rr_hard_gate"
```

---

## Troubleshooting

**If RR hard gate blocks all signals:**
- Check MIN_RR is not too high
- Verify signal generation includes entry/stop/target

**If stale data check is too strict:**
- Check timezone handling (UTC assumed)
- Verify candle timestamps are in milliseconds

**If ML boost not applied:**
- Check ML_SCORE_BOOST_MIN and ML_SCORE_BOOST_RANGE env vars
- Verify signal has ml_probability field

**If confluence weight seems wrong:**
- Calculate manually: weight = max(0, confluence / 50)
- For 15% confluence: weight = 0.30, score reduced to 30%

---

## Contact & Documentation

Full details available in:
- PHASE1_IMPLEMENTATION_SUMMARY.md (comprehensive guide)
- Each file has PHASE 1 FIX comments with line numbers
- Logs include [scoring] prefixes for easy filtering
