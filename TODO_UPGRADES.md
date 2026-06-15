# SignalRankAI Upgrade Implementation TODO

## Phase 1: Pipeline Reliability

### ✅ P0: Redis Pulse Metrics Fix
- **Status**: ✅ COMPLETE (Already in core.py)
- **Location**: engine/core.py ~line 1684 - `global_stats_instance.increment_scanned(1)` inside asset loop

### ✅ P1: Crypto Data Starvation Fix (Minimum Candles)
- **Status**: ✅ COMPLETE
- **Task**: Update limit from 200→720 in cryptocompare_adapter.py
- **Files**: 
  - [x] data/connectors/cryptocompare_adapter.py (limit: 200 → 720)
  - [x] Fallback section also updated to 720

### ✅ P2: Explicit Rejection Logging
- **Status**: ✅ ALREADY IMPLEMENTED
- **Details**: Detailed logging exists at all gate failure points:
  - Line 1573: HARDBLACKLIST skip logging
  - Line 1592: DATA STARVATION logging
  - Line 1635: Candle/indicator diagnostics
  - Line 1670: no_trade_zone gate logging
  - Line 1712: Insufficient candle count warnings
  - Line 2471: cooldown cycle skip logging

### ✅ P3: Macro Degradation Fallback
- **Status**: ✅ ALREADY IMPLEMENTED in core.py
- **Location**: Lines ~1090-1212 have fallback to cached values when DXY/VIX fail

## Phase 2: Structural Proactive Upgrades (Future)

### 🔧 P4: Dual-Layer Provider Failover
- **Status**: NOT IMPLEMENTED - Would require new fetch_candles_with_failover function
- **Task**: Add fetch_candles_with_failover function
- **Location**: data/market_data.py

### 🔧 P5: AI-Driven Asset Discovery
- **Status**: NOT IMPLEMENTED - Would require new gemini_portfolio_manager.py
- **Task**: Create gemini_portfolio_manager.py
- **Location**: services/

### 🔧 P6: Dead Engine Telemetry
- **Status**: PARTIAL - circuit_breaker exists, but no 12-hour flatline webhook
- **Task**: Create engine_health_tracker.py with webhook
- **Location**: core/

---

## Implementation Log

*2024-XX-XX - Started upgrade implementation*
*2024-XX-XX - P1 Complete: CryptoCompare limit increased to 720*
*2024-XX-XX - Review: P0, P2, P3, P7 already implemented in core.py*
