# Multi-Provider Data Integration - Complete

## Overview
Your SignalRankAI bot now supports **5 data providers** with automatic fallbacks, covering **crypto, FX, and stocks**.

## Integrated Data Providers

### 1. **Polygon.io** (Premium Multi-Asset)
- **Coverage**: Stocks, FX, Crypto
- **Quality**: Institutional-grade
- **Free Tier**: 5 calls/minute
- **Setup**: `POLYGON_API_KEY=your_key`
- **Status**: ✅ Integrated

### 2. **Twelve Data** (Generous Free Tier)
- **Coverage**: Stocks, FX, Crypto
- **Quality**: Excellent
- **Free Tier**: 800 calls/day
- **Setup**: `TWELVEDATA_API_KEY=your_key`
- **Status**: ✅ Integrated

### 3. **Yahoo Finance** (Free, No API Key)
- **Coverage**: Stocks, FX, Crypto
- **Quality**: Good
- **Free Tier**: Unlimited (relaxed rate limits)
- **Setup**: None required (uses yfinance library)
- **Status**: ✅ Integrated

### 4. **OANDA** (Bank-Grade FX)
- **Coverage**: FX only
- **Quality**: Bank-grade
- **Setup**: Not available in Nigeria ⚠️
- **Status**: ❌ Disabled (geographic restrictions)

### 5. **Existing Providers**
- **Binance/Bybit**: Crypto (already working)
- **CryptoCompare**: Crypto fallback
- **AlphaVantage**: FX (legacy, limited)
- **Status**: ✅ Kept as fallbacks

## Automatic Fallback Logic

### Crypto Priority Order
```
1. Binance (fast, free, excellent)
2. Bybit (if Binance blocked)
3. CryptoCompare (fallback)
4. Yahoo Finance (works for major crypto)
5. Polygon.io (if API key set)
6. Twelve Data (if API key set)
```

### FX Priority Order
```
1. AlphaVantage (free, no restrictions)
2. Yahoo Finance (free, no key needed)
3. Polygon.io (if API key set)
4. Twelve Data (if API key set)
```

### Stocks Priority Order
```
1. Yahoo Finance (free, no key needed)
2. Polygon.io (if API key set)
3. Twelve Data (if API key set)
```

## Stock Trading Features

### Stock Symbol Discovery
Automatically discovers top stocks from:
1. **Manual List**: `STOCK_TICKERS=AAPL,MSFT,GOOGL`
2. **S&P 500 Liquid Stocks**: 50+ hardcoded mega-caps
3. **Polygon.io Live**: Top volume stocks (if API key available)

### Supported Stock Symbols (Default)
**Tech**: AAPL, MSFT, GOOGL, AMZN, NVDA, META, TSLA, AMD, INTC, NFLX, ADBE, CRM, ORCL, CSCO  
**Finance**: JPM, BAC, WFC, GS, MS, C, V, MA  
**Healthcare**: JNJ, UNH, PFE, ABBV, TMO, MRK, ABT  
**Consumer**: WMT, HD, DIS, NKE, MCD, SBUX, KO, PEP  
**Industrial**: BA, CAT, GE, MMM, HON  
**Energy**: XOM, CVX, COP, SLB  
**Communication**: T, VZ, CMCSA

### Market Hours Support
- Stocks respect market hours (9:30 AM - 4:00 PM ET)
- Crypto: 24/7
- FX: Sunday 22:00 UTC - Friday 22:00 UTC

## Environment Variables

### Required (No Changes Needed)
```bash
DATABASE_URL=postgresql://...
TELEGRAM_TOKEN=your_bot_token
```

### Optional Data Provider Keys
```bash
# Polygon.io (recommended for stocks + crypto + FX)


# Twelve Data (generous free tier)


# OANDA - DISABLED (NOT AVAILABLE IN NIGERIA)

# Legacy (keep for fallback)
ALPHAVANTAGE_API_KEY=your_alpha_key
CRYPTOCOMPARE_API_KEY=your_cc_key
```

### Stock Trading Settings
```bash
# Enable stock signals (default: false for now)
STOCK_TRADING_ENABLED=true

# Manual stock list (optional)
STOCK_TICKERS=AAPL,MSFT,GOOGL,AMZN,NVDA,META,TSLA

# Auto-discover top N stocks (default: 20)
STOCK_TRENDING_TOP_N=20

# Multi-provider fallback (default: true)
USE_MULTI_PROVIDER_DATA=true
```

