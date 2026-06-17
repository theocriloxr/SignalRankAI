# Professional Grade Upgrade TODO

## COMPLETED (Phase 1: Core Fixes)
✅ 1. SignalOrchestrator - Professional-grade signal delivery with state management
   - Created: `services/signal_orchestrator.py`
   - Implements: is_significant_update() to compare signal states
   - Implements: SignalOrchestrator class for editMessageText support
   - Implements: Cooldown registry per signal_id

✅ 2. Asset Class Enable/Disable - CRYPTO_ENABLED and COMMODITY_ENABLED
   - Updated: `config.py` - Already had settings, verified
   - Updated: `engine/core.py` - Added crypto_enabled and commodity_enabled checks

✅ 3. Config Settings for Spam Prevention
   - Added: SIGNAL_NOTIFY_COOLDOWN_SECONDS (default: 900 = 15 min)
   - Added: SIGNAL_UPDATE_THRESHOLD_PCT (default: 0.1%)
   - Added: SIGNAL_ORCHESTRATOR_ENABLED (default: True)

## PENDING / NEXT PHASES

### Phase 2: Signal State Persistence (Priority: HIGH)
- [ ] Integrate SignalOrchestrator with delivery flow in core.py
- [ ] Store signal hash signature in SignalDelivery table
- [ ] Use editMessageText API for updates instead of new messages

### Phase 3: Daily Digest & Performance Reporting (Priority: MEDIUM)
- [ ] Implement automated daily digest at market close
- [ ] Track signals issued vs signals triggered
- [ ] Track winning trades vs losing trades
- [ ] Calculate total PnL percentage

### Phase 4: Advanced Order Types (Priority: MEDIUM)
- [ ] Trailing Stop Loss support (ATR-based trailing)
- [ ] Multiple TP levels with partial exits

### Phase 5: Data Provider Redundancy (Priority: MEDIUM)
- [ ] Failover from Yahoo Finance to Alpha Vantage
- [ ] WebSocket fallback for real-time prices

### Phase 6: Observability (Priority: LOW)
- [ ] Prometheus metrics for engine pulse
- [ ] Grafana dashboard setup
- [ ] Alerting for API rate limits

## Quick Start for Enabled Additional Assets

To enable crypto and commodity trading:

```bash
# In Railway/Docker environment variables:
CRYPTO_ENABLED=true
COMMODITY_ENABLED=true
STOCKS_ENABLED=true
FX_ENABLED=true
```

## Testing the Orchestrator

```python
from services.signal_orchestrator import is_significant_update, get_signal_orchestrator

# Test significant update detection
old_signal = {'entry': 201.634, 'stop_loss': 201.464, 'take_profit': 202.5}
new_signal = {'entry': 201.625, 'stop_loss': 201.464, 'take_profit': 202.5}

# Should return False (entry change is only 0.009 ~0.0045% < threshold)
result = is_significant_update(old_signal, new_signal, 0.1)
print(f"Significant update: {result}")  # False

# Use orchestrator for dispatch decisions
orchestrator = get_signal_orchestrator()
result = orchestrator.dispatch_signal(signal_data, chat_id=12345, existing_message_id=67890)
print(f"Action: {result['action']}")  # 'edit', 'new', or 'suppress'
```

## Files Modified/Created

1. `services/signal_orchestrator.py` (NEW)
2. `config.py` (UPDATED - added signal orchestrator settings)
3. `engine/core.py` (UPDATED - added CRYPTO_ENABLED and COMMODITY_ENABLED checks)
