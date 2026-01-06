# Stock Trading Feature

## Overview
SignalRankAI now supports stock trading in addition to cryptocurrency trading. The system can generate signals for trending stocks using the same advanced filtering and ML scoring system.

## Activation

Set the following environment variable in Railway:

```bash
STOCK_TRADING_ENABLED=true
```

## Data Provider

Stock data is fetched using Yahoo Finance (yfinance), which works globally including Nigeria:

- **Provider**: Yahoo Finance (free, no API key needed)
- **Coverage**: US stocks, major international stocks
- **Timeframes**: 1m, 5m, 15m, 1h, 4h, 1d
- **Reliability**: High (not geo-blocked in Nigeria)

## Stock Discovery

The system automatically discovers trending stocks using:

1. **Volume Leaders**: Stocks with highest trading volume
2. **Volatility Movers**: Stocks with significant price movement
3. **Technical Breakouts**: Stocks breaking key resistance levels

Popular tickers included:
- **Tech**: AAPL, MSFT, GOOGL, AMZN, TSLA, NVDA, META
- **Finance**: JPM, BAC, GS, V, MA
- **Energy**: XOM, CVX
- **Healthcare**: JNJ, UNH, PFE
- **Consumer**: WMT, HD, NKE

## Signal Generation

Stock signals follow the same pipeline as crypto:

1. **Data Fetching**: Real-time candles from Yahoo Finance
2. **Indicator Calculation**: RSI, MACD, BB, EMA, Volume
3. **Strategy Execution**: Momentum, Trend, Structure, Volatility
4. **Consensus Filter**: Multi-strategy agreement required
5. **ML Scoring**: XGBoost probability assessment
6. **Risk Management**: ATR-based SL/TP, position sizing
7. **Validation**: Signal validator ensures correctness

## Delivery

- **FREE**: 3 signals/day (delayed summaries, mix of crypto + stocks)
- **PREMIUM**: Instant delivery, all signals (crypto + stocks)
- **VIP**: Ultra-quality signals first, elite filter enabled

## Current Price Display

Stock prices are fetched live in `/signal` and `/outcome` commands:

```
Current Price: $185.42
P/L: +2.3%
Progress to TP: 45%
```

## Configuration

### Required Environment Variables
```bash
STOCK_TRADING_ENABLED=true  # Enable stock trading
```

### Optional Environment Variables
```bash
TRADABLE_ASSETS=AAPL,MSFT,TSLA  # Comma-separated stock symbols (optional)
```

### Disable if Needed
```bash
STOCK_TRADING_ENABLED=false  # Disable stock trading (crypto only)
```

## Signal Examples

### Stock Signal (LONG)
```
🟢 LONG AAPL 1h
Entry: $184.50
Stop Loss: $182.00
Take Profit: $189.00
RR: 1.8
Score: 78.5
ML: 82% ✅
Regime: UPTREND
```

### Stock Signal (SHORT)
```
🔴 SHORT TSLA 4h
Entry: $245.80
Stop Loss: $250.20
Take Profit: $236.00
RR: 2.2
Score: 81.2
ML: 79% ✅
Regime: DOWNTREND
```

## Limitations

1. **Market Hours**: US stock market is closed on weekends and US holidays
2. **Pre/Post Market**: Limited data during pre/post market hours
3. **Volatility**: Stocks generally less volatile than crypto (wider timeframes recommended)
4. **Correlation**: Tech stocks often correlate (diversification recommended)

## Monitoring

Check stock signals in logs:

```bash
# Railway logs
railway logs --service signalrank-ai

# Look for stock signals
grep "AAPL\|MSFT\|TSLA" logs.txt
```

## Deactivation

To disable stock trading:

```bash
STOCK_TRADING_ENABLED=false
```

Or remove the environment variable entirely.

## Support

Stock trading uses the same system as crypto:
- ✅ Signal validation
- ✅ Real-time price fetching
- ✅ Deduplication per user
- ✅ Signal corrections
- ✅ Outcome tracking
- ✅ ML scoring

No additional configuration needed beyond `STOCK_TRADING_ENABLED=true`.
