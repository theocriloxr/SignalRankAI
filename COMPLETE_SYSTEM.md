# SignalRankAI - Complete Trading System

A professional-grade trading bot with **all phases** of advanced features implemented.

## ✅ IMPLEMENTED FEATURES

### 📈 Phase 1: Foundation (Core Strategy)
- **Multi-timeframe indicators**: EMA (20, 50, 200), SMA, RSI, MACD, ADX, ATR, Bollinger Bands
- **Trend analysis**: EMA/SMA golden cross, market structure (HH/LL detection)
- **Volume confirmation**: Volume ratio, OBV (On-Balance Volume), volume spike detection
- **Market regime detection**: Trending vs Ranging classification
- **Momentum indicators**: RSI, MACD with signal line, momentum calculations
- **Confluence scoring**: Requires multiple signals before entry (trend + momentum + volume + regime)

### 🎯 Phase 1: Risk Management (5% per trade)
- **Fixed % risk per trade**: 5% default (configurable)
- **ATR-based stops**: Stop loss = entry - 2*ATR, TP = entry + 4*ATR
- **Position sizing**: Calculated based on risk per trade and stop distance
- **Dynamic position sizing**: Adjusted for volatility regime and correlation risk
- **R:R validation**: Minimum 2:1 reward:risk ratio enforced

### 📊 Phase 2: Entry Precision
- **Breakout detection**: Price breaks above resistance with volume confirmation
- **Retest validation**: Detects price retesting broken level for optimal entry
- **Support/Resistance zones**: Pivot point-based S/R identification
- **Zone validation**: Ensures entry respects nearby S/R levels
- **Confluence entry**: Wait for multiple confirmations before executing

### 📉 Phase 3: Money Management
- **Max active trades**: 5 trades maximum (configurable)
- **Trade cooldown**: 15 minutes minimum between entries (configurable)
- **Correlation avoidance**: Won't open highly correlated pairs (>0.7 correlation)
- **Dynamic position sizing**: Reduces size in high volatility or high correlation scenarios
- **Position tracking**: `trades` table tracks open and closed positions with full metadata

### 🔄 Phase 4: Advanced Exit Logic
- **Trailing stops**: Locks in profit by moving SL up by 1.5*ATR
- **Multi-tier profit targets**: Exit 33% at TP/3, 33% at TP*2/3, 33% at TP
- **Break-even stops**: Moves SL to entry+buffer after reaching 2R profit
- **Partial exits**: Execute exit in chunks at different profit levels
- **Time-based exits**: Exit if trade held >24 hours without reaching TP
- **Signal invalidation**: Exit if entry conditions no longer met
- **Exit suggestions**: Provides recommendations based on RSI, MACD, momentum

### 🧠 Phase 5: Smart Filters
- **Volume spike filter**: Requires >1.2x average volume (liquidity)
- **Liquidity checker**: Rejects pairs with >1% spread
- **Regime filter**: Adjusts signals based on trending vs ranging market
- **Correlation manager**: Avoids same-direction trades in correlated pairs
- **Spread control**: Rejects trades with excessive bid-ask spread
- **Trading hours**: Avoids low-liquidity periods (21:00-23:00 UTC gap)
- **News event avoidance**: Can register and avoid high-impact news events

### 📊 Phase 6: Analytics & Optimization
- **Backtest engine**: Full trade history with metrics
- **Performance metrics**:
  - Win rate, avg win/loss, profit factor
  - Max drawdown, expectancy, Sharpe ratio, Sortino ratio
  - Average hold time
- **Walk-forward optimization**: Tests parameters over rolling windows
- **Parameter optimization**: Grid search for best parameters
- **Trade export**: Save all trades to CSV

---

## 🔧 SYSTEM ARCHITECTURE

### Core Modules

```
data/indicators.py         → All technical indicators (EMA, RSI, MACD, etc.)
engine/risk_manager.py     → Position sizing, stops, risk calculation
engine/exit_manager.py     → Trail stops, partial exits, invalidation checks
engine/filters.py          → Smart filters, regime detection, correlation
engine/backtest.py         → Analytics, walk-forward testing, optimization
engine/scoring.py          → Confluence validation, signal scoring
engine/core.py             → Main trading loop with all systems integrated
db/models.py               → Trade model for position tracking
```

### Data Flow

