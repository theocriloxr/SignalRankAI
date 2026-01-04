# TradingView Integration Setup Guide

## Overview

SignalRankAI now includes TradingView technical analysis integration for enhanced signal quality and pair coverage. This document explains all configuration needed to enable and optimize the TradingView integration.

---

## Installation

### 1. Install TradingView-TA Library

First, install the required package:

```bash
pip install tradingview-ta
```

Or add to requirements.txt:

```
tradingview-ta>=3.3.0
```

Then update your environment:

```bash
pip install -r requirements.txt
```

**Note**: This library is optional. If not installed, SignalRankAI will gracefully fall back to Binance/CryptoCom/AlphaVantage without errors.

---

## Environment Variables

### Core TradingView Settings

#### `TRADINGVIEW_ENABLED` (Required)
- **Type**: Boolean
- **Default**: `false`
- **Valid Values**: `true`, `1`, `yes`, `on`
- **Purpose**: Enable/disable all TradingView features
- **Example**:
  ```bash
  export TRADINGVIEW_ENABLED=true
  ```

#### `TRADINGVIEW_MIN_CONFIDENCE` (Optional)
- **Type**: Float (0.0 to 1.0)
- **Default**: `0.40`
- **Range**: 0.2 to 0.8
- **Purpose**: Minimum indicator agreement required for a TradingView signal
- **Guidance**:
  - `0.2` = Very permissive (single indicator match)
  - `0.4` = Balanced (40% indicators agree) ← **Recommended**
  - `0.6` = Strict (60% indicators agree)
  - `0.8` = Very strict (80% indicators agree)
- **Example**:
  ```bash
  export TRADINGVIEW_MIN_CONFIDENCE=0.45
  ```

#### `TRADINGVIEW_SYMBOLS` (Optional)
- **Type**: Comma-separated string
- **Default**: Auto-discovery (uses Binance top pairs)
- **Purpose**: Specify which symbols to analyze with TradingView
- **Format**: `SYMBOL1,SYMBOL2,SYMBOL3` (no spaces)
- **Examples**:
  ```bash
  # Crypto only
  export TRADINGVIEW_SYMBOLS=BTCUSDT,ETHUSDT,BNBUSDT,ADAUSDT,DOGEUSDT
  
  # Mix crypto and forex
  export TRADINGVIEW_SYMBOLS=BTCUSDT,ETHUSDT,EURUSD,GBPUSD,USDJPY
  ```

---

### Data Source Configuration

#### `CRYPTO_TIMEFRAMES` (Related to TradingView)
- **Type**: Comma-separated string
- **Default**: `5m,15m,1h,4h,1d`
- **Purpose**: Timeframes to analyze for crypto assets
- **Supported by TradingView**: `1m, 5m, 15m, 1h, 4h, 1d, 1w`
- **Example**:
  ```bash
  export CRYPTO_TIMEFRAMES=5m,15m,1h,4h,1d
  ```

#### `FX_TIMEFRAMES` (Related to TradingView)
- **Type**: Comma-separated string
- **Default**: `1d`
- **Purpose**: Timeframes to analyze for forex assets
- **Note**: AlphaVantage (primary FX source) is rate-limited; TradingView can supplement
- **Example**:
  ```bash
  export FX_TIMEFRAMES=1h,4h,1d
  ```

#### `TRADABLE_ASSETS` (Optional)
- **Type**: Comma-separated string
- **Default**: Empty (auto-discover from Binance)
- **Purpose**: Fallback list of assets if discovery fails
- **Example**:
  ```bash
  export TRADABLE_ASSETS=BTCUSDT,ETHUSDT,BNBUSDT,EURUSD,GBPUSD
  ```

---

### Backup Data Sources (Keep Configured)

These remain your primary data sources. TradingView supplements them:

#### `BINANCE_API_KEY` (Optional but recommended)
- For fetching crypto candles and market data

#### `CRYPTOCOMPARE_API_KEY` (Optional)
- Alternative crypto data source

#### `ALPHAVANTAGE_API_KEY` (Optional but needed for FX)
- For forex pair data and daily candles

