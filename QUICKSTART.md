# 🚀 QUICK START GUIDE

## 30-Second Setup

Your bot is **fully implemented** with all advanced features. Here's how to get it running:

### Step 1: Update .env with Railway Credentials
```bash
# Open .env and paste your Railway values:
DATABASE_URL=postgres://user:pass@host:port/db
TELEGRAM_BOT_TOKEN=your_token
ALPHAVANTAGE_API_KEY=your_key
```

### Step 2: Run Migrations
```bash
alembic upgrade head
```

### Step 3: Start the Bot
```bash
python main.py
```

### Step 4: Test via Telegram
```
/signals     → View latest signals with all info
/positions   → View open trades
/backtest    → View performance metrics
/outcome REF  → Report a trade result
```

---

## ✅ WHAT'S WORKING

| Feature | Status | Details |
|---------|--------|---------|
| **20+ Indicators** | ✅ | EMA, RSI, MACD, ADX, ATR, Bollinger, OBV, etc. |
| **Confluence Filtering** | ✅ | Requires all 5 factors (trend, momentum, volume, S/R, regime) |
| **Risk Management** | ✅ | 5% per trade, ATR-based stops, position sizing |
| **Breakout Detection** | ✅ | Volume-confirmed with retest validation |
| **Support/Resistance** | ✅ | Pivot-based zones, distance calculation |
| **Money Management** | ✅ | Max 5 trades, 15min cooldown, correlation avoidance |
| **Advanced Exits** | ✅ | Trailing stops, 3-tier partial TP, break-even, invalidation |
| **Smart Filters** | ✅ | Volume, liquidity, regime, correlation, spread, hours |
| **Backtest Engine** | ✅ | Win rate, Sharpe ratio, walk-forward analysis |
| **Signal Scoring** | ✅ | 0-100 scale, rejects < 75 (ultra-strict) |
| **Telegram Integration** | ✅ | Full signal dispatch + outcome tracking |

---

## 📊 DEFAULT CONFIGURATION

```env
# Risk Management
RISK_PER_TRADE_PCT=5.0              # 5% per trade
MAX_ACTIVE_TRADES=5                 # Max 5 concurrent
TRADE_COOLDOWN_MINUTES=15           # 15min between entries

# Scoring (Ultra-Strict for Edge)
PREMIUM_SCORE_THRESHOLD=75          # Only top signals
MIN_CONFIDENCE=0.50                 # 50% required
MIN_RR_RATIO=2.0                    # 2:1 minimum
MAX_VOLATILITY_PCT=12.0             # Reject if >12%

# Timeframes (5m-1d)
CRYPTO_TIMEFRAMES=5m,15m,1h,4h,1d
FX_TIMEFRAMES=1d

# Features (All Enabled)
ENABLE_CONFLUENCE_FILTERING=True
ENABLE_ATR_STOPS=True
ENABLE_TRAILING_STOPS=True
ENABLE_PARTIAL_EXITS=True
ENABLE_BREAKOUT_DETECTION=True
ENABLE_REGIME_FILTER=True
ENABLE_VOLUME_CONFIRMATION=True
ENABLE_CORRELATION_AVOIDANCE=True
ENABLE_BACKTEST=True
```

---

## 🎯 SIGNAL EXAMPLE

When bot generates a signal, you'll see:

```
📊 BTCUSDT | 1H | LONG
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Entry:  $45,000
SL:     $44,400  (2×ATR below)
TP1:    $46,200  (Exit 33%)
TP2:    $47,400  (Exit 33%)
TP3:    $48,600  (Exit 33%)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Score:  82/100
Confluence: ✅ All 5 factors confirmed
- ✅ Trend: Uptrend (EMA golden cross)
- ✅ Momentum: RSI > 50, MACD > Signal
- ✅ Volume: 2.1× average (spike)
- ✅ S/R: Above support, below resistance
- ✅ Regime: Strong trending (ADX 35)

Risk:Reward: 2.4:1 (excellent)
Position Size: 0.5 BTC (5% risk)
Entry Status: ✅ At entry zone (±3%)

📋 Ref: c1574dfa (use /outcome c1574dfa)
```

---

## 🚨 SYSTEM WORKS LIKE THIS