```
1. Fetch Market Data
   ↓
2. Calculate Indicators (20+ technical indicators)
   ↓
3. Generate Signals (all strategies)
   ↓
4. Apply Filters (volume, liquidity, regime, correlation)
   ↓
5. Validate Confluence (trend + momentum + volume + regime)
   ↓
6. Calculate Risk & Position Size (5% per trade)
   ↓
7. Set Stops & TP (ATR-based, 2:1 minimum R:R)
   ↓
8. Score Signal (confluence + regime + ML + R:R)
   ↓
9. Dispatch if Score > 75 (ultra-strict)
   ↓
10. Manage Position
    - Check trailing stop
    - Execute partial exits
    - Monitor time-based exits
    - Detect signal invalidation
    ↓
11. Close Trade & Record Stats
    - Calculate P&L
    - Update backtest metrics
    - Track for optimization
```

---

## 📈 TRADING CONFIGURATION

### Risk Management (.env)
```env
RISK_PER_TRADE_PCT=5.0              # 5% per trade
MAX_ACTIVE_TRADES=5                 # Max 5 concurrent
TRADE_COOLDOWN_MINUTES=15           # 15min gap between entries
MIN_RR_RATIO=2.0                    # 2:1 minimum
```

### Scoring Thresholds
```env
PREMIUM_SCORE_THRESHOLD=75          # Ultra-strict quality gate
MIN_CONFIDENCE=0.50                 # 50% base confidence required
ML_PROB_THRESHOLD=0.65              # 65% ML certainty required
MAX_VOLATILITY_PCT=12.0             # Reject if >12% volatility
```

### Timeframes (5m - 1d as requested)
```env
CRYPTO_TIMEFRAMES=5m,15m,1h,4h,1d  # All timeframes
FX_TIMEFRAMES=1d                    # FX daily only
```

### Assets (Crypto + FX)
```env
TRADABLE_ASSETS=BTCUSDT,ETHUSDT,...  # Crypto pairs
FX_PAIRS=EURUSD,GBPUSD,USDJPY,...    # 8 major FX pairs
FX_MAX_PAIRS_PER_CYCLE=3             # Rate limit for free tier
```

---

## 🚀 QUICK START

### 1. Set Up Environment
```bash
# Copy Railway credentials to .env
cp .env.example .env
# Update with your Railway DATABASE_URL, API keys, etc.
```

### 2. Install Dependencies
```bash
pip install -r requirements.txt
```

### 3. Run Migrations
```bash
alembic upgrade head
```

### 4. Start the Bot
```bash
python main.py
```

### 5. Monitor via Telegram
```
/signal - View latest signal with entry, SL, TP
/signals - View all active signals
/outcome <signal_id> - Report trade outcome
/backtest - View performance metrics
/positions - View open trades
```

---

## 📊 SIGNAL ANATOMY

Each signal includes:

```json
{
  "asset": "BTCUSDT",
  "timeframe": "1h",
  "direction": "long",
  "entry": 45000,
  "stop_loss": 44100,
  "take_profit": [46200, 47400, 48600],
  "score": 82,
  "confluence": 100,          // All 5 factors confirmed
  "rr_ratio": 2.4,            // Risk/reward ratio
  "atr": 300,                 // Stop distance
  "regime": "trending",       // Market condition
  "volume_ratio": 2.1,        // Above average
  "breakout": true,           // Breakout + retest
  "entry_status": "AT_ENTRY", // ±3% entry zone
  "signal_id": "c1574dfa",    // For /outcome tracking
  "risk_pct": 5.0,            // 5% of account
  "position_size": 0.5,       // In base asset
  "timestamp": "2026-01-05T12:34:56Z"
}
```

---

## 🧮 CONFLUENCE SCORING

A signal requires **ALL** of these to have high confluence:

1. **Trend Alignment** (EMA/SMA golden cross)
   - ✅ Price > EMA20 > EMA50 > EMA200 = strong uptrend
   - ✅ Price < EMA20 < EMA50 < EMA200 = strong downtrend

2. **Momentum Confirmation** (RSI + MACD)
   - ✅ Long: RSI > 50 AND MACD > Signal Line
   - ✅ Short: RSI < 50 AND MACD < Signal Line

3. **Volume Confirmation**
   - ✅ Current Volume > 1.2x average volume

4. **Support/Resistance Respect**
   - ✅ Long: Price above support level
   - ✅ Short: Price below resistance level

5. **Market Regime Alignment**
   - ✅ Trending: ADX > 25 (strong trend exists)
   - ✅ Ranging: ADX < 20 (range conditions)

**Score**: Number of confirmations × 20% = 0-100% confluence

Signal rejected if confluence < 50%.

---

## 💰 PROFIT TARGET CALCULATION

### ATR-Based (Dynamic)
```
Entry = Market Price
SL = Entry - 2*ATR (longs) or Entry + 2*ATR (shorts)
TP1 = Entry + 4*ATR  (33% exit)
TP2 = Entry + 8*ATR  (33% exit)
TP3 = Entry + 12*ATR (33% exit)
```

