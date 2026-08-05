# SignalRankAI — Provider Activation Guide

Adding credentials **activates market data after restart/config reload**.
Adding credentials **never activates execution** (see the execution rule below).

## Keyless public providers (no keys required)

1. Ensure the provider's `*_ENABLED` flag is `1` (defaults: CoinGecko, Coin
   Metrics, DefiLlama, FRED(flag), Coinbase, OKX, Kraken).
2. Restart the engine (or trigger config reload).
3. Verify with the provider `health()` probe — state should be `public_ready`.

## Credential providers (dormant until keys added)

| Provider | Variables to add | Resulting state |
|---|---|---|
| Massive (Polygon.io) | `MASSIVE_API_KEY` (or legacy `POLYGON_API_KEY`) | `healthy` |
| OANDA | `OANDA_API_KEY`/`OANDA_TOKEN` + `OANDA_ACCOUNT_ID`, env `practice` or `live` | `healthy` |
| Alpaca | `ALPACA_API_KEY` + `ALPACA_API_SECRET` (or `APCA_*` aliases) | `healthy` |
| Twelve Data | `TWELVEDATA_API_KEY` (or `TWELVE_DATA_API_KEY`) | `healthy` |
| Finnhub | `FINNHUB_API_KEY` | `healthy` |
| FRED | `FRED_API_KEY` | `healthy` |
| Trading Economics | `TRADING_ECONOMICS_API_KEY` | `healthy` |
| CoinGlass | `COINGLASS_API_KEY` | `healthy` (capabilities per plan) |
| Dune | `DUNE_API_KEY` | `healthy` |
| Kaiko | `KAIKO_API_KEY` (+ `KAIKO_REGION`) | `healthy` |
| Glassnode | `GLASSNODE_API_KEY` | `healthy` |
| CryptoQuant | `CRYPTOQUANT_API_KEY` | `healthy` |
| Nasdaq Data Link | `NASDAQ_DATA_LINK_API_KEY` + `NASDAQ_DATA_LINK_DATASETS_JSON` | `healthy` |

## Execution rule (never automatic)

```
execution_ready == False
unless explicit execution flag (live/live_guarded/1)
   AND certification evidence env var set
   AND instrument allowlist configured when one exists
   AND per-user opt-in / tier entitlement / environment safety / venue certification
```

An execution flag without certification resolves to `plan_insufficient` —
never to live trading.

## Staging parity

Staging runs the same adapters against safe endpoints:

- `HYPERLIQUID_TESTNET=1` → testnet API
- `OKX_DEMO_TRADING_ENABLED=1` → demo env (when execution ever enabled)
- `OANDA_ENVIRONMENT=practice` → practice account
- `ALPACA_PAPER_TRADING_ENABLED=1`, `ALPACA_LIVE_TRADING_ENABLED=0`
- `DERIBIT_ENVIRONMENT=test` → test.deribit.com

## Verification

```bash
python -m pytest -q tests/test_v22_provider_expansion.py
```

Every adapter exposes a zero-network `health()` probe returning
`provider_id`, `enabled`, `state`, and required env vars.
