# SignalRankAI Fix Plan - Signal Deduplication and Button Callbacks

## Summary of Issues to Fix

### 1. Signal Deduplication Bug (Most Critical)
**Problem**: `compute_signal_fingerprint()` in `db/pg_features.py` includes `candle_timestamp` in the hash, causing duplicate signals when the same trade idea is regenerated on different candles.

**Current Code** (line ~189):
```python
raw: str = f"{asset}|{timeframe}|{direction}|{entry}|{sl}|{tp_norm}|{strategy_group}|{strategy_name}|{candle_timestamp}"
```

**Fix**: Remove candle_timestamp from fingerprint - dedup should be based on trade thesis (asset, direction, timeframe, strategy), not candle instance.

### 2. Button Callback Duplication
**Problem**: Callbacks are handled in two places:
- `signalrank_telegram/callback_handlers.py` - global router
- `signalrank_telegram/bot.py` - per-button handlers (like `_check_outcome_callback`)

This causes routing fragility and "button does nothing" bugs.

**Fix**: Consolidate into ONE callback router (keep global router, remove per-button handlers).

### 3. _check_outcome_callback Bug
**Problem**: Uses `sig_row.expired` field but only works if outcome row already exists. When no outcome yet, shows generic "active / no outcome yet" state that feels broken.

**Fix**: Query canonical Outcome table and give clear "pending / tp1 / sl / expired" status.

### 4. MT5 Placeholder Bug  
**Problem**: `_handle_mt5_trade()` in callback_handlers.py only sends "Opening MT5 trade execution..." and doesn't actually execute.

**Fix**: Either implement real execution or hide button until implemented.

### 5. Outcome Tracking Split
**Problem**: Multiple outcome writers:
- `engine/realtime_outcome_tracker.py`
- `engine/core.py`  
- `engine/shadow_outcome_worker.py`
- Telegram callback reads from different table

**Fix**: Choose ONE canonical writer (worker tracker) and unify outcome state.

---

## Implementation Order

### Step 1: Fix Signal Fingerprint (CRITICAL - Single Line Change)
File: `db/pg_features.py`
- Remove candle_timestamp from the fingerprint calculation

### Step 2: Add Redis Dedup Lock Layer
File: `db/pg_features.py` or new file
- Add Redis-backed dedup lock with timeframe-specific TTL

### Step 3: Consolidate Callbacks
File: `signalrank_telegram/callback_handlers.py` 
- Keep global router
- Remove duplicate handlers from bot.py

### Step 4: Fix Check Outcome
File: `signalrank_telegram/bot.py` and/or `callback_handlers.py`
- Query proper Outcome table
- Show clear status

### Step 5: Fix MT5 Button
File: `signalrank_telegram/bot.py` and/or `callback_handlers.py`
- Hide or implement real execution

### Step 6: Unify Outcome Writer
Files: `engine/core.py`, `engine/realtime_outcome_tracker.py`
- Designate single canonical writer
- Add reconciliation job

---

## Layer-Based User Delivery Cooldown (Bonus)

Layer 1: Engine-level dedup (FIX ABOVE)
Layer 2: User delivery cooldown (per user, per asset)
Layer 3: Smart asset cooldown (per user, per asset, per direction)

Tier-based cooldowns:
- FREE: 12 hours
- PREMIUM: 6 hours  
- VIP: 4 hours
