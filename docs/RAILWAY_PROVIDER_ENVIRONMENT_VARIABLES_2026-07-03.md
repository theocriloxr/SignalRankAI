# Railway Provider Environment Variables - 2026-07-03

This checklist is based on the exact environment variable names currently read by the codebase.

## Minimum Production Set

These should be present before treating the bot as production-ready.

```text
DATABASE_URL=<Railway Postgres private URL>
REDIS_URL=<Railway Redis private URL>
TELEGRAM_BOT_TOKEN=<Telegram bot token>
OWNER_IDS=<comma-separated owner Telegram IDs>
ADMIN_IDS=<comma-separated admin Telegram IDs>
ENCRYPTION_KEY=<strong stable secret for stored broker credentials>
GEMINI_API_KEY=<Google Gemini API key>
META_API_TOKEN=<MetaApi token for MT5 linking/trading>
TWELVEDATA_API_KEY=<TwelveData key>
POLYGON_API_KEY=<Polygon key>
ALPHAVANTAGE_API_KEY=<Alpha Vantage key>
CRYPTOCOMPARE_API_KEY=<CryptoCompare key>
COINGECKO_API_KEY=<CoinGecko key>
FINNHUB_API_KEY=<Finnhub key for economic calendar/news risk>
```

## Recommended Market Data Coverage

### Crypto

```text
BINANCE_API_KEY=<optional for private/exchange execution; public market data can work without it>
BINANCE_API_SECRET=<optional>
BYBIT_API_KEY=<optional for private/exchange execution>
BYBIT_API_SECRET=<optional>
CRYPTOCOMPARE_API_KEY=<recommended crypto fallback and live price source>
COINGECKO_API_KEY=<recommended CoinGecko Pro/Demo coverage>
CRYPTOPANIC_API_KEY=<optional crypto news>
CRYPTO_DATA_PROVIDER=auto
CRYPTO_PREFERRED_PROVIDER=
CRYPTO_WS_PROVIDER=binance
CRYPTO_WS_ENABLED=1
AUTO_DISCOVERY_ALL_PROVIDERS=1
CRYPTO_MICROSTRUCTURE_PROVIDERS=bybit,okx,binance
CRYPTO_DERIVATIVES_PROVIDERS=bybit,okx,binance
ORDER_BOOK_IMBALANCE_THRESHOLD=1.5
SQUEEZE_FUNDING_THRESHOLD=0.0005
```

If Binance is blocked from Railway, prefer:

```text
CRYPTO_DATA_PROVIDER=cryptocompare
CRYPTO_WS_PROVIDER=cryptocompare
```

### Forex, Metals, Commodities, Indices, Stocks

```text
TWELVEDATA_API_KEY=<required for broad OHLC fallback>
POLYGON_API_KEY=<recommended stocks/indices/forex fallback>
ALPHAVANTAGE_API_KEY=<recommended FX fallback>
FMP_API_KEY=<optional stocks/fundamentals fallback>
FCS_API_KEY=<optional forex/commodities connector>
TIINGO_API_KEY=<optional equities/news connector>
OANDA_API_KEY=<optional broker/data connector>
OANDA_ACCOUNT_ID=<required if using OANDA>
OANDA_PRACTICE=true
FX_PREFERRED_PROVIDER=
ALPHAVANTAGE_ENABLED=1
YFINANCE_ENABLED=1
TRADINGVIEW_ENABLED=1
TRADINGVIEW_OHLCV_ENABLED=0
```

### News and Macro Risk

```text
NEWSAPI_KEY=<recommended general headlines and sentiment; NEWS_API_KEY is accepted as an alias>
FOREX_FACTORY_CALENDAR_URL=https://nfs.faireconomy.media/ff_calendar_thisweek.json
FINNHUB_API_KEY=<optional economic-calendar fallback>
X_BEARER_TOKEN=<optional X/Twitter news source>
TWITTER_BEARER_TOKEN=<optional alias fallback for X_BEARER_TOKEN>
ECONOMIC_CALENDAR_CACHE_TTL_SECONDS=3600
ECONOMIC_CALENDAR_TIMEOUT_SECONDS=8
NO_TRADE_BUFFER_MINUTES=30
NEWS_VOLATILITY_BUFFER_MULTIPLIER=1.0
```

`NewsAPI` supplies headlines after publication; it does not supply a scheduled
economic calendar. The default Fair Economy/Forex Factory JSON feed supplies
event time, currency, impact, forecast, previous, and actual values without a
TradingEconomics subscription. Keep both sources enabled. Official government
releases can be added as authoritative fallbacks, but TradingEconomics is not a
required environment variable in this codebase.

## AI and Governance

```text
GEMINI_API_KEY=<required for Gemini analysis>
GEMINI_MODEL=gemini-2.0-flash
GEMINI_SIGNAL_REVIEW_MODEL=gemini-2.0-flash
GEMINI_API_TIMEOUT_SECONDS=8
GEMINI_SIGNAL_REVIEW_TIMEOUT_SEC=8
GEMINI_SIGNAL_REVIEW_ENABLED=1
GEMINI_REVIEW_ENABLED=1
GEMINI_DAILY_REVIEW_ENABLED=1
GEMINI_INLINE_TOP_N=3
GEMINI_DAILY_LIMIT=10
```

