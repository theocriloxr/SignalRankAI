# SignalRankAI Master Upgrade Plan

## Executive Summary
This document outlines the comprehensive upgrades to make SignalRankAIbulletproof based on the issues identified in the Master Blueprint.

---

## Phase 1: Pipeline Reliability (Immediate Fixes)

### 1. Fix Redis Pulse Metrics (COMPLETED - Already Implemented)
**Location**: `engine/core.py`
**Status**: ✅ ALREADY FIXED

The code already has the fix at line ~750:
```python
# === PHASE 1 FIX: Increment global_stats_instance.scanned for each asset analyzed ===
global_stats_instance.increment_scanned(1)
```

**Verification**: No action required - this is already in place.

---

### 2. Crypto Data Starvation Fix (Minimum Candles)
**Issue**: CoinGecko/CryptoCompare is only pulling ~84-200 hourly candles, breaking 100/200-period indicators.

**Proposed Fix**:
- Update `data/connectors/cryptocompare_adapter.py` to pull **720 candles** (30 days of hourly data)
- Currently: `"limit": 200`
- Target: `"limit": 720`

**Files to Modify**:
- `data/connectors/cryptocompare_adapter.py`
- `data/market_data.py` (increase limit to 750 for safety margin)

---

### 3. Graceful Macro Degradation (Forex/Indices Bypass)
**Issue**: If DXY/VIX fails, system blocks all technical trade signals.

**Proposed Fix**:
The macro fallback is already implemented in `engine/core.py` (~lines 600-700):
- `_macro_fallback_cache` provides cached values
- Multiple retry formats for DXY
- Logger warnings on cache fallback usage

**Status**: ✅ ALREADY IMPLEMENTED - Add verification logging.

**Files to Verify**:
- `engine/core.py` - ensure macro warnings are logged properly

---

## Phase 2: Structural Proactive Upgrades

### 4. Dual-Layer Provider Failover (Data Redundancy)
**Issue**: Single point failure when primary API (Polygon/Yahoo) fails.

**Proposed Solution**: Create failover wrapper in `data/market_data.py`:

```python
async def fetch_candles_with_failover(asset_symbol: str, timeframe: str) -> list:
    """Fetch with primary/backup provider failover."""
    # Try primary
    candles = await primary_provider.fetch(asset_symbol, timeframe)
    if candles and len(candles) >= MIN_CANDLES:
        return candles
    
    logger.warning(f"Primary failed for {asset_symbol}. Routing to fallback...")
    return await backup_provider.fetch(asset_symbol, timeframe)
```

**Files to Create/Modify**:
- `data/market_data.py` - add `fetch_candles_with_failover` function

---

### 5. AI-Driven Asset Discovery (Gemini Portfolio Manager)
**Issue**: Hardcoded fallback list when Binance is blocked.

**Proposed Solution**: Create Gemini-powered asset selector:

```python
async def gemini_select_assets(vix_level: float, regime: str) -> List[str]:
    """Use Gemini to dynamically select top 20 assets based on market conditions."""
    prompt = f"""Based on VIX={vix_level}, regime={regime}, 
    select top 20 most liquid crypto assets for today.
    Return as comma-separated list."""
    # Call Gemini API
```

**Files to Create**:
- `services/gemini_portfolio_manager.py` - new service file

---

### 6. "Dead Engine" Telemetry Circuit Breaker
**Issue**: Engine yields 0 signals silently - no notification.

**Proposed Solution**: Create health tracker:

```python
class EngineHealthTracker:
    def __init__(self):
        self.consecutive_zero_signals = 0
        self.alert_threshold_hours = 12
    
    def record_cycle(self, signals_generated: int):
        if signals_generated == 0:
            self.consecutive_zero_signals += 1
        else:
            self.consecutive_zero_signals = 0
        
        if self.consecutive_zero_signals >= self.alert_threshold_cycles:
            self.send_critical_alert()
```

**Files to Create**:
- `core/engine_health_tracker.py` - new file
- Integrate into `engine/core.py` main_loop

---

### 7. Explicit Rejection Logging
**Issue**: Silent `continue` statements hide why assets fail.

**Proposed Solution**: Replace all silent continues with detailed warnings:

**Current (Bad)**:
```python
if not has_candles:
    continue
```

**Proposed (Good)**:
```python
if not has_candles:
    logger.warning(f"⏩ Skipped {asset}: insufficient candle depth (Had 0, need 200)")
    continue
```

**Files to Modify**:
- `engine/core.py` - add explicit logging throughout the pipeline
- Add to all gate failure points

---

## Implementation Priority

| Priority | Task | Status | Effort |
|----------|------|--------|--------|
| P0 | Redis Pulse Fix | ✅ COMPLETE | N/A |
| P1 | Crypto Data Starvation Fix | 🔧 TODO | Low |
| P2 | Explicit Rejection Logging | 🔧 TODO | Medium |
| P3 | Dead Engine Telemetry | 🔧 TODO | Medium |
| P4 | Provider Failover | 🔧 TODO | Medium |
| P5 | AI Asset Discovery | 🔧 TODO | High |

---

## Notes

- The codebase already has significant infrastructure in place
- Many "fixes" mentioned are already implemented
- Main gaps are in explicit logging and health telemetry
- Provider failover would add significant robustness

---

*Generated: SignalRankAI Upgrade Plan*
*For questions, refer to the original Master Blueprint document.*
