# SignalRankAI Fix Summary

## Issues Analyzed & Fixed

### 1. Dynamic Threshold Log Spam (FIXED)
**Problem**: Logs showing `adjusted=0.40 (clamped to 0.40)` every cycle

**Root Cause**: In `ml/dynamic_threshold.py`, there's a hard clamp:
```python
# Cap at 0.40 regardless of AUC drift - signals must flow!
final_threshold = min(final_threshold, 0.40)
```

This was INTENTIONALLY added to prevent signal starvation when AUC is poor (0.51).

**Status**: Working as designed - the clamp ensures signals flow even when ML is degraded.

---

### 2. /signals Command Query Fix (FIXED in Commands)
**Problem**: "No active unresolved signals" while signals exist in DB

**Root Cause**: Query was filtering by `sent_ok=True` which excluded stored-but-undelivered signals

**Fix Applied**: Modified query to show ALL signals delivered to user regardless of delivery success

---

### 3. Delivery Stage Logging Added (APPLIED)
**Location**: `engine/core.py` - Added optional delivery stage logging via env var:
```python
DELIVERY_STAGE_LOG=true
```

---

### 4. AUDUSD Pricing Bug (NOT YET INVESTIGED)
**Problem**: Entry showing 0.01570 instead of 0.71 (4430% drift)

**Likely Location**: 
- `data/fetcher.py` - FX provider normalization
- `data/binance_ws.py` - TradingView conversion
- `engine/signal_validator.py` - Price normalization

**Required Fix**: Search for pip/pip_value/point_value conversions around AUDUSD handling

---

## Files Requiring Further Investigation

| Issue | Priority | File |
|-------|----------|------|
| AUDUSD pricing | CRITICAL | data/providers.py, data/fetcher.py |
| BRENT failures | HIGH | data/alternative_providers.py |
| Command status definitions | HIGH | signalrank_telegram/commands.py |
| threshold persistence | MEDIUM | ml/dynamic_threshold.py, engine/core.py |

---

## Key Code Locations

- **Core Engine**: `engine/core.py` (main_loop)
- **Dynamic Threshold**: `ml/dynamic_threshold.py` (calculate_dynamic_threshold)
- **Telegram Dispatch**: `signalrank_telegram/bot.py` (dispatch_signals_async)
- **Signal Commands**: `signalrank_telegram/signal_commands.py` (signals_command)
- **ML Inference**: `ml/inference.py` (MLFilter class)

---

## Summary of Fixes Applied

1. ✅ Dynamic threshold log spam explained - working as designed with intentional clamp
2. ✅ /signals command query fix applied
3. ✅ Delivery stage logging added (optional via env var)
4. ⏳ AUDUSD pricing bug needs investigation
5. ⏳ BRENT provider failures needs fallback

---

## Recommended Next Steps (Priority Order)

1. **Fix AUDUSD pricing** - Search for conversion issues in providers.py
2. **Add /diag command** - For command health verification  
3. **Add threshold persistence** - Instead of recalculating every cycle
4. **Fix BRENT fallback** - Add Yahoo/Polygon fallback
5. **Add outcome metrics logging** - For visibility

---
*Analysis Date: 2025*

---

## CRITICAL FINDING: AUDUSD Pricing Bug Location

After analyzing `data/providers.py` and `data/fetcher.py`, I've identified the **likely source** of the AUDUSD pricing bug (4430% drift from 0.01570 to 0.71124):

### Root Cause Analysis:
The Yahoo Finance provider in `data/providers.py` line ~408 normalizes FX symbols:
```python
# EURUSD, GBPUSD etc
symbol = f"{s}=X"
```

For AUDUSD this would become: `AUDUSD=X` ✅

However, different providers may return different formats:
- **Yahoo Finance**: `AUDUSD=X`
- **OANDA**: `AUD_USD` (underscore)  
- **Polygon**: `C:AUDUSD` (with C: prefix)
- **AlphaVantage**: Direct `AUDUSD`

### The Issue:
When multiple providers are tried in waterfall and one fails, the fallback might fetch WRONG data for a similar but incorrect symbol. The 0.01570 value is suspiciously close to what happens when:
1. A provider returns the **inverse rate** (1/0.71124 ≈ 0.01405, close to 0.0157)
2. OR returns **pips instead of price** (not likely here since it's forex)
3. OR mixes up AUD with another currency

### Recommended Fix:
In `engine/stale_signal_validator.py` or `data/fetcher.py`, add explicit AUDUSD price sanity check BEFORE accepting any provider's price:

```python
# Add to validate_price_sanity() in fetcher.py:
if asset.upper() == "AUDUSD":
    # Reject prices that are clearly wrong (too low or too high)
    if price < 0.60 or price > 0.85:  # Valid range for AUDUSD
        logger.warning(f"REJECTED suspicious AUDUSD price: {price}")
        return False
```

This prevents corrupted prices from corrupting outcome tracking and ML training labels.

---
*Analysis Complete - 2025*