Optional Codex/OpenAI governance review:

```text
OPENAI_API_KEY=<OpenAI API key>
CODEX_OPENAI_API_KEY=<optional fallback if OPENAI_API_KEY is not used>
OPENAI_CODEX_REVIEW_ENABLED=0
OPENAI_CODEX_REVIEW_MODEL=gpt-4.1-mini
OPENAI_CODEX_REVIEW_TIMEOUT_SECONDS=25
OPENAI_CODEX_REVIEW_MAX_TOKENS=1200
```

## Broker and Execution

```text
META_API_TOKEN=<MetaApi token>
META_API_REGION=new-york
META_API_DOMAIN=agiliumtrade.agiliumtrade.ai
EXECUTION_ROUTER_ENABLED=1
BROKER_EXEC_IDEMPOTENCY_SECONDS=86400
MT5_EXECUTION_RETENTION_DAYS=45
```

## TradingView/Webhooks

```text
TV_WEBHOOK_SECRET=<shared secret for TradingView webhook route>
TRADINGVIEW_BROKER=BINANCE
TRADINGVIEW_FX_PREFIX=OANDA
TRADINGVIEW_INDEX_PREFIX=TVC
TRADINGVIEW_STOCK_PREFIX=NASDAQ
WEBHOOK_SECRET=<optional generic webhook signing secret>
WEBHOOK_URL=<optional external webhook URL>
WEBHOOK_TIMEOUT_SECONDS=10
WEBHOOK_MAX_RETRY=3
```

## Railway Stability Settings

```text
DB_POOL_SIZE=20
DB_MAX_OVERFLOW=20
DB_MAX_CONCURRENT_SESSIONS=40
DB_POOL_TIMEOUT_SECONDS=30
DB_POOL_RECYCLE_SECONDS=1800
DB_POOL_PRE_PING=1
DB_CONNECT_TIMEOUT=15
DB_COMMAND_TIMEOUT=45
MARKET_CACHE_FETCH_CONCURRENCY=8
MARKET_FETCH_TIMEOUT_SECONDS=20
ENGINE_MARKET_FETCH_TIMEOUT_SECONDS=180
USE_MULTI_PROVIDER_DATA=true
PROVIDER_COOLDOWN_SECONDS=600
PROVIDER_OUTAGE_MINUTES=10
PROVIDER_OUTAGE_ALERT_SCHEDULE_MINUTES=10,30,60
PROVIDER_OUTAGE_ALERT_INTERVAL_MINUTES=60
PROVIDER_OUTAGE_ALERT_OPTIONAL=0
TELEGRAM_GLOBAL_SEND_DELAY_SECONDS=0.08
TELEGRAM_RETRY_AFTER_MAX_SECONDS=180
TELEGRAM_SEND_MAX_ATTEMPTS=2
OUTCOME_NOTIFICATION_CLAIM_STALE_SECONDS=300
```

## Asset-Class Toggles

```text
FX_ENABLED=1
STOCKS_ENABLED=1
INDICES_ENABLED=1
INDEX_ENABLED=1
FX_DEFAULT_ENABLED=1
TRADABLE_ASSETS=BTCUSDT,ETHUSDT,EURUSD,GBPUSD,USDJPY,XAUUSD,XAGUSD,WTI,BRENT
FX_PAIRS=EURUSD,GBPUSD,USDJPY,USDCHF,USDCAD,AUDUSD,NZDUSD,EURJPY
CRYPTO_TIMEFRAMES=1m,5m,15m,1h,4h,1d
FX_TIMEFRAMES=1m,5m,15m,1h,4h,1d
COMMODITY_TIMEFRAMES=1m,5m,15m,1h,4h,1d
INDEX_TIMEFRAMES=5m,15m,1h,4h,1d
STOCK_TIMEFRAMES=5m,15m,1h,4h,1d
```

## Notes

- Use the exact names above. For example, the code reads `TWELVEDATA_API_KEY`, not `TWELVE_DATA_API_KEY`.
- `FINNHUB_API_KEY` is currently used by the economic calendar service, not the OHLC provider waterfall.
- Bybit, OKX, Coinbase Exchange, Kraken, Yahoo Finance, and the default Fair Economy calendar feed use public endpoints and need no Railway secret.
- Do not add `TRADINGECONOMICS_API_KEY`; the active calendar waterfall does not require it.
- `FMP_API_KEY`, `FCS_API_KEY`, and `TIINGO_API_KEY` are connector keys and are optional but useful for resilience.
- `TRADINGVIEW_OHLCV_ENABLED` defaults to off because TradingView TA is useful for validation but should not emit synthetic OHLC candles.
- If Railway logs still show `effective_pool=2 effective_overflow=0`, Railway is running old code or explicit env vars are overriding the new defaults.
