# SignalRankAI — Provider Activation Matrix

Resolved by `data/provider_activation.py::resolve_activation()`. One state per
provider per environment. **Credentials alone never activate execution** — an
explicit execution flag *and* certification evidence are required.

## States

| State | Meaning | Market data | Execution |
|---|---|---|---|
| `disabled` | Feature flag off (`*_ENABLED=0`) | no | no |
| `public_ready` | Public endpoint + enabled, no key needed | yes | no |
| `missing_credentials` | Credential provider without keys — normal, not an error | no | no |
| `invalid_credentials` | Keys present but health check failed | no | no |
| `plan_insufficient` | Subscribed plan lacks capability (or execution flag set without certification) | no | no |
| `rate_limited` | Quota exhausted / explicit `*_RATE_LIMITED` | no | no |
| `healthy` | Credentials present + (after restart/config reload) health pass | yes | only with explicit execution flag + certification |
| `degraded` | Partial capability loss | limited | only guarded |
| `circuit_open` | Circuit breaker open / `*_CIRCUIT_OPEN` | no | no |
| `suspended` | Admin suspension `*_SUSPENDED` | no | no |

## Current defaults (v2.2)

| Provider | Key needed | Default state | Notes |
|---|---|---|---|
| Coinbase, OKX, Kraken, KuCoin, Bybit | no | `public_ready` | public REST market data |
| Hyperliquid | no | `public_ready` (opt-in gate) | `HYPERLIQUID_MARKET_DATA_ENABLED=1` |
| Deribit | no | `public_ready` (opt-in gate) | derivatives public data |
| CoinGecko / GeckoTerminal | no | `public_ready` | discovery/context; never execution quote |
| Coin Metrics Community | no | `public_ready` | keyless; Pro via `COIN_METRICS_API_KEY` |
| DefiLlama | no | `public_ready` | context/discovery |
| FRED | `FRED_API_KEY` | `missing_credentials` | dormant without key |
| Trading Economics | `TRADING_ECONOMICS_API_KEY` | `missing_credentials` | dormant |
| CoinGlass | `COINGLASS_API_KEY` | `missing_credentials` | dormant; capabilities per plan |
| Dune | `DUNE_API_KEY` | `missing_credentials` | dormant |
| Kaiko | `KAIKO_API_KEY` | `missing_credentials` | dormant |
| Glassnode | `GLASSNODE_API_KEY` | `missing_credentials` | dormant |
| CryptoQuant | `CRYPTOQUANT_API_KEY` | `missing_credentials` | dormant |
| Massive (Polygon.io) | `MASSIVE_API_KEY` or `POLYGON_API_KEY` | `missing_credentials` | one consolidated secret |
| Alpaca / OANDA / Tradier | key pairs | `missing_credentials` | dormant |
| Twelve Data / Finnhub / Tiingo / FMP / EODHD / Marketstack / Nasdaq Data Link | key | `missing_credentials` | dormant |

## Execution rule

```
execution_ready == False
unless  (execution flag == live/live_guarded/1)
   AND  (execution certification id configured)
   AND  (instrument allowlist configured when one exists)
```

An execution flag set **without** certification resolves to
`plan_insufficient` — it never silently enables trading.
