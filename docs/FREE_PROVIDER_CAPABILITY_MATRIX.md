# Free / no-key market-data capability matrix

The runtime routes providers by endpoint and asset class. A connector being
healthy for quotes does not imply it is healthy for OHLC.

| Asset class | No-key/public providers in code | Key-based free-tier fallbacks | Intended use |
|---|---|---|---|
| Crypto | Coinbase Exchange, OKX, Bybit, Kraken, KuCoin, CryptoCompare | Optional exchange/API keys | Intraday OHLC and final quotes |
| FX | Yahoo/yfinance (best-effort); ECB reference rates (1d analysis only) | Twelve Data, FMP, Alpha Vantage, Tiingo, Polygon, OANDA practice | Intraday where configured; ECB only for daily context/learning |
| Stocks | Yahoo/yfinance (best-effort) | Twelve Data, FMP, Alpha Vantage, Tiingo, Polygon | Session-aware OHLC; configured official/free-tier APIs are prioritised |
| Indices | Yahoo/yfinance (best-effort) | FMP, Twelve Data, Alpha Vantage, Polygon | Cash/index proxy data with canonical symbol mapping |
| Commodities | Yahoo/yfinance (best-effort) | FMP, Twelve Data, Alpha Vantage, OANDA | Futures/spot proxy OHLC with provenance |
| Macro | ECB daily FX; existing public context | FRED, Finnhub, Polygon | Analysis-only unless a tradeable proxy exists |

Safety rules:
- ECB observations never satisfy 5m/15m/1h actionable requirements.
- Key-based providers are skipped or degrade when their key is absent.
- At most `OHLC_MAX_PROVIDER_ATTEMPTS_PER_TIMEFRAME` providers are attempted.
- Final delivery quotes use the canonical typed quote path and fail closed.

Configured key-based connectors are ordered before Yahoo for non-crypto assets. Missing keys are skipped before the provider-attempt budget is consumed.
