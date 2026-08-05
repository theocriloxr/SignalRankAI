# PROVIDER_CAPABILITY_MATRIX — SignalRankAI

Certification vocabulary: DECLARED / IMPLEMENTED / UNIT_VERIFIED /
SANDBOX_VERIFIED / STAGING_VERIFIED / PRODUCTION_CERTIFIED / QUARANTINED /
DISABLED. **No provider below is PRODUCTION_CERTIFIED.** The matrix records
intended capability and current status; anything not listed is not advertised.

## Market data / live quotes (existing production adapters)

| Provider | Asset classes | Capabilities | Status |
|---|---|---|---|
| MetaAPI (MT5 bridge) | FX, commodity, index, stock | live quotes, OHLC | STAGING_VERIFIED (prior cert work); runtime evidence per account |
| Twelve Data | crypto, FX, stocks, indices | OHLC, quotes | STAGING_VERIFIED; quota-dependent |
| FCS (FX/commodity) | FX, commodity | quotes, OHLC | STAGING_VERIFIED; live-quote reliability varies |
| Yahoo | multi | quotes (analysis only) | DECLARED — never authoritative production feed |
| Polygon | equities, crypto | OHLC, reference | DECLARED (credential gated) |
| TradingView | multi | OHLCV | UNIT_VERIFIED; flag-enforced `TRADINGVIEW_ENABLED` |
| Binance / Bybit / OKX / Coinbase / Kraken (public market data) | crypto | OHLC, quotes, funding/OI where available | DECLARED / sandbox harness pending |

## Execution venues (all DISABLED — fail closed)

| Venue | Intended capabilities | Status | Blocking dependency |
|---|---|---|---|
| Bybit | spot/perp orders, stop/trigger, reduce-only, position modes | DECLARED | credentials + testnet certification (`BYBIT_EXECUTION_ENABLED=0`) |
| MT5/MetaApi | broker execution | DECLARED | paid account + guarded activation |
| OANDA | FX/CFD execution, practice account | DECLARED | credentials + jurisdiction |
| Interactive Brokers | stocks/options/futures | DECLARED | subscription/permissions |
| Alpaca | equities/options/crypto | DECLARED | credentials; live behind gates |
| Tradier | equities/options | DECLARED | sandbox certification |
| Hyperliquid | spot/perp, DEX | DECLARED | wallet/key isolation + testnet certification |
| dYdX / GMX / Jupiter / Aevo / Paradex | DEX derivatives | DECLARED | review + credentials |

## Independent data & intelligence (DECLARED)

Finnhub, Tiingo, Alpha Vantage, Nasdaq Data Link, on-chain providers, economic
calendar/news feeds, options feeds. Each must pass licensing review before
advertisement (SR-PROVIDER-007, blocked external).

## Routing policy

Typed failures (`data/provider_failures.py`), circuit breakers
(`core/circuit_breaker.py`), quote trust policy
(`data/provider_types.py`). No silent static fallback: a missing capability is
a typed `UnsupportedCapability`, never an implicit substitute.
