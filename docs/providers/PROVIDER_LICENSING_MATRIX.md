# SignalRankAI — Provider Licensing Matrix

SignalRankAI must not give a tier data that a provider licence prohibits it
from redistributing. This matrix records known licensing posture; the
implementation carries capability flags rather than hardcoded redistribution
rights.

| Provider | Redistribution posture | Gate variables | Signals | Notes |
|---|---|---|---|---|
| Coinbase / OKX / Kraken / KuCoin / Bybit / Hyperliquid / Deribit | Public market data OK for display/analysis; check each venue's ToS before automated redistribution | `*_MARKET_DATA_ENABLED` | yes | execution requires separate auth + flags |
| CoinGecko / GeckoTerminal | Public API for apps; Pro terms for heavy/paid use | `COINGECKO_ACCESS_MODE`, monthly credit budget | yes (context) | `COINGECKO_USE_FOR_EXECUTION_QUOTE=0` |
| Coin Metrics Community | Community terms; Pro licence for redistribution | `COIN_METRICS_ACCESS_MODE` | yes (analysis) | |
| DefiLlama | Open data, attribution appreciated | `DEFILLAMA_ENABLED` | context only | |
| FRED | Free public use, requires attribution | `FRED_ENABLED` | macro context | point-in-time for backtests |
| Yahoo (yfinance) | Unauthorized scraping is against ToS — fallback only | — | best-effort | never sole execution truth |
| Twelve Data | External display requires the appropriate licence | `TWELVE_DATA_COMMERCIAL_DISPLAY_LICENSED=0` | yes | do not activate external display when licence does not permit |
| Alpaca | Market-data licences vary by feed (IEX vs broader) | `ALPACA_DATA_FEED`, `ALPACA_OPTIONS_DATA_FEED` | yes | upgrade feeds via config only |
| OANDA | Account-authenticated pricing; check redistribution terms | `OANDA_MARKET_DATA_ENABLED` | yes | practice vs live env |
| Massive (Polygon.io) | Paid licence required for production redistribution; bulk flat files separate | `MASSIVE_MARKET_DATA_ENABLED`, `MASSIVE_FLAT_FILES_ENABLED` | yes | API key required |
| Trading Economics | Paid subscription; redistribution restricted | `TRADING_ECONOMICS_ENABLED` | calendar context | |
| CoinGlass | Plan-dependent capabilities; some endpoints restricted | `COINGLASS_*_ENABLED` | derivatives intel | heatmaps/options gated off by default |
| Finnhub | Free tier limited; paid packages for broader redistribution | `FINNHUB_MARKET_DATA_ENABLED` | yes | |
| Alpha Vantage | Free tier limited to 25 req/day; key required | `ALPHA_VANTAGE_DAILY_REQUEST_BUDGET`, `ALPHA_VANTAGE_USE_FOR_LIVE_DELIVERY=0` | fallback | never high-frequency scans |
| Kaiko / Coin Metrics Pro / Glassnode / Dune / Nasdaq Data Link / CryptoQuant | Institutional subscription terms govern all redistribution | `*_ENABLED`, `*_API_KEY` | analysis/intel | dormant until subscribed |

## Rules of thumb

1. Public-endpoint data may be displayed with attribution where required.
2. Credential-provider data may be used for the subscriber's internal analysis.
3. Redistribution to third parties requires the matching commercial licence.
4. When licence state is unknown, keep the provider in `analysis_only` role and
   never use it as the sole live delivery source.
