# SignalRankAI Professional-Grade Upgrade Plan

## Executive Summary

This plan outlines a comprehensive upgrade to transform SignalRankAI from a functional signal generator into a professional-grade automated trading platform. The upgrade addresses four pillars: Consistency, Data Integrity, Statistical Edge, and Infrastructure Resilience.

---

## 1. PROBLEM ANALYSIS

### 1.1 Root Causes Identified

#### Issue 1: Repeating Signals (Spamming)
**Root Cause**: The engine treats each cycle as a fresh signal event, generating new "VIP SIGNAL DETECTED" messages instead of updating existing ones.

Evidence from logs:
- Signal IDs: `2543ad58-83e` and `dc8a483b-53e` showing duplicate messages
- Entry price moving: `201.634 → 201.625 → 201.609` triggers new events

**Solution Required**: Implement SignalOrchestrator with stateful tracking and editMessageText support.

#### Issue 2: Asset Class Limitation
**Root Cause**: Missing environment variable handling for CRYPTO_ENABLED, COMMODITY_ENABLED in core.py (lines 1301-1306 only handle FX and STOCKS).

**Solution Required**: Add equivalent flags for CRYPTO_ENABLED and COMMODITY_ENABLED.

---

## 2. CORE IMPROVEMENTS

### 2.1 SignalOrchestrator Implementation

Create `services/signal_orchestrator.py`:

```python
class SignalOrchestrator:
    """Stateful signal management with editMessageText support."""
    
    def __init__(self, db_session, bot_token):
        self.db = db_session
        self.bot = Bot(token=bot_token)
    
    async def dispatch(self, signal_payload):
        # 1. Check if signal exists in database
        # 2. If exists, check if update is significant (>0.1% price move)
        # 3. If significant, editMessageText; else suppress
        # 4. If new, send new message
```

**Key Functions**:
- `generate_deterministic_hash()` - Creates signature based on trading values
- `is_significant_update()` - Calculates if levels moved enough
- `dispatch()` - Handles create vs update logic

### 2.2 Asset Class Enablement

Update `config.py` or core.py to add:

```python
# Asset class toggles (add to existing FX_ENABLED, STOCKS_ENABLED)
CRYPTO_ENABLED = os.getenv('CRYPTO_ENABLED', 'true').lower() == 'true'
COMMODITY_ENABLED = os.getenv('COMMODITY_ENABLED', 'true').lower() == 'true'
```

Update `core.py` lines ~1301-1306:
```python
fx_enabled = _env_bool('FX_ENABLED', True)
stocks_enabled = _env_bool('STOCKS_ENABLED', True)
crypto_enabled = _env_bool('CRYPTO_ENABLED', True)
commodity_enabled = _env_bool('COMMODITY_ENABLED', True)

# Filter assets based on all flags
crypto_assets = [a for a in open_assets if is_crypto(a)] if crypto_enabled else []
commodity_assets = [a for a in open_assets if is_commodity(a)] if commodity_enabled else []
```

### 2.3 Throttling/Cooldown Implementation

Add Redis-based cooldown:
- `last_notify_ts:{signal_id}` - Last notification timestamp
- Cooldown period: 30 minutes (configurable via `SIGNAL_COOLDOWN_MINUTES`)

---

## 3. DATABASE SCHEMA UPDATES

### 3.1 TradeHistory Table (New)

```sql
CREATE TABLE trade_history (
    id SERIAL PRIMARY KEY,
    signal_id VARCHAR(50) NOT NULL,
    asset VARCHAR(20) NOT NULL,
    timeframe VARCHAR(10),
    direction VARCHAR(10) NOT NULL,  -- 'long' or 'short'
    entry_price DECIMAL(18, 8),
    exit_price DECIMAL(18, 8),
    stop_loss DECIMAL(18, 8),
    take_profit DECIMAL(18, 8),
    status VARCHAR(20),  -- 'pending', 'active', 'closed'
    outcome VARCHAR(20),  -- 'tp1', 'tp2', 'tp3', 'sl', 'invalidated', 'missed'
    r_multiple DECIMAL(10, 4),
    pnl_pct DECIMAL(10, 4),
    opened_at TIMESTAMP,
    closed_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);
```

### 3.2 SignalDelivery Enhancement (UUID Persistence)

```sql
ALTER TABLE signal_delivery 
ADD COLUMN signature_hash VARCHAR(64),
ADD COLUMN message_id BIGINT,
ADD COLUMN edit_count INTEGER DEFAULT 0;
```

---

## 4. ANALYTICAL ENHANCEMENTS

### 4.1 Regime Detection

Enhance `engine/regime.py`:
- ADX for trend strength
- Bollinger Band width for volatility
- Only allow "Breakout" in high volatility with rising ADX
- Use "Mean Reversion" in contracting volatility

### 4.2 CorrelationMatrix