#### `BYBIT_API_KEY` (Optional)
- Alternative crypto source (public API available)

---

## Complete Configuration Example

### For Crypto-Only (Recommended Starting Point)

```bash
# === TradingView ===
export TRADINGVIEW_ENABLED=true
export TRADINGVIEW_MIN_CONFIDENCE=0.40
export TRADINGVIEW_SYMBOLS=BTCUSDT,ETHUSDT,BNBUSDT,ADAUSDT,DOGEUSDT,XRPUSDT,LINKUSDT,UNIUSDT

# === Crypto Data Sources ===
export CRYPTO_TIMEFRAMES=5m,15m,1h,4h,1d
export BINANCE_API_KEY=your_binance_key_here
export CRYPTOCOMPARE_API_KEY=your_cc_key_here

# === Strategy Settings ===
export CONSENSUS_MIN_SCORE=0.85
export PREMIUM_SCORE_THRESHOLD=55
export CYCLE_SLEEP_SECONDS=60
```

### For Crypto + Forex

```bash
# === TradingView ===
export TRADINGVIEW_ENABLED=true
export TRADINGVIEW_MIN_CONFIDENCE=0.40
export TRADINGVIEW_SYMBOLS=BTCUSDT,ETHUSDT,EURUSD,GBPUSD,USDJPY,AUDUSD

# === Crypto Data Sources ===
export CRYPTO_TIMEFRAMES=5m,15m,1h,4h,1d
export BINANCE_API_KEY=your_binance_key_here

# === Forex Data Sources ===
export FX_TIMEFRAMES=1h,4h,1d
export ALPHAVANTAGE_API_KEY=your_alphavantage_key_here
export ALPHAVANTAGE_MIN_SECONDS_BETWEEN_CALLS=15

# === Strategy Settings ===
export CONSENSUS_MIN_SCORE=0.85
export PREMIUM_SCORE_THRESHOLD=55
```

### For Maximum Pair Coverage

```bash
# === TradingView ===
export TRADINGVIEW_ENABLED=true
export TRADINGVIEW_MIN_CONFIDENCE=0.35  # Lower = more signals
export TRADINGVIEW_SYMBOLS=BTCUSDT,ETHUSDT,BNBUSDT,ADAUSDT,DOGEUSDT,XRPUSDT,LINKUSDT,UNIUSDT,LTCUSDT,AVAXUSDT,SOLusdt,MATICUSDT,EURUSD,GBPUSD,USDJPY,AUDUSD,NZDUSD,EURGBP

# === Primary Data Sources ===
export BINANCE_API_KEY=your_key
export CRYPTOCOMPARE_API_KEY=your_key
export ALPHAVANTAGE_API_KEY=your_key

# === Timeframes ===
export CRYPTO_TIMEFRAMES=1m,5m,15m,1h,4h,1d
export FX_TIMEFRAMES=1h,4h,1d

# === Relaxed Strategy Settings (More Signals) ===
export CONSENSUS_MIN_SCORE=0.70
export PREMIUM_SCORE_THRESHOLD=50
```

---

## How TradingView Integration Works

### Data Flow

```
┌─────────────────────────────────────────────────┐
│  TradingView Analysis                           │
│  (30+ Indicators Voting)                        │
│                                                  │
│  • RSI, MACD, Stochastic RSI                    │
│  • Bollinger Bands, ATR                         │
│  • Moving Averages (EMA, SMA)                   │
│  • Volume Profile, VWAP                         │
│  • And 20+ more...                              │
└────────────────────┬────────────────────────────┘
                     │
                     ↓
        ┌────────────────────────┐
        │ Consensus Voting       │
        │ (Indicator Strength)   │
        └────────────────────┬───┘
                             │
                ┌────────────┴────────────┐
                ↓                         ↓
           BUY Signal              SELL Signal
           (Confidence)            (Confidence)
                │                         │
                └────────────┬────────────┘
                             │
                             ↓
           ┌─────────────────────────────┐
           │ Signal Scoring & Consensus  │
           │ Filter                      │
           │                             │
           │ Threshold: 0.85 (default)   │
           └────────────┬────────────────┘
                        │
               ┌────────┴─────────┐
               ↓                  ↓
           PASS ✓            FAIL ✗
               │                  │
               ↓                  ↓
        Dispatch to Users   Archive
```

