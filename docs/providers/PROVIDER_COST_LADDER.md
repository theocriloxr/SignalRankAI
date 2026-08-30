# SignalRankAI — Provider Cost Ladder

Tier-aware budgeting: **Free** users get public/low-cost cached sources;
**Premium** broader licensed data; **VIP** priority live feeds + derivatives
intelligence; **Professional/Institutional** licensed WebSockets, APIs, exports
and dedicated quotas. Never redistribute data a provider licence prohibits.

## Rung 0 — Free / public / keyless (use now)

| Provider | Primary use | Cost | Notes |
|---|---|---|---|
| Coinbase / OKX / Kraken / KuCoin / Bybit | crypto spot/perps candles | free public REST | keep as primary crypto sources |
| Hyperliquid | perps/spot candles, funding, OI, mark/oracle | free public | mainnet + testnet separation |
| Deribit | BTC/ETH options, futures, perps, IV | free public | public market data |
| CoinGecko / GeckoTerminal | token discovery, metadata, DEX pools | keyless (rate-limited) | never final execution quote |
| Coin Metrics Community | historical market + network metrics | keyless | Pro upgrade later |
| DefiLlama | TVL, stablecoins, yields, unlocks | free | context only |
| FRED | rates, yields, inflation, macro | free | vintages; dormant without key |
| Yahoo (yfinance) | best-effort fallback | free | never sole execution truth |

## Rung 1 — First revenue-funded upgrades

| Provider | Primary use | Typical cost model |
|---|---|---|
| OANDA | authoritative FX + commodity bid/ask, candles, practice mode | account-backed |
| Alpaca (Basic / Algo Trader Plus) | U.S. equities, ETFs, equity options | free Basic (IEX) / paid broader feeds |
| Massive (Polygon.io successor) | independent U.S. equities/options/indices/futures/forex/crypto confirmation | paid tiers, flat files |
| Twelve Data Business/Venture/Pro | broad multi-asset historical + streaming | credit-based; free tier unsuitable for production scan volume |
| Trading Economics | economic calendar, consensus vs actual, point-in-time macro | paid |
| CoinGlass | funding, OI, liquidations, long/short, order-book analytics | per plan; heatmaps cost more |
| Finnhub | fundamentals, news, sentiment, WebSockets, international | free start + paid packages |
| Alpha Vantage | low-frequency stock/FX/indicator fallback | free tier = 25 req/day; never for high-frequency scans |

## Rung 2 — Institutional

| Provider | Primary use | Notes |
|---|---|---|
| Kaiko | normalized institutional trades/order books/derivatives reference data | dormant adapter in repo |
| Coin Metrics Pro | institutional market/network/WebSocket feeds | upgrade via `COIN_METRICS_API_KEY` |
| Glassnode | advanced on-chain metrics | API is a paid add-on |
| Dune | custom blockchain SQL analytics | `dune-client` |
| Nasdaq Data Link | specialist financial/economic datasets | configured datasets only |
| Interactive Brokers | global execution (equities/options/futures/bonds/FX) | **later-stage**; not first integration |

## Budget guards

- `PROVIDER_COST_BUDGET_ENABLED=1`, `PROVIDER_CREDIT_TRACKING_ENABLED=1`
- `COINGECKO_MONTHLY_CREDIT_BUDGET`, `TWELVE_DATA_CREDIT_BUDGET_PER_MINUTE`, `TWELVE_DATA_DAILY_CREDIT_BUDGET`
- Circuit breakers + permanent unsupported-symbol caches prevent retry storms.