### Rate Limit Tuning
```bash
# Polygon (default: 12 seconds = 5 calls/min)
POLYGON_MIN_SECONDS_BETWEEN_CALLS=12.0

# Twelve Data (default: 1 second)
TWELVEDATA_MIN_SECONDS_BETWEEN_CALLS=1.0

# AlphaVantage (default: 20 seconds)
ALPHAVANTAGE_MIN_SECONDS_BETWEEN_CALLS=20.0
```

## TradingView OHLCV

**Note**: TradingView doesn't have an official OHLCV API. Current implementation uses TradingView only for technical analysis summary (buy/sell recommendations). 

For actual candle data, the bot uses the providers above. If you need TradingView candles specifically, consider:
- Using `tradingview-scraper` library (requires web scraping)
- Or stick with Yahoo/Polygon/Twelve Data which provide the same data

## Installation

### 1. Install New Dependencies
```bash
pip install -r requirements.txt
```

New packages added:
- `yfinance>=0.2.28` - Yahoo Finance data
- `oandapyV20>=0.7.2` - OANDA FX data

### 2. Get API Keys (Optional but Recommended)

**Free Options:**
- **Yahoo Finance**: No key needed ✅
- **OANDA Demo**: Sign up at oanda.com for free demo account
- **Polygon Free**: 5 calls/min free tier
- **Twelve Data Free**: 800 calls/day free tier

**Recommended Setup (Free):**
```bash
# Stocks: Yahoo (already included, no key needed)
# FX: AlphaVantage (free, works in Nigeria)
# Crypto: Keep Binance/Bybit (already working)

ALPHAVANTAGE_API_KEY=get_free_from_alphavantage.co
```

### 3. Enable Stock Trading
```bash
# In Railway env vars
STOCK_TRADING_ENABLED=true
STOCK_TRENDING_TOP_N=20
```

### 4. Deploy to Railway
All changes are automatic - just push to Railway and the multi-provider system activates.

## How It Works

### Asset Type Detection
```python
is_crypto("BTCUSDT")  # True
is_fx("EURUSD")       # True
is_stock("AAPL")      # True
```

### Multi-Provider Fetch
```python
# Bot automatically tries providers in order:
candles = get_candles("AAPL", "1h")
# Tries: Yahoo → Polygon → Twelve Data
# Returns first successful result
```

### Fallback Example
```
1. Try Yahoo Finance for AAPL... ✅ Success (200 candles)
   → Use Yahoo data

Or if Yahoo fails:
1. Try Yahoo Finance for AAPL... ❌ Failed
2. Try Polygon.io for AAPL... ✅ Success (200 candles)
   → Use Polygon data
```

## Monitoring

Check Railway logs for provider selection:
```
[data] stock_provider=yahoo symbol=AAPL tf=1h candles=200
[data] fx_provider=oanda symbol=EURUSD tf=1h candles=200
[data] crypto_provider=binance/bybit symbol=BTCUSDT tf=1h candles=200
```

## Benefits

✅ **Redundancy**: If one provider fails, bot automatically tries next
✅ **Free Options**: Yahoo + OANDA demo = unlimited free data
✅ **Quality**: Bank-grade FX (OANDA), institutional stocks (Polygon)
✅ **Coverage**: Crypto + FX + Stocks all supported
✅ **Speed**: Tries fastest/best provider first
✅ **Zero Downtime**: Multiple fallbacks prevent signal gaps

## Testing

```bash
# Test stock data
python -c "from data.fetcher import get_candles; print(len(get_candles('AAPL', '1h')))"

# Test FX data
python -c "from data.fetcher import get_candles; print(len(get_candles('EURUSD', '1h')))"

# Test crypto (should still work)
python -c "from data.fetcher import get_candles; print(len(get_candles('BTCUSDT', '1h')))"
```

Expected output: `200` (or close to it) for each

## Next Steps

1. Deploy to Railway with updated code
2. Optionally add API keys for Polygon/Twelve Data/OANDA
3. Enable stock trading: `STOCK_TRADING_ENABLED=true`
4. Monitor logs to see which providers are being used
5. Enjoy multi-asset trading signals! 🚀