### Signal Characteristics

**TradingView signals have**:
- ✅ 30+ technical indicators consensus
- ✅ Configurable confidence threshold
- ✅ Support for crypto AND forex
- ✅ Multiple timeframes (1m to 1w)
- ✅ Automatic entry/stop/target calculation

**Comparison with other strategies**:

| Feature | Binance | CryptoCom | TradingView | Custom |
|---------|---------|-----------|-------------|--------|
| Crypto  | ✅ | ✅ | ✅ | ✅ |
| Forex   | ❌ | ❌ | ✅ | ❌ |
| Indicators | Limited | Limited | 30+ | Configurable |
| API Key Needed | No | Optional | No | No |
| Pair Coverage | Good | Good | Excellent | Custom |

---

## Testing Your Configuration

### 1. Validate Installation

```bash
python -c "from tradingview_ta import TA_Handler; print('✅ tradingview-ta installed')"
```

Expected output: `✅ tradingview-ta installed`

### 2. Test TradingView Connection

```bash
python -c "
import os
os.environ['TRADINGVIEW_ENABLED'] = 'true'
from data.fetcher import get_tradingview_candles
candles = get_tradingview_candles('BTCUSDT', '1h')
print(f'✅ TradingView connection OK: {len(candles)} candles')
"
```

Expected: `✅ TradingView connection OK: ...`

### 3. Test TradingView Signals

```bash
python -c "
import os
os.environ['TRADINGVIEW_ENABLED'] = 'true'
from strategies.tradingview import get_tradingview_signals
signals = get_tradingview_signals('BTCUSDT', '1h')
print(f'✅ Got {len(signals)} signals from TradingView')
for sig in signals:
    print(f'  - {sig.get(\"direction\")} {sig.get(\"confidence\"):.0%}')
"
```

Expected: `✅ Got X signals from TradingView`

### 4. Test Symbol Discovery

```bash
python -c "
import os
os.environ['TRADINGVIEW_ENABLED'] = 'true'
from data.fetcher import discover_tradingview_symbols
symbols = discover_tradingview_symbols('BINANCE')
print(f'✅ Discovered {len(symbols)} crypto pairs')
print('  Top 10:', symbols[:10])
"
```

---

## Troubleshooting

### "ModuleNotFoundError: No module named 'tradingview_ta'"

**Solution**: Install the package
```bash
pip install tradingview-ta
```

### "No TradingView signals generated"

**Check**:
1. Is `TRADINGVIEW_ENABLED=true`?
2. Is the pair valid on TradingView? (e.g., `BTCUSDT` for crypto, `EURUSD` for forex)
3. Is the timeframe supported? (1m, 5m, 15m, 1h, 4h, 1d, 1w)
4. Check logs: `grep -i tradingview logs.txt`

**Fix**: Lower `TRADINGVIEW_MIN_CONFIDENCE` to get more signals

```bash
export TRADINGVIEW_MIN_CONFIDENCE=0.30
```

### "TradingView signals too weak/unreliable"

**Solution**: Increase the confidence threshold
```bash
export TRADINGVIEW_MIN_CONFIDENCE=0.50
```

Or check the consensus threshold:
```bash
export CONSENSUS_MIN_SCORE=0.90
```

### "Too many signals, want to filter more"

**Solutions**:
1. Increase `TRADINGVIEW_MIN_CONFIDENCE` (e.g., 0.5 or higher)
2. Increase `CONSENSUS_MIN_SCORE` (e.g., 0.90)
3. Reduce `TRADINGVIEW_SYMBOLS` to fewer pairs
4. Reduce `CRYPTO_TIMEFRAMES` or `FX_TIMEFRAMES`

### "TradingView takes too long"

**Causes**: Network latency, rate limiting, or too many symbols

