# Signal Spam Fix Plan v2 - Comprehensive Architecture Fix

## Executive Summary

Based on deep code analysis, the SOLUSDT signal spam is caused by a **systematic architecture failure** in signal lifecycle management. The fix requires addressing 10 interconnected issues across deduplication, cooldown, outcome tracking, and delivery layers.

---

## Root Cause Analysis

### Issue 1: Deduplication API Mismatch (CRITICAL)
**Location**: `engine/loop.py` lines ~170, ~220

**Current Code (WRONG)**:
```python
# Line ~170 - Wrong API signature
is_dup = await dedup.is_duplicate(asset, timeframe, sig.direction, sig.entry)

# Line ~220 - Method doesn't exist
await dedup.register_signal(asset, timeframe, sig.direction, sig.entry)
```

**Correct API**:
```python
# Need full signal dict with ALL fingerprint fields
signal_dict = {
    "asset": asset,
    "timeframe": timeframe,
    "direction": sig.direction,
    "entry": round(sig.entry, 3),
    "stop_loss": round(sig.stop_loss, 3),
    "strategy_name": sig.strategy_name,
    "score": sig.score,
    "created_at": datetime.utcnow()
}

is_dup = await dedup.is_duplicate(signal_dict)
await dedup.mark_seen(signal_dict)  # NOT register_signal()
```

**Impact**: Without correct API, fingerprint is never generated properly → deduplication always returns False → spam

---

### Issue 2: Fingerprint Missing Timeframe (CRITICAL)
**Location**: `engine/signal_deduplicator.py` `_generate_fingerprint()`

**Current**:
```python
def to_key(self) -> str:
    return f"{self.asset}:{self.direction}:{self.timeframe}:{self.entry}:{self.stop_loss}:{self.strategy}"
```

**Problem**: Timeframe is included but cooldown is SAME for all timeframes
- 4H signal and 15M signal get same cooldown (15 min)
- 4H barely moves in 15 min → should have 90+ min cooldown

**Fix**: Add TIMEFRAME-SPECIFIC cooldown:
```python
TIMEFRAME_COOLDOWNS = {
    "4h": 90 * 60,    # 90 minutes - SOLUSDT uses this
    "1d": 6 * 60 * 60, # 6 hours
    "1h": 20 * 60,    # 20 minutes
    "15m": 10 * 60,   # 10 minutes
    "5m": 5 * 60,    # 5 minutes
}
```

---

### Issue 3: Entry Price Tolerance Missing
**Location**: `engine/signal_deduplicator.py`

**Problem**: Entry exact match (69.4100 vs 69.4101) = different signal
- Same trading setup but minor price drift triggers new signal

**Fix**: Add entry zone tolerance:
```python
entry_zone_tolerance: float = 0.002  # 0.2% tolerance
```

---

### Issue 4: Confluence Triggers New Signals
**Location**: `engine/loop.py` signal generation

**Problem**: Confidence changes (40%→46%) → new UUID → new alert

**Fix**: Separate CONFIDENCE update from SIGNAL creation:
```python
# Don't regenerate signal for confidence changes
# Update metadata only, don't send new alert
if existing_signal and not material_change:
    await update_signal_metadata(signal_id, {"confidence": new_confidence})
    continue  # Skip sending
```

---

### Issue 5: Scan Frequency Not Timeframe-Aware
**Location**: `engine/loop.py` main_loop()

**Current**:
```python
interval_seconds = 120  # Fixed 2 min for all timeframes
```

**Problem**: 4H timeframe scanned every 2 min = 120x/day
- 4H candle needs 60-120 min between rescans

**Fix**: Dynamic interval by timeframe:
```python
def get_scan_interval(timeframes: List[str]) -> int:
    max_tf = max(timeframes, key=lambda tf: TF_HOURS[tf])
    base_intervals = {
        "4h": 90 * 60,
        "1d": 6 * 60 * 60,
        "1h": 20 * 60,
        "15m": 10 * 60,
    }
    return base_intervals.get(max_tf, 120)
```

---

### Issue 6: Outcome Tracker Symbol Mapping
**Location**: `core/trade_tracker.py` `_convert_symbol_for_yfinance()`

**Current**: Uses `data.market_data.format_ticker()` which should work

**Potential Issue**: Verify conversion:
- SOLUSDT → SOL-USD (yfinance format)
- BTCUSDT → BTC-USD
- EURUSD → EURUSD (already normalized)

---

### Issue 7: No Signal State Machine
**Current**: Signal Created → Sent → Forgotten

**Required**: NEW → ACTIVE → ENTRY_TOUCHED → TP1/TP2/TP3/PARTIAL_TP → SL → EXPIRED → ARCHIVED

---

### Issue 8: No Update Logic - Always Create
**Location**: `engine/loop.py`

**Current**: Every scan → new signal object → new alert