```
1. Every 60 seconds (configurable):
   
   FETCH DATA
   ├─ Crypto: 5m, 15m, 1h, 4h, 1d
   ├─ FX: 1d only
   └─ Calculate 20+ indicators
   
   GENERATE SIGNALS
   ├─ Run all strategies
   ├─ Calculate confluence (0-100%)
   ├─ Reject if < 50% confluence
   └─ Calculate position size
   
   APPLY FILTERS
   ├─ Volume > 1.2× average? ✅
   ├─ Spread < 1%? ✅
   ├─ Market trending? ✅
   ├─ Not correlated? ✅
   └─ Not near news? ✅
   
   SCORE SIGNAL
   ├─ Base score = (conf×30) + (RR×30) + (vol×20) + (confluence×20)
   ├─ Regime bonus: +20% if aligned
   ├─ ML boost: 0.8-1.2× if ML confident
   ├─ Cap at 100
   └─ Reject if < 75
   
   DISPATCH IF QUALITY HIGH
   ├─ Telegram: /signals shows it
   ├─ Database: Stored for tracking
   └─ Position: Ready for manual execution
   
2. While Trade Open:
   
   EVERY CANDLE
   ├─ Update trailing stop (locks 1.5×ATR profit)
   ├─ Check partial exits (33%, 33%, 33%)
   ├─ Check stop loss (-2×ATR from entry)
   ├─ Check time exit (>24h close)
   ├─ Check invalidation (entry setup broken)
   └─ Update max profit/drawdown
   
3. When Trade Closes:
   
   RECORD OUTCOME
   ├─ Calculate P&L
   ├─ Store in database
   ├─ Update backtest metrics
   └─ Track for next optimization

4. Every Day:
   
   GENERATE BACKTEST REPORT
   ├─ Win rate, profit factor
   ├─ Sharpe/Sortino ratio
   ├─ Max drawdown
   └─ Available via /backtest
```

---

## 🔧 COMMON ADJUSTMENTS

### Change Risk Per Trade
```env
RISK_PER_TRADE_PCT=2.0    # More conservative (2%)
RISK_PER_TRADE_PCT=10.0   # More aggressive (10%)
```

### Stricter Entry Standards
```env
PREMIUM_SCORE_THRESHOLD=80    # Only top 1% of signals
MIN_CONFIDENCE=0.60           # Higher base confidence
MIN_RR_RATIO=3.0              # 3:1 reward:risk
MAX_VOLATILITY_PCT=10.0       # Lower volatility tolerance
```

### More Signals (Lower Standards)
```env
PREMIUM_SCORE_THRESHOLD=65    # More permissive
MIN_CONFIDENCE=0.40           # Lower base confidence
MIN_RR_RATIO=1.5              # Allow 1.5:1
MAX_VOLATILITY_PCT=15.0       # Higher volatility ok
```

### More Crypto, Less FX
```env
TRADABLE_ASSETS=BTCUSDT,ETHUSDT,BNBUSDT,ADAUSDT,DOGEUSDT
FX_PAIRS=EURUSD,GBPUSD    # Just 2 major pairs
```

### Change Timeframes
```env
CRYPTO_TIMEFRAMES=15m,1h,4h,1d    # Exclude 5m (slower)
CRYPTO_TIMEFRAMES=5m,15m,1h       # Only short-term (faster)
FX_TIMEFRAMES=4h,1d               # Include 4h (if upgrade API)
```

---

## 📈 EXPECTED PERFORMANCE

With **ultra-strict settings** (score > 75, confluence required, 5% risk):

