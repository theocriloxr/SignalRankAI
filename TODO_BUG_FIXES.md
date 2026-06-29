# SignalRankAI Bug Fixes TODO

## Status: COMPLETED ✅

### All Bugs FIXED:

#### Priority 1: Critical Bugs
- [x] Fix Command Registry Mismatch
  - [x] Added /mode command handler in bot.py (mode_command imported and registered)
  - [x] Verify mode exists in COMMAND_TIERS → Yes ("mode": "VIP")
- [x] Fix Trade Tracker Duplicate Opens
  - [x] Key changed to exclude timeframe: `("fallback", symbol, direction, str(entry), str(stop))`
  - [x] Strict existence check in add_trade()

#### Priority 2: High Impact
- [x] Fix Deduplication Logic
  - [x] Fingerprint changed: `f"{asset}:{direction}:{entry_zone}"` (no timeframe)
  - [x] Multi-timeframe signals now merge into one with higher confidence
- [x] Fix Outcome Data Routing
  - [x] Stale validator has fallback: Binance REST → DB market_ticks → yfinance
  - [x] Asset-class thresholds configured for crypto/stock/fx/commodity

#### Priority 3: Architecture
- [x] Single Command Registry exists
  - [x] audit_handler validates handlers match COMMAND_TIERS on startup
  - [x] Logs mismatch warnings

---

## Verification Results:

| File | Status | Notes |
|------|--------|-------|
| signalrank_telegram/bot.py | ✅ FIXED | /mode handler added |
| core/trade_tracker.py | ✅ FIXED | Key excludes timeframe |
| engine/signal_deduplicator.py | ✅ FIXED | Fingerprint excludes timeframe |
| engine/stale_signal_validator.py | ✅ FIXED | Multi-source fallback + thresholds |

---

## Completed:
- [x] Codebase analysis and bug identification
- [x] Verified fixes in all core files
- [x] Created and updated TODO file
