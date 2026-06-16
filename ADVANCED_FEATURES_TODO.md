# SignalRankAI Advanced Features Implementation

## Task List

### 1. Advanced Risk & Market Defenses

- [ ] **A. Macro News "Kill Switch"** - Add 30-min filter for USD-sensitive assets
  - File: `services/economic_calendar.py`
  - Task: Add check for `minutes_until_high_impact_news < 30` blocking USD, Gold (XAUUSD), US Indices
  
- [ ] **B. Multi-Timeframe Confluence Gate** - Enforce 4h/Daily EMA alignment
  - File: `engine/mtf_analysis.py`
  - Task: Modify strategies to require MTF alignment before ML scorer
  
- [ ] **C. Low Volatility Filter** - ATR-based dead market detection
  - File: `engine/advanced_filters.py` or new file
  - Task: If 1h ATR < 50% of 14-day avg ATR, reject signal

### 2. AI & Machine Learning Expansions

- [ ] **D. Gemini Live Market Sentiment** - Predictive alpha integration
  - File: `services/gemini_ml.py` + `engine/core.py`
  - Task: Before finalizing signal, call Gemini with 5 news headlines, drop/score-reduce if bearish
  
- [ ] **E. Dynamic Risk/Reward using ML** - TP1/TP2/TP3 targets
  - File: `engine/advanced_exit_manager.py`
  - Task: Create multi-target exits based on momentum/ATR

### 3. Telegram Bot & User Experience

- [ ] **F. Interactive Inline Keyboards** - Add buttons to signals
  - File: `signalrank_telegram/bot.py`, `signalrank_telegram/formatter.py`
  - Task: Add View Chart, Ask Gemini Why, Performance Stats buttons
  
- [ ] **G. /stats and /leaderboard Commands** - Win rate tracking
  - File: `signalrank_telegram/commands.py`
  - Task: Implement /stats with weekly wins/losses/win rate
  
- [ ] **H. Auto-Execution Webhooks** - JSON webhook payloads
  - File: `signalrank_telegram/webhook.py` (new)
  - Task: Generate JSON for Cornix/PineConnector/MT5

### 4. Data Provider Resiliency

- [ ] **I. Waterfall Provider Fallback** - Already implemented in `data/fetcher.py`
  - Status: COMPLETE - Multi-provider fallback already in place

---

## Implementation Order

1. Start with Risk Features (A, B, C) - Core pipeline protection
2. Then AI/ML Features (D, E) - Enhanced signal quality
3. Then Telegram Features (F, G, H) - User experience
4. Verify Data Provider (I) - Already complete
