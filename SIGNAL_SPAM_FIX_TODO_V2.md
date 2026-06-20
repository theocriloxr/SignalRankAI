# SignalRankAI Fix Implementation Plan V2

## Executive Summary
This document outlines the comprehensive fixes for 4 critical issues identified in the SignalRankAI codebase.

---

## ISSUE 1: Button Callback Consolidation

### Current State:
- bot.py has inline handlers (_build_signal_keyboard + per-button handlers)
- callback_handlers.py has global router
- Duplication causes "button does nothing" bugs

### Fix Plan:
1. Keep ONLY callback_handlers.py global router as single source of truth
2. Remove duplicate handlers from bot.py
3. Make every callback answer immediately, then do real work
4. Implement real MT5 execution flow or hide button
5. Fix check_outcome to query canonical Outcome table

### Files to Edit:
- signalrank_telegram/bot.py → Remove duplicate callback handlers, keep keyboard building
- signalrank_telegram/callback_handlers.py → Enhance global router

---

## ISSUE 2: Signal Deduplication Fix (ALREADY PARTIALLY DONE)

### Current State:
✅ candle_timestamp REMOVED from fingerprint in db/pg_features.py
⚠️ Need: engine/core.py to use signal_deduplicator.py path
⚠️ Need: Redis-backed dedup lock with timeframe TTL

### Fix Plan:
1. Route engine/core.py through signal_deduplicator.py policy
2. Add Redis dedup lock with timeframe-specific TTL:
   - 4H signal: 4 hour lock
   - 1H signal: 1 hour lock
   - Prevent same asset+direction+timeframe spam

### Files to Edit:
- engine/core.py → Integrate signal_deduplicator.py
- Add Redis dedup layer

---

## ISSUE 3: Outcome Tracking Unification

### Current State:
- engine/realtime_outcome_tracker.py - live tracker
- engine/core.py - writes outcome data
- engine/shadow_outcome_worker.py - ML-rejected signals
- callback /check_outcome - reads from Outcome table

### Fix Plan:
1. Choose ONE canonical writer (realtime_outcome_tracker)
2. Make engine/core only persist trade-open/trade-close events
3. Ensure every delivered signal has delivery row
4. Add reconciliation job

### Files to Edit:
- engine/realtime_outcome_tracker.py
- engine/core.py

---

## ISSUE 4: Three-Layer Dedup Protection

### Layer 1: Global Signal Deduplication (Engine Level)
```
Logic: One active signal per (asset + direction + timeframe)
- Redis key: dedup:global:{asset}:{direction}:{timeframe}
- TTL: Based on timeframe (1h=1h, 4h=4h, 1d=24h)
- Block if exists and not resolved
```

### Layer 2: User Delivery Cooldown (Tier-Based)
```
Tier    | Cooldown
--------|--------
Free   | 12 hours
Premium| 6 hours
VIP    | 4 hours

Redis key: dedup:user:{user_id}:{asset}:{direction}
```

### Layer 3: Smart Asset Cooldown (Same Direction Only)
```
Key: dedup:user:{user_id}:{asset}:{direction}
- Allow SOL SELL if SOL BUY was sent
- Block SOL BUY for 4h after SOL BUY
```

---

## Implementation TODO:

### Phase 1: Button Fixes (Priority: HIGH)
- [ ] 1.1 Remove duplicate callback handlers from bot.py
- [ ] 1.2 Enhance callback_handlers.py global router
- [ ] 1.3 Fix check_outcome to query Outcome table properly
- [ ] 1.4 Replace MT5 placeholder or hide button

### Phase 2: Dedup Fixes (Priority: CRITICAL)
- [ ] 2.1 Add Redis dedup lock to engine/core.py
- [ ] 2.2 Integrate signal_deduplicator.py path
- [ ] 2.3 Implement 3-layer cooldown system

### Phase 3: Outcome Unification (Priority: MEDIUM)
- [ ] 3.1 Make realtime_outcome_tracker canonical
- [ ] 3.2 Remove duplicate outcome logic from core.py
- [ ] 3.3 Add reconciliation job

### Phase 4: UX Enhancements (Priority: LOW)
- [ ] 4.1 Material change override (signal upgrade)
- [ ] 4.2 Smart edit vs new message

---

## Migration Notes:

### After applying these fixes:
1. Restart engine to pick up new dedup logic
2. Restart worker for outcome tracker changes
3. Monitor logs for "dedup" messages
4. Verify button clicks work immediately

---

## Risk Assessment:

### Low Risk:
- Button consolidation (well-tested patterns)
- Outcome tracking fixes

### Medium Risk:
- Dedup changes may block signals initially
- Monitor closely after deploy

### Mitigation:
- Add environment toggle to disable if needed
- Watch dedup hit rate in first 24h