**Solutions**:
1. Reduce number of pairs in `TRADINGVIEW_SYMBOLS`
2. Reduce number of timeframes analyzed
3. Add rate limiting:
   ```bash
   export TRADINGVIEW_RATE_LIMIT=2  # seconds between requests
   ```

---

## Performance Notes

### API Limits

TradingView library rates:
- ✅ Free tier (no API key needed)
- ✅ No hard rate limits (community-friendly)
- ⚠️ Best practice: 2-3 seconds between requests

### Data Freshness

TradingView data:
- 🟢 Real-time (updated as market trades)
- 🟡 1-2 minute delay common (free tier)
- 🟢 Sufficient for day trading and above

### Recommended for Production

```bash
# Conservative (reliable, fewer signals)
TRADINGVIEW_ENABLED=true
TRADINGVIEW_MIN_CONFIDENCE=0.50
TRADINGVIEW_SYMBOLS=BTCUSDT,ETHUSDT,EURUSD,GBPUSD

# Balanced (good signal volume)
TRADINGVIEW_ENABLED=true
TRADINGVIEW_MIN_CONFIDENCE=0.40
TRADINGVIEW_SYMBOLS=BTCUSDT,ETHUSDT,BNBUSDT,ADAUSDT,EURUSD,GBPUSD,USDJPY

# Aggressive (more signals, test first)
TRADINGVIEW_ENABLED=true
TRADINGVIEW_MIN_CONFIDENCE=0.35
TRADINGVIEW_SYMBOLS=[20+ pairs]
```

---

## Monitoring

### Logs to Check

```bash
# TradingView-specific logs
tail -f logs.txt | grep -i tradingview

# Signal generation logs
tail -f logs.txt | grep "signal\|consensus"

# Error logs
tail -f logs.txt | grep ERROR
```

### Metrics to Watch

1. **Signal Volume**: Should increase with TradingView enabled
2. **Win Rate**: Monitor `/stats` command for win rate by strategy
3. **Consensus Percentage**: TradingView signals should be well-agreed
4. **False Signals**: Check outcome reports

---

## Advanced Configuration

### Multi-Strategy Weighting

TradingView can be weighted differently:

```python
# In engine/consensus.py or config.py
STRATEGY_WEIGHTS = {
    'trend': 1.0,
    'momentum': 1.0,
    'volatility': 0.8,
    'structure': 0.9,
    'tradingview': 1.2,  # Boost TradingView slightly
}
```

### Custom Symbol List

Instead of auto-discovery, specify exact pairs:

```bash
# Crypto focus
export TRADINGVIEW_SYMBOLS=BTCUSDT,ETHUSDT,BNBUSDT,ADAUSDT,DOGEUSDT,XRPUSDT

# Forex focus
export TRADINGVIEW_SYMBOLS=EURUSD,GBPUSD,USDJPY,AUDUSD,CADUSD,NZDUSD

# Mixed strategy
export TRADINGVIEW_SYMBOLS=BTCUSDT,ETHUSDT,EURUSD,GBPUSD,USDJPY
```

---

## Quick Start Summary

### Minimal Setup (5 minutes)

```bash
# 1. Install library
pip install tradingview-ta

# 2. Enable in environment
export TRADINGVIEW_ENABLED=true

# 3. (Optional) Specify symbols
export TRADINGVIEW_SYMBOLS=BTCUSDT,ETHUSDT,EURUSD,GBPUSD

# 4. Deploy and test
python main.py
```

### Production Setup

1. Install: `pip install -r requirements.txt`
2. Configure `.env` with all variables above
3. Test: Run validation commands in "Testing Your Configuration"
4. Deploy to Railway/server
5. Monitor: Check logs and `/stats` command

---

## Next Steps

1. ✅ Install `tradingview-ta`
2. ✅ Set `TRADINGVIEW_ENABLED=true`
3. ✅ Choose crypto, forex, or mixed symbols
4. ✅ Deploy and monitor for 24 hours
5. ✅ Adjust confidence and consensus thresholds based on results
6. ✅ Enjoy expanded pair coverage and improved signal quality!

---

**Questions?** Check the main README.md or see the bot's `/help` command for more information.
