# Signal Spam Fix Plan

## Executive Summary
Based on the analysis of the codebase, multiple root causes are contributing to signal spam (SOLUSDT BUY appearing every 2-3 minutes). The fix requires addressing 9 interconnected issues.

---

## Identified Issues & Root Causes

### Issue 1: SOLUSDT Signal Spam (Critical) - FIXED
**Root Cause**: Deduplication API mismatch + wrong method calls

In `engine/loop.py`:
```python
# BUG: Passing individual params but method expects signal dict
is_dup = await dedup.is_duplicate(asset, timeframe, sig.direction, sig.entry)
await dedup.register_signal(...)  # Method doesn't exist - should be mark_seen()
```

The correct calls in `signal_deduplicator.py`:
```python
async def is_duplicate(self, signal: Dict[str, Any]) -> bool:  # Expects dict
async def mark_seen(self, signal: Dict[str, Any]) -> None:  # Not register_signal
```

**Fix Applied**: Update loop.py to use correct API.

### Issue 2: No Signal Refresh Logic
**Root Cause**: Engine sends alerts every cycle without checking existing signals

Current flow: Scan → Generate → Send (every cycle)
Should be: Scan → Generate → Check Exists → Update / Skip

### Issue 3: Scan Frequency Too Aggressive
**Root Cause**: 4H signals scanned every 120 seconds

4H candle barely moves in 2 minutes - no new signals should be generated.

Recommended cooldown by timeframe:
- 4H: 60-120 minutes
- 1D: 4-8 hours
- 1H: 15-30 minutes
- 15M: 5-10 minutes

### Issue 4: Confluence Recalculation Creating New Signals
**Root Cause**: Confluence changes (40% → 46% → 40%) trigger new signal_id

The engine treats different confluence as new signal instead of updating metadata.

### Issue 5: Outcome Tracking Symbol Mapping
**Root Cause**: Signal uses SOLUSDT, tracker expects SOL/USD

In `core/trade_tracker.py`:
```python
def _convert_symbol_for_yfinance(symbol):
    if symbol.endswith("USDT"):
        return f"{symbol[:-4]}-USD"  # SOLUSDT -> SOL-USD
```

But signal.symbol is SOLUSDT → outcome never found.

### Issue 6: Open Trades Never Resolve
**Root Cause**: Same as Issue 5 - symbol mismatch prevents outcome resolution.

### Issue 7: Inline Keyboard Buttons
**Status**: Appears correct - patterns match button callback_data.

Button creation in bot.py:
```python
callback_data=f"signal_reaction_{signal_id}|taking_it"
```

Handler pattern:
```python
pattern=r"^signal_reaction_"
```

### Issue 8: Telegram State Loss
**Root Cause**: user_data may be cleared between callbacks.

Need to audit all user_data/chat_data paths.

### Issue 9: Signal Delivery Architecture
**Root Cause**: No persistent storage + deduplication before send

Required architecture:
```
Scan → Generate → Store → Dedupe → Rank → Deliver → Track → Update
```

---

## Fix Implementation Priority

### P0 - Critical (Immediate)
1. Fix signal deduplication API calls in loop.py
2. Add cooldown by timeframe
3. Add signal refresh/update logic
4. Fix outcome tracker symbol mapping

### P1 - High Priority
5. Fix trade lifecycle (open → resolved)
6. Add signal update logic (metadata only, no new alerts)
7. Fix open trade tracking

### P2 - Medium Priority
8. Audit callback handlers
9. Multi-timeframe fusion
10. Portfolio intelligence

---

## Files to Modify

| File | Changes |
|------|---------|
| `engine/loop.py` | Fix dedup API, add cooldown |
| `engine/signal_deduplicator.py` | Add strict dedup, timeframe-based cooldown |
| `core/trade_tracker.py` | Fix symbol mapping |
| `engine/realtime_outcome_tracker.py` | Add symbol normalization |
| `signalrank_telegram/bot.py` | Add state persistence |

---

## Implementation Notes

### Cooldown Configuration
```python
TIMEFRAME_COOLDOWNS = {
    "4h": 90 * 60,   # 90 minutes
    "1d": 6 * 60 * 60,  # 6 hours
    "1h": 20 * 60,  # 20 minutes
    "15m": 10 * 60,  # 10 minutes
}
```

### Signal Fingerprint Key
```python
def _make_fingerprint(signal):
    return hash((
        signal["asset"],
        signal["direction"],
        signal["timeframe"],
        round(signal["entry"], 3),  # Round to 3 decimal places
        round(signal["stop_loss"], 3),
        signal["strategy_name"]
    ))
```

### Symbol Normalization
```python
def normalize_symbol_for_outcome(symbol: str) -> str:
    """Convert signal symbol to tracker-compatible symbol."""
    symbol = symbol.upper()
    if symbol.endswith("USDT"):
        return symbol[:-4] + "USD"  # SOLUSDT -> SOLUSD
    if symbol.endswith("USD") and not symbol.endswith("USDD"):
        return symbol  # Already normalized
    return symbol