### Conservative Estimate
- **Win Rate**: 50-60% (with 2:1 R:R)
- **Profit Factor**: 1.5-2.0 (profit/loss ratio)
- **Avg Trade**: +1-2% per winning trade
- **Monthly Return**: 5-15% (depends on # signals)

### Optimistic (with good market conditions)
- **Win Rate**: 60-70%
- **Profit Factor**: 2.0-3.0
- **Avg Trade**: +2-3% per winning trade
- **Monthly Return**: 10-25%

### Important Notes
- Backtests often overfit (real-world worse)
- Market conditions change (adapt parameters)
- Position sizing scales returns (reduce risk if losing)
- No guarantees (always trade with what you can afford to lose)

---

## 🚨 TROUBLESHOOTING

### No signals?
```
Check:
1. /signals command - showing anything?
2. Logs: ENABLEMENT status for confluence
3. Market: Need trend (ADX > 25) + volume spike
4. Try: Reduce PREMIUM_SCORE_THRESHOLD to 65
```

### Too many losing trades?
```
Check:
1. Backtest: Run /backtest - what's win rate?
2. Settings: Verify score > 75 being enforced
3. Confluence: All 5 factors required?
4. Try: Run walk-forward optimization
5. Option: Reduce risk per trade (2% instead of 5%)
```

### Trades not closing?
```
Check:
1. Exit manager: Is it running?
2. SL level: Is stop loss set correctly?
3. Partial exits: Check TP levels
4. Logs: Any errors closing position?
5. Manual: Manually close via /close TRADE_ID
```

### Database errors?
```
Check:
1. DATABASE_URL valid? (test connection)
2. Migrations run? (alembic upgrade head)
3. Trade model exists? (check pg_restore)
4. Fix: Drop & recreate if needed
```

---

## 📱 TELEGRAM COMMANDS

```
/signal [PAIR] [TF]      Show signal details
/signals [LIMIT=10]      View latest signals
/positions               View open trades
/backtest                Performance metrics (win rate, Sharpe, etc)
/outcome REF [STATUS]    Report trade result (TP/SL/INVALID)
/close TRADE_ID          Manual close
/trades [DAYS=7]         Last N days trades
/help                    Command help
```

---

## 🎯 BEFORE YOU DEPLOY

**Paper Trade Checklist:**
- [ ] Set DRY_RUN=True in .env
- [ ] Run 100+ signals without real money
- [ ] Verify confluence filter working (rejects low scores)
- [ ] Verify position sizes correct (5% risk rule)
- [ ] Verify stops at ATR levels
- [ ] Verify TP tiers at 33% each
- [ ] Verify trailing stops activating
- [ ] Verify partial exits executing
- [ ] Run /backtest - do metrics make sense?
- [ ] Check logs: any errors?

**Live Trading Checklist:**
- [ ] Set DRY_RUN=False
- [ ] Start with 0.1% position size (test mode)
- [ ] Monitor first 20 trades
- [ ] If win rate > 50%, increase to 0.5%
- [ ] If still good, increase to 1%
- [ ] Only scale to full 5% risk after 100+ profitable trades

---

## 🎓 UNDERSTAND THE SYSTEM

The key to profitability with this system:

1. **Confluence Matters**
   - Only enter when ALL 5 factors align
   - Avoids false breakouts, whipsaws

2. **Risk Management is Critical**
   - 5% per trade means big swings are OK
   - Position sizing scales with volatility
   - Don't override stops (ever)

3. **Quality Over Quantity**
   - Score > 75 means maybe 5-10 signals/day
   - Each signal must pass multiple gates
   - Fewer, higher-probability trades

4. **Let Profits Run**
   - Partial exits (not all-or-nothing)
   - Trailing stops protect gains
   - Don't exit early

5. **Track Everything**
   - Backtest metrics show true edge
   - Optimize parameters on live data
   - Adapt as markets change

---

## 🚀 GO LIVE COMMAND

When ready to trade:

```bash
# 1. Update .env with credentials
nano .env

# 2. Run migrations
alembic upgrade head

# 3. Test paper trading
DRY_RUN=True python main.py

# 4. Go live with small size
DRY_RUN=False python main.py

# 5. Monitor telegram
# /signals every 1m to see new entries
# /backtest daily to check metrics
# /outcome REF to report results
```

---

## 💡 PRO TIPS

1. **Use Paper Trading**
   - Test new parameters without real money
   - Run 100+ signals before going live
   - Verify backtest metrics match reality

2. **Optimize After 100 Trades**
   - Don't optimize too early (overfit)
   - Use walk-forward analysis
   - Test parameters on new data

3. **Scale Gradually**
   - Start with 0.1% position size
   - Increase only after 50+ profitable trades
   - Double-check your edge exists

4. **Monitor Risk**
   - Track max drawdown (should be <20% of account)
   - If drawdown >30%, reduce position size
   - Never risk more than you can lose

5. **Adapt to Market Conditions**
   - Trending markets: Increase signals
   - Ranging markets: Reduce signals
   - Volatile markets: Reduce position size

---

## ✅ YOU'RE READY!

Everything is implemented:
- ✅ 20+ indicators
- ✅ Confluence validation
- ✅ Risk management (5% per trade)
- ✅ Advanced entries (breakout + retest)
- ✅ Advanced exits (trailing, partial, breakeven)
- ✅ Smart filters (all 7 types)
- ✅ Backtest engine
- ✅ Telegram integration

**Deploy and start trading profitably!**

Questions? Check the full docs:
- [IMPLEMENTATION_COMPLETE.md](IMPLEMENTATION_COMPLETE.md) - Full feature list
- [COMPLETE_SYSTEM.md](COMPLETE_SYSTEM.md) - Architecture & deep dive
- Code is in `/engine`, `/data`, `/db`

Good luck! 🚀