### Example
```
BTCUSDT @ $45,000
ATR (14-period) = $300

SL = $45,000 - (2 × $300) = $44,400
TP1 = $45,000 + (4 × $300) = $46,200  ✅ Exit 33%
TP2 = $45,000 + (8 × $300) = $47,400  ✅ Exit 33%
TP3 = $45,000 + (12 × $300) = $48,600 ✅ Exit 33%

Risk = $600
Reward = $3,600
R:R = 6:1 (excellent!)
```

---

## 📈 POSITION MANAGEMENT

### Entry
1. ✅ Confluence check (all 5 factors)
2. ✅ Filter check (volume, liquidity, regime, correlation)
3. ✅ Calculate position size (5% risk ÷ SL distance)
4. ✅ Set stops at ATR levels
5. ✅ Dispatch signal to Telegram

### Active Management
1. **Every candle:**
   - ✅ Update trailing stop (locks in 1.5*ATR profit)
   - ✅ Check partial exit targets
   - ✅ Monitor time-based exit (24h max)
   - ✅ Detect signal invalidation

2. **Trailing Stop Example:**
   ```
   Entry @ $45,000
   Current @ $46,200 (+2.67%)
   Trailing SL = $46,200 - (1.5 × $300) = $45,750
   (Protects $750 profit if reverses)
   ```

### Exit Triggers
- **Take Profit**: Hit TP level (execute partial exits)
- **Stop Loss**: Hit SL level (exit full position)
- **Signal Invalidation**: Entry conditions no longer met
- **Time Exit**: Held >24h without reaching TP
- **Breakeven Stop**: Hit 2R profit, move SL to entry
- **Trailing Stop**: Hit trailed SL in trend

---

## 📊 BACKTEST RESULTS FORMAT

```
╔════════════════════════════════════════╗
║         BACKTEST SUMMARY               ║
╠════════════════════════════════════════╣
║ Total Trades:              42         ║
║ Wins / Losses:        28 / 14         ║
║ Win Rate:              66.67%         ║
│────────────────────────────────────────│
║ Total P&L:            $2,840.50       ║
║ Avg P&L/Trade:           $67.63       ║
║ Avg Win:                 $125.45       ║
║ Avg Loss:               -$58.20        ║
│────────────────────────────────────────│
║ Profit Factor:             2.15        ║
║ Expectancy:               $67.63       ║
║ Max Drawdown:           -$540.30       ║
║ Avg Hold Time:             6.2h        ║
│────────────────────────────────────────│
║ Sharpe Ratio:              1.84        ║
║ Sortino Ratio:             2.31        ║
╚════════════════════════════════════════╝
```

---

## 🔍 TROUBLESHOOTING

### "No signals being generated"
- Check confluence filter: may be too strict
- Verify market regime: need strong trend (ADX > 25)
- Check volume: needs >1.2x average
- Monitor logs: `grep "confluence\|score" logs.txt`

### "Too many losing trades"
- System is designed to be CONSERVATIVE (5% risk per trade)
- Verify backtest shows edge before trading live
- Run walk-forward optimization to find best parameters
- Check signal invalidation logic is working

### "Position not closing at TP"
- Verify partial exit targets are configured
- Check trailing stop isn't interfering
- Monitor SL level vs current price
- Confirm exit signals are being processed

### "FX candles not fetching"
- AlphaVantage free tier: 25 calls/day max
- Reduce FX_MAX_PAIRS_PER_CYCLE to 2-3
- Consider upgrading to premium tier
- Or use alternative provider (OANDA, Forex.com)

---

## 🎯 NEXT STEPS FOR PRODUCTION

1. ✅ **Test on paper trading** (DRY_RUN=True)
   - Verify all signals execute correctly
   - Monitor position management
   - Review backtest metrics

2. ✅ **Optimize parameters** (optional)
   - Run walk-forward optimization
   - Find best ATR period, EMA lengths
   - Adjust thresholds for your market

3. ✅ **Go live with small size**
   - Start with 1-2 trades max
   - Monitor P&L and drawdown daily
   - Scale up if performance consistent

4. ✅ **Monitor & improve**
   - Track win rate and profit factor
   - Review losing trades for patterns
   - Adjust filters if needed

---

**Built with Professional Trading Standards**
- Ultra-strict quality gates (score > 75)
- Comprehensive risk management (5% per trade)
- Advanced position management (trailing stops, partial exits)
- Smart filtering (volume, liquidity, regime, correlation)
- Full analytics (backtest, walk-forward optimization)

✅ Ready to deploy!