**Fix**: Check existing → update OR skip:
```python
existing = await find_active_signal(asset, timeframe, direction)
if existing:
    if materially_changed(existing, new_signal):
        await update_signal(existing.id, new_data)
        await notify_update(existing.id, "updated")
    else:
        logger.debug("Signal unchanged, skipping")
    continue
```

---

### Issue 9: Missing Cooldown Window by Timeframe
**Location**: `engine/signal_deduplicator.py`

**Add per-timeframe cooldown**:
```python
def get_cooldown_seconds(timeframe: str) -> int:
    cooldowns = {
        "4h": 90 * 60,
        "1d": 6 * 60 * 60,
        "1h": 20 * 60,
        "15m": 10 * 60,
    }
    return cooldowns.get(timeframe.lower(), 15 * 60)
```

---

### Issue 10: No Strict Deduplication Using DB
**Current**: In-memory + Redis only

**Problem**: On restart, all state lost → spam resumes

**Fix**: Query DB for recent signals:
```python
async def is_duplicate_strict_db(signal: Dict) -> bool:
    """Check DB for existing signal within cooldown window."""
    # Query signals table for same asset+direction+timeframe+strategy
    # within cooldown hours
```

---

## Files to Modify

| Priority | File | Changes |
|----------|------|---------|
| P0 | `engine/loop.py` | Fix dedup API calls, add timeframe cooldown |
| P0 | `engine/signal_deduplicator.py` | Add TF-specific cooldown, entry tolerance |
| P1 | `engine/signal_monitor.py` | Add signal state machine |
| P1 | `core/trade_tracker.py` | Verify symbol mapping |
| P2 | `signalrank_telegram/bot.py` | Audit callbacks |

---

## Implementation Steps

### Step 1: Fix SignalDeduplicator API
```python
# In signal_deduplicator.py - Enhanced fingerprint
def _generate_fingerprint(self, signal: Dict) -> SignalFingerprint:
    asset = str(signal.get("asset", "")).upper()
    direction = str(signal.get("direction", "long")).lower()
    timeframe = str(signal.get("timeframe", "1h")).lower()
    
    # Entry with tolerance (0.2%)
    entry = round(float(signal.get("entry", 0)), 3)
    stop_loss = round(float(signal.get("stop_loss", 0) or signal.get("sl", 0)), 3)
    strategy = signal.get("strategy_name", signal.get("strategy", ""))
    
    return SignalFingerprint(...)
```

### Step 2: Fix loop.py Calls
```python
# Replace wrong API calls
# OLD:
is_dup = await dedup.is_duplicate(asset, timeframe, sig.direction, sig.entry)
await dedup.register_signal(...)

# NEW:
signal_dict = {
    "asset": asset,
    "timeframe": timeframe,
    "direction": sig.direction,
    "entry": round(sig.entry, 3),
    "stop_loss": round(sig.stop_loss, 3),
    "strategy_name": sig.strategy_name,
    "score": sig.score,
    "created_at": datetime.utcnow()
}
is_dup = await dedup.is_duplicate(signal_dict)
if is_dup:
    continue
await dedup.mark_seen(signal_dict)
```

### Step 3: Add Timeframe-Specific Cooldown
```python
# In signal_deduplicator.py
TIMEFRAME_COOLDOWNS = {
    "4h": 5400,   # 90 minutes
    "1d": 21600,  # 6 hours
    "1h": 1200,   # 20 minutes
    "15m": 600,   # 10 minutes
}

def get_cooldown_seconds(self, timeframe: str) -> int:
    return TIMEFRAME_COOLDOWNS.get(timeframe.lower(), 900)
```

### Step 4: Add Signal Update Logic
```python
# Check if signal exists before creating new
existing = await find_active_signal(
    asset=asset,
    timeframe=timeframe, 
    direction=sig.direction,
    strategy=sig.strategy_name
)

if existing:
    # Check material changes
    entry_changed = abs(existing.entry - sig.entry) / existing.entry > 0.001
    sl_changed = abs(existing.stop_loss - sig.stop_loss) / existing.stop_loss > 0.001
    
    if not entry_changed and not sl_changed:
        # Same setup, refresh timestamp only
        await refresh_signal_timestamp(existing.signal_id)
        continue
    
    # Material change - update but don't send new alert
    await update_signal(existing.signal_id, {"entry": sig.entry, "stop_loss": sig.stop_loss})
    continue
```

---

## Test Checklist

- [ ] SOLUSDT BUY signals appear at most once per 90 minutes (for 4H)
- [ ] Same entry zone (±0.2%) treated as duplicate
- [ ] Confluence changes don't trigger new alerts
- [ ] Outcome tracking resolves trades correctly
- [ ] Inline buttons respond correctly

---

## Expected Results

| Metric | Before | After |
|--------|--------|-------|
| SOLUSDT signals/day | ~288 (every 5 min) | ~16 (every 90 min) |
| Duplicate rate | 95%+ | <5% |
| Outcome resolved | 0% | >80% |
| User complaints | High | Minimal |
