# SignalRankAI Infrastructure Upgrade Plan

## Phase 1: Critical Fixes (Database & Zombie Assets)

### 1.1 NullPool Strategy (db/session.py)
**Issue**: TooManyConnectionsError on Railway due to connection pool limits
**Solution**: Replace traditional pool with NullPool for instant open/close
```python
from sqlalchemy.pool import NullPool
engine = create_async_engine(url, poolclass=NullPool)
```
**Status**: REQUIRES IMPLEMENTATION

### 1.2 Hard Blacklist in Core (engine/core.py)
**Issue**: USDCUSDT and other zombie stablecoins still trading from database
**Solution**: Add HARD_BLACKLIST array check before trade execution
```python
HARD_BLACKLIST = ["USDCUSDT", "USDTPERF", "DAIUSDT", "FDUSDUSDT"]
if asset in HARD_BLACKLIST:
    continue
```
**Status**: REQUIRES IMPLEMENTATION

## Phase 2: New Alpha Generation Modules

### 2.1 Market Regime Filter (engine/regime_filter.py)
**Purpose**: Filter out sideways market signals using ADX
**Implementation**: New file using pandas_ta for ADX calculation
**Status**: NEW FILE NEEDED

### 2.2 Smart Risk Sizer (engine/risk_manager.py upgrade)
**Purpose**: ML-conviction based position sizing
**Logic**:
- ML Prob >= 85%: Risk 1.5%
- ML Prob >= 75%: Risk 1.0%  
- ML Prob < 75%: Risk 0.5%
**Status**: ENHANCE EXISTING

### 2.3 Trade Manager - Auto-Breakeven (engine/trade_manager.py)
**Purpose**: Move SL to entry when TP1 is hit
**Implementation**: New file with async process_active_trades loop
**Requirements**:
- Need new DB column: sl_moved_to_be on Trade model
- Need TP1 tracking
**Status**: NEW FILE NEEDED

### 2.4 Order Book Microstructure (engine/microstructure.py)
**Purpose**: Check order book imbalance before trading
**Implementation**: New file checking Binance depth API
**Logic**:
- LONG blocked if Ask > Bid * 1.5
- SHORT blocked if Bid > Ask * 1.5
**Status**: NEW FILE NEEDED

## Integration Points

### engine/core.py Integration:
1. Add regime_filter check before signal generation
2. Add microstructure check before dispatch
3. Add HARD_BLACKLIST check
4. Use enhanced risk_manager

### worker/ loop Integration:
1. Add trade_manager periodic call (every 1 min)

## Database Migrations Needed:
1. Add sl_moved_to_be column to trades table
2. Add tp1, tp2, tp3 columns to trades table

## Execution Order:
1. Fix db/session.py (NullPool) - CRITICAL
2. Add HARD_BLACKLIST to core.py - CRITICAL  
3. Create engine/regime_filter.py
4. Enhance engine/risk_manager.py
5. Create engine/trade_manager.py
6. Create engine/microstructure.py
7. Integrate all into core.py
8. Test and deploy
