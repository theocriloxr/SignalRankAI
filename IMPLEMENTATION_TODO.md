# SignalRankAI Codex Audit - Implementation TODO

## Status: PHASE 1 & 2 COMPLETE

## Phase 1: P0 - Must Be Done Before Production

### 1.1 Symbol Normalization ✅
- [x] Create `utils/symbol_normalizer.py`
- [x] Normalize: BTCUSD, BTCUSDT, BTC/USD → BTCUSDT
- [x] Support: Crypto, Forex, Stocks, Commodities, Indices

### 1.2 Command Registry ✅
- [x] Create `utils/command_registry.py`
- [x] Single source of truth for commands
- [x] Generate /help, menus, permissions, handlers

### 1.3 Active Signal Registry ✅
- [x] Create database migration (`migrations/versions/active_signal_registry.py`)
- [x] Fields: signal_id, fingerprint, asset, direction, timeframe, status, message_id, chat_id
- [x] Track: entry_hit, tp1_hit, tp2_hit, tp3_hit, sl_hit, expiry
- [x] SQL script: `ADD_ACTIVE_SIGNALS_TABLE.sql`

### 1.4 Message Editing Engine
- [ ] Update signal delivery to use editMessageText
- [ ] Signal lifecycle: SIGNAL CREATED → ENTRY HIT → TP1 HIT → TP2 HIT
- [ ] Replace "NEW SIGNAL" spam with edits

### 1.5 Universal Outcome Tracking
- [ ] Every signal must end as: TP1/TP2/TP3/SL/Expired/Cancelled
- [ ] No signal should remain ACTIVE forever

## Phase 2: P1 - Signal Quality

### 2.1 Correlation Engine ✅
- [x] Create `engine/correlation_engine.py`
- [x] Track: JPY, USD, Gold, Oil, Indices, Crypto exposure
- [x] Prevent: AUDJPY SELL + CADJPY SELL + NZDJPY SELL

### 2.2 Multi-Timeframe Fusion
- [ ] Combine: BTC 1H BUY + 4H BUY + 1D BUY
- [ ] Output: BTC BUY (1D Bullish, 4H Bullish, 1H Pullback)

### 2.3 Regime Detection
- [ ] Detect: Trending, Ranging, Volatile, Accumulation, Distribution
- [ ] Use before strategy selection

## Phase 3: P1.5 - Dynamic Strategy Vision

### 3.1 Strategy Orchestrator
- [ ] Create `strategy_orchestrator.py`
- [ ] Inputs: Asset, Timeframe, Volatility, Regime, Session, Spread
- [ ] Output: Strategy Weighting

### 3.2 ML Weighting Layer
- [ ] Store: Strategy, Asset, Timeframe, Regime, Result
- [ ] Self-adjust based on performance

## Phase 4: P2 - Revenue Features

### 4.1 Portfolio Intelligence
- [ ] Commands: /portfolio, /risk, /exposure
- [ ] Show: Crypto, Forex, Commodity Exposure, Total Risk

### 4.2 AI Coach
- [ ] Commands: /coach
- [ ] Explain: Why trade won, Why trade lost, How to improve

### 4.3 Public Track Record
- [ ] Show: 30-day win rate, 90-day win rate, Profit factor, Drawdown
- [ ] Per asset class

## Phase 5: P3 - Copy Trading

### 5.1 Tier-Based Execution
- [ ] Free: Delayed Signals
- [ ] Premium: Live Signals
- [ ] VIP: Copy Trade
- [ ] Elite: Auto Execute

### 5.2 Risk Profiles
- [ ] Users choose: Conservative, Balanced, Aggressive
- [ ] Sizing changes automatically
