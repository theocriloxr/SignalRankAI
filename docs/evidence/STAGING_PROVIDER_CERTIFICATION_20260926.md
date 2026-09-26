# Staging Provider Certification — 2026-09-26

## Evidence identity

- Blueprint commit: `12e2427e1faa4a7b72d3484953a7d3736d19eb81`
- Staging provider-cert deployment: `65c8d1a6-0358-49ee-91b2-aa8b60718fda`
- Clean-room deployment for the same commit: `115f4d92-b78f-4063-99e1-3908fdd3137f`
- Alembic head: `0045_mt5_credential_retirement`
- Provider certification exit: `0`
- Live-money posture: disabled/fail-closed

The provider-certification service used `scripts/certify_providers.py --live` in the
staging environment. A successful adapter import or mock result was not accepted
as live certification.

## Enabled providers verified

The exact staging run reported these enabled providers with explicit live/public
endpoint evidence:

| Provider | Certification |
|---|---|
| Coinbase Exchange | IMPLEMENTED_AND_PUBLIC_ENDPOINT_VERIFIED |
| OKX | IMPLEMENTED_AND_PUBLIC_ENDPOINT_VERIFIED |
| Kraken | IMPLEMENTED_AND_PUBLIC_ENDPOINT_VERIFIED |
| KuCoin | IMPLEMENTED_AND_PUBLIC_ENDPOINT_VERIFIED |
| Bybit V5 | IMPLEMENTED_AND_PUBLIC_ENDPOINT_VERIFIED |
| Binance | IMPLEMENTED_AND_PUBLIC_ENDPOINT_VERIFIED |
| CryptoCompare | IMPLEMENTED_AND_LIVE_VERIFIED |
| Yahoo Finance / yfinance | IMPLEMENTED_AND_PUBLIC_ENDPOINT_VERIFIED |
| Twelve Data | IMPLEMENTED_AND_LIVE_VERIFIED |
| Massive (formerly Polygon.io) | IMPLEMENTED_AND_LIVE_VERIFIED |
| Tiingo | IMPLEMENTED_AND_LIVE_VERIFIED |
| European Central Bank | IMPLEMENTED_AND_PUBLIC_ENDPOINT_VERIFIED |
| CoinGecko / GeckoTerminal | IMPLEMENTED_AND_PUBLIC_ENDPOINT_VERIFIED |
| Coin Metrics Community | IMPLEMENTED_AND_PUBLIC_ENDPOINT_VERIFIED |

`DefiLlama` remained `ANALYSIS_ONLY`; it is a context/discovery source and
does not claim a candle/execution-truth capability.

## Optional providers deliberately disabled

The following adapters remain implemented but are not part of the enabled
production-ready provider set:

| Provider | Staging status | Enable gate | Remaining external requirement |
|---|---|---|---|
| Financial Modeling Prep | DISABLED | `FMP_ENABLED` | Suitable plan/endpoint entitlement and recertification |
| Alpha Vantage | DISABLED | `ALPHAVANTAGE_ENABLED` | Suitable plan/endpoint entitlement and recertification |
| OANDA v20 | DISABLED | `OANDA_ENABLED` | Intended practice/live credentials, account mapping and broker certification |
| FRED | DISABLED | `FRED_ENABLED` | Valid credential and macro-provider recertification |

Other dormant adapters remain disabled by catalogue policy until their own
credentials, licences, regional conditions and capability-specific certification
are supplied.

A key by itself no longer activates FMP, Alpha Vantage or OANDA in runtime
fallback selection. FRED also defaults off. This prevents an uncertified or
under-entitled provider from adding latency/noise to the active fallback chain.

## Release verification

For the same commit, the clean-room verifier reported:

- Alembic release-chain PASS at `0045_mt5_credential_retirement`;
- schema audit PASS, including broker credential envelope and immutable
  trading-account ledger contracts;
- release provenance self-check PASS;
- 396 targeted tests PASS;
- `CLEANROOM_PASS`.

Therefore `SR-PROVIDER-007` is integration-verified for the enabled provider
set. Optional disabled providers remain an explicit external boundary under
`SR-PROVIDER-008`; this evidence does not claim those optional providers are
certified.
