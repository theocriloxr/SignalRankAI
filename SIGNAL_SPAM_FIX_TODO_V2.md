# Signal Spam Fix TODO v2 - Implementation Checklist

## P0 - Critical Fixes (Immediate)

### TODO 1: Fix SignalDeduplicator API and Timeframe Cooldown
- [ ] Add TIMEFRAME_COOLDOWNS constant in `engine/signal_deduplicator.py`
- [ ] Modify `get_cooldown_seconds()` to use timeframe-specific cooldowns
- [ ] Add entry zone tolerance for fingerprint matching
- [ ] Ensure timeframe is in fingerprint key

### TODO 2: Fix loop.py Dedup API Calls  
- [ ] Change: `is_dup = await dedup.is_duplicate(asset, timeframe, sig.direction, sig.entry)`
- [ ] To: `is_dup = await dedup.is_duplicate(signal_dict)` (pass full dict)
- [ ] Change: `await dedup.register_signal(asset, timeframe, sig.direction, sig.entry)`
- [ ] To: `await dedup.mark_seen(signal_dict)` (correct method)

### TODO 3: Build Proper Signal Dict Before Dedup Check
- [ ] Create complete signal_dict with all fingerprint fields BEFORE dedup check
- [ ] Include: asset, timeframe, direction, entry, stop_loss, strategy_name, score
- [ ] Round entry and stop_loss to 3 decimals for consistency

## P1 - High Priority

### TODO 4: Add Signal Update Logic
- [ ] Query for existing active signal before creating new
- [ ] If exists and no material change → skip (just refresh timestamp)
- [ ] If material change → update metadata only (no new alert)
- [ ] Only send new alert for NEW signals or material updates

### TODO 5: Add Entry Zone Tolerance
- [ ] Modify fingerprint to use entry with ±0.2% tolerance
- [ ] Implement rounded entry for fingerprint key

### TODO 6: Test Comprehensive
- [ ] Test SOLUSDT 4H doesn't spam (should be once per 90 min)
- [ ] Test different entry prices in same zone treated as duplicate
- [ ] Test outcome tracking resolves correctly

## P2 - Medium Priority

### TODO 7: Signal State Machine
- [ ] Add state tracking: NEW → ACTIVE → UPDATE → RESOLVED → ARCHIVED
- [ ] Track entry_touched, TP1, TP2, TP3 events

### TODO 8: Callback Handler Audit
- [ ] Verify all button callback_data matches handler patterns
- [ ] Test inline button interactions

## Implementation Notes

### Timeframe Cooldown Mapping
```python
TIMEFRAME_COOLDOWNS = {
    "4h": 5400,    # 90 minutes - for SOLUSDT, XAUUSD, etc.
    "1d": 21600,   # 6 hours
    "1h": 1200,    # 20 minutes  
    "15m": 600,    # 10 minutes
    "5m": 300,     # 5 minutes
}
```

### Signal Dict Structure for Dedup
```python
signal_dict = {
    "asset": "SOLUSDT",
    "timeframe": "4h",
    "direction": "long",
    "entry": 69.410,  # rounded to 3 decimals
    "stop_loss": 66.629, 
    "strategy_name": "EMA_Trend",
    "score": 75.0,
    "created_at": datetime.utcnow()
}
```

## Test Commands

```bash
# Test dedup manually
python -c "
import asyncio
from engine.signal_deduplicator import SignalDeduplicator

async def test():
    dedup = SignalDeduplicator()
    
    # Test signal
    sig = {
        'asset': 'SOLUSDT',
        'timeframe': '4h', 
        'direction': 'long',
        'entry': 69.410,
        'stop_loss': 66.629,
        'strategy_name': 'EMA_Trend',
        'score': 75,
        'created_at': datetime.utcnow()
    }
    
    # First check - should be False
    is_dup = await dedup.is_duplicate(sig)
    print(f'First check: {is_dup}')
    
    # Mark seen
    await dedup.mark_seen(sig)
    
    # Second check - should be True  
    is_dup = await dedup.is_duplicate(sig)
    print(f'Second check: {is_dup}')

asyncio.run(test())
"
```

## Completion Criteria

1. ✅ SOLUSDT BUY signals appear at most once per 90 minutes (for 4H)
2. ✅ No duplicate alerts for same trading setup  
3. ✅ Outcome tracking finds and resolves trades
4. ✅ Inline buttons respond correctly
5. ✅ Signal updates don't create new alerts