Add `engine/correlation_matrix.py`:
- Calculate correlation between currency pairs
- Reduce position size when correlated signals detected
- Example: If CHFJPY BUY and EURCHF LONG → reduce size

### 4.3 Backtest-on-the-Fly

Add walk-forward analysis:
- Simulate last 20 candles before dispatch
- Penalize confidence score if strategy lost money on last 5 tests

---

## 5. FEATURE ADDITIONS

### 5.1 Daily Digest

Add scheduled job for end-of-market-day report:
- Signals issued vs triggered
- Winning vs losing trades
- Total PnL percentage

### 5.2 Trailing Stop Loss

Enhance `engine/exit_manager.py`:
- Once trade hits TP1, trail stop loss at fixed ATR distance
- Protects profits during "Moonbag" scenarios

### 5.3 Data Source Redundancy

Enhance `data/fetcher.py`:
- Primary: Yahoo Finance
- Fallback: Alpha Vantage
- Fallback: Direct exchange WebSocket

---

## 6. COMMAND IMPROVEMENTS

### 6.1 Existing Commands to Fix/Enhance

1. `/signal` - Single signal lookup by ID
2. `/signals` - List all signals with filtering
3. Add status display (ACTIVE, EXPIRED, CLOSED)

### 6.2 New Commands

1. `/stats` - Real-time win rate, exposure, PnL
2. `/pause [asset]` - Temporarily blacklist asset
3. `/force_sync` - Trigger Gemini audit pipeline
4. `/risk` - Configure risk % (already exists, verify)
5. `/execution` - Set auto/manual mode

---

## 7. INFRASTRUCTURE

### 7.1 Observability

Add Prometheus metrics:
- `engine_scanned_total`
- `signals_delivered_total`
- `api_latency_seconds`

Add Grafana dashboard for visualization.

### 7.2 Health Checks

Add `/ops_health` command that returns:
- Database connectivity
- Redis connectivity
- API provider status
- Engine pulse status

---

## 8. IMPLEMENTATION ROADMAP

### Phase 1: Critical Fixes (Week 1)
- [ ] Implement SignalOrchestrator
- [ ] Add CRYPTO_ENABLED, COMMODITY_ENABLED flags
- [ ] Add editMessageText support in bot.py
- [ ] Add cooldown throttling

### Phase 2: Data Integrity (Week 2)
- [ ] Create TradeHistory table
- [ ] Add signature_hash to SignalDelivery
- [ ] Implement OutcomeSubscriber

### Phase 3: Analytical Edge (Week 3)
- [ ] Enhance regime detection
- [ ] Implement CorrelationMatrix
- [ ] Add backtest-on-the-fly

### Phase 4: Features (Week 4)
- [ ] Daily Digest job
- [ ] Trailing Stop Loss
- [ ] Data source redundancy

### Phase 5: Infrastructure (Week 5)
- [ ] Prometheus metrics
- [ ] Health check dashboard
- [ ] CI/CD pipeline

---

## 9. DEPENDENCIES

### Required Python Packages
```txt
redis>=5.0.0
asyncpg>=0.29.0
prometheus-client>=0.19.0
httpx>=0.26.0
```

### Environment Variables Required
```bash
# Asset toggles
CRYPTO_ENABLED=true
COMMODITY_ENABLED=true
STOCKS_ENABLED=true
FX_ENABLED=true

# SignalOrchestrator
SIGNAL_UPDATE_THRESHOLD_PCT=0.1
SIGNAL_COOLDOWN_MINUTES=30

# Prometheus
PROMETHEUS_ENABLED=true
```

---

## 10. SUCCESS METRICS

| Metric | Current | Target |
|--------|---------|--------|
| Signal duplicates per ID | 3-5 | 0 |
| Asset class coverage | FX only | FX+Crypto+Stock+Commodity |
| True win rate tracking | Partial | Complete |
| Message edit rate | 0% | 80%+ |
| Daily digest delivery | Manual | Automated |

---

## 11. FILES TO MODIFY

1. **services/signal_orchestrator.py** (CREATE)
2. **engine/core.py** (MODIFY - lines ~1301-1306)
3. **signalrank_telegram/bot.py** (MODIFY - dispatch logic)
4. **config.py** (MODIFY - add asset toggles)
5. **db/models.py** (MODIFY - add fields)
6. **engine/exit_manager.py** (MODIFY - trailing stops)
7. **engine/regime.py** (MODIFY - enhance detection)
8. **engine/correlation_matrix.py** (CREATE)

---

## 12. TESTING STRATEGY

### Unit Tests
- SignalOrchestrator.is_significant_update()
- Config asset class toggles
- Cooldown throttling

### Integration Tests
- Full signal flow: generate → store → deliver → update
- Asset class routing (crypto, stock, commodity)

### Manual Tests
- /signal command with different signal IDs
- /signals command with filters
- Daily digest delivery

---

*Plan Version: 1.0*
*Created: 2024*
*Status: Ready for Implementation*
