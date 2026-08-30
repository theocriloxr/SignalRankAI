# Provider Activation and Cost Ladder

Provider adapters are configuration-driven. Public endpoints may initialize
without credentials; keyed providers remain dormant until valid credentials and
plan capabilities are present. Credentials alone never enable execution.

## Start with public/freemium data

Coinbase, OKX, Kraken, Hyperliquid public data, Deribit public data, CoinGecko,
Coin Metrics Community, DefiLlama and available public macro/reference sources.

## First commercial upgrades

1. OANDA for authoritative FX and metals bid/ask data.
2. Alpaca for U.S. equities/options and paper execution.
3. Massive for independent equities/options/index data.
4. Twelve Data at a commercial redistribution tier.
5. Trading Economics for point-in-time calendar/macro evidence.
6. CoinGlass for derivatives intelligence.
7. Finnhub for fundamentals/news/international coverage.

## Institutional phase

Kaiko, Coin Metrics Pro, Glassnode API, CryptoQuant, Dune, Nasdaq Data Link and
Interactive Brokers should be enabled only after contracts, redistribution
rights and operational budgets are confirmed.

Use `scripts/certify_providers.py` to distinguish import/mock verification from
public, sandbox or live verification. Context-only providers are never treated
as execution quote sources.
