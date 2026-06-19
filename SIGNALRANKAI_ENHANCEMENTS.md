# SignalRankAI New Features Implementation Plan

## Phase 1: Core Intelligence Features

### 1. Opportunity Ranking Engine ✓
- **Status**: IN PROGRESS
- Signals ranked globally by score
- Tier-based delivery:
  - Free: Top 3 daily
  - Premium: Top 10 daily
  - VIP: All qualified signals
- Implementation location: `signalrank_telegram/tier_delivery.py`

### 2. Asset Correlation Engine
- **Status**: PENDING
- Groups correlated assets:
  - JPY (CADJPY, AUDJPY, NZDJPY, etc.)
  - USD (DXY, related pairs)
  - Gold (XAU, XAG, miners)
  - Crypto (BTC, ETH, alts)
  - Risk-on / Risk-off regimes
- Implementation location: `services/asset_mapper.py`

### 3. Portfolio Intelligence Layer
- **Status**: PENDING
- Display:
  - Current Portfolio Risk status
  - Open Trades count
  - Exposure by asset class (Forex/Crypto/Metals/Stocks)
  - Correlation warnings
- Implementation location: `signalrank_telegram/portfolio.py` (new)

### 4. Risk Management Layer
- **Status**: PENDING
- Daily Drawdown Limits: 2%, 4%, 6% (tier-based)
- Weekly/Monthly Drawdown Limits
- Auto Shutdown when exceeded
- Implementation location: `core/risk_monitor.py` (new)

---

## Phase 2: AI Features

### 5. AI Trade Coach
- **Status**: PENDING
- Analyze last 20 trades
- Identify mistakes (closing winners early, etc.)
- Provide recommendations
- Implementation location: `ai/trade_coach.py` (new)

### 6. AI Trade Replay
- **Status**: PENDING
- `/replay SIGNAL_ID` command
- Show signal generation, price movement, TP hits
- Implementation location: `signalrank_telegram/commands.py`

### 7. AI Market Narrative
- **Status**: PENDING
- Daily AI Brief:
  - USD strength
  - Gold direction
  - Indices outlook
  - Crypto sentiment
- Implementation location: `ai/market_narrative.py` (new)

### 8. AI Portfolio Manager
- **Status**: PENDING
- `/portfolio` command with AI analysis
- Exposure reduction recommendations
- Rebalancing suggestions
- Implementation location: `ai/portfolio_manager.py` (new)

---

## Phase 3: Trust & Verification

### 9. Trust Layer (Win Rate Stats)
- **Status**: PENDING
- Strategy win rates by:
  - EMA Trend: 71%
  - Breakout: 68%
  - Liquidity Sweep: 74%
- By asset class:
  - Crypto / Forex / Stocks / Indices / Commodities
- Implementation location: `signalrank_telegram/stats.py`

### 10. News Impact Engine
- **Status**: PENDING
- Check events: FOMC, NFP, CPI, ECB, BoE, BoJ
- Reduce confidence during high-impact news
- Implementation location: `data/news_impact.py` (new)

---

## Phase 4: Platform Features

### 11. Signal Marketplace
- **Status**: FUTURE
- Community strategies
- Subscribable AI Trend/Swing/Scalper/News/Macro
- Long-term feature

### 12. AI Assistant Vision
- **Status**: FUTURE
- Bloomberg Terminal + TradingView + ChatGPT combined
- Analyze, Review, Explain commands
- Long-term vision

---

## Architecture Recommendations

Proposed service layers:
- Market Data Service
- Signal Service
- Risk Service
- Execution Service
- Outcome Service
- Portfolio Service
- Notification Service
- AI Service
- Telegram Service
- Dashboard Service

## Status Legend
- ✓ = COMPLETE
- IN PROGRESS = Currently being implemented
- PENDING = Not started
- FUTURE = Long-term goal
