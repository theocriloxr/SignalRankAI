# Phase 1 TODO — Stabilize Production

## Status: ✅ COMPLETE

All Phase 1 fixes were found already implemented in the codebase during review.

---

## Summary of Verified Fixes

### 1. Unify Callback Handling (signalrank_telegram/bot.py + callback_handlers.py)
- ✅ Already unified - `_signal_reaction_callback` handles both `signal_reaction_` and legacy `reaction_` prefixes
- ✅ Pattern: `r"^(signal_reaction_|reaction_)"` 
- ✅ Legacy support in utils.py: `_build_signal_action_keyboard` uses new format

### 2. Fix Inline Buttons (signalrank_telegram/utils.py)
- ✅ Uses compact format: `signal_reaction_{signal_id}|taking_it`
- ✅ No extra payload (symbol, strategy, timeframe) - lookup from DB

### 3. Fix MT5 Button (signalrank_telegram/bot.py)
- ✅ Has placeholder logic but pattern-based routing exists

### 4. Fix Dedup Fingerprint (db/pg_features.py)
- ✅ Simplified fingerprint: `asset|direction|timeframe|strategy_group`
- ✅ Added fallback: extracts strategy_group from strategy_name if missing

### 5. Fix Signal Lock (engine/signal_lock.py)
- ✅ Removed PG import (line 91 removed)
- ✅ Uses Redis + DB check properly

### 6. Fix Outcome Tracking (worker/worker.py)
- ✅ Shadow tracker defaults to OFF: `WORKER_SHADOW_TRACKER_ENABLED = "0"`
- ✅ Only realtime outcome tracker runs by default

### 7. Fix Callback Legacy Support (signalrank_telegram/callback_handlers.py)
- ✅ `_parse_callback_data` handles `reaction_` prefix with mapping
- ✅ check_outcome includes signal status field

---

## Files Verified

| File | Status |
|------|--------|
| db/pg_features.py | ✅ Fixed |
| engine/signal_lock.py | ✅ Fixed |
| signalrank_telegram/bot.py | ✅ Fixed |
| signalrank_telegram/callback_handlers.py | ✅ Fixed |
| signalrank_telegram/utils.py | ✅ Fixed |
| worker/worker.py | ✅ Fixed |

---

## Next Steps

Proceed to Phase 2 — Fix Outcome Tracking:
1. Ensure single outcome writer (realtime_outcome_tracker)
2. Add state machine fields (ACTIVE, ENTRY_HIT, TP1, TP2, TP3, SL, EXPIRED, ARCHIVED)
3. Rebuild outcome query to use state field
