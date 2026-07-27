# Provider Environment Contract

All provider credentials are optional unless the selected deployment profile explicitly marks the provider required. Missing optional credentials must not prevent application startup. Enabled providers must be certified through `scripts/certify_providers.py`; fixture-only tests do not count as live certification.

| Provider | Variables | Intended role | Default production status |
|---|---|---|---|
| Coinbase / OKX / Kraken / Bybit / Deribit | public endpoints; provider-specific flags | Crypto spot/derivatives | Public providers enabled only after regional smoke |
| Twelve Data | `TWELVEDATA_API_KEY` | Multi-asset keyed provider | Optional |
| Polygon | `POLYGON_API_KEY` | Equities/index/FX/options | Optional |
| Alpha Vantage | `ALPHAVANTAGE_API_KEY` | Equities/FX/macro fallback | Optional |
| FMP | `FMP_API_KEY` | Equities/index/FX/fundamentals | Optional |
| Tiingo | `TIINGO_API_KEY` | Equity/FX/crypto fallback | Optional |
| OANDA practice | `OANDA_API_KEY`, `OANDA_ACCOUNT_ID`, `OANDA_PRACTICE=1` | FX/broker validation | Sandbox only |
| EODHD | `EODHD_API_KEY` or `EODHD_API_TOKEN` | EOD and delayed intraday/historical | Disabled until keyed certification |
| Marketstack | `MARKETSTACK_API_KEY` | EOD/delayed equity history | Disabled until keyed certification |
| Finnhub | `FINNHUB_API_KEY` | Calendar/news and keyed market fallback | Optional |
| Alpaca | `ALPACA_API_KEY` + `ALPACA_API_SECRET`, or APCA aliases | Equity/crypto/options sandbox | Disabled until sandbox certification |
| Tradier | `TRADIER_TOKEN`, optional `TRADIER_BASE_URL` | Equity/options sandbox | Disabled until sandbox certification |
| Nasdaq Data Link | `NASDAQ_DATA_LINK_API_KEY`, `NASDAQ_DATA_LINK_DATASETS_JSON` | Configured daily historical datasets | Disabled until mapping/certification |
| Stooq | public endpoint | Daily historical fallback | Analysis/historical only |

No provider may be described as real-time if the active account/plan returns delayed data. Every quote and candle must retain provider, endpoint class, fetch time and delayed/realtime provenance.
