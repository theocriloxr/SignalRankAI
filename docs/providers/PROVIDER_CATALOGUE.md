# SignalRankAI — Provider Catalogue

Status: **2026-08-05** · Branch `fix/remaining-staging-blockers`

Every provider listed below has a real adapter under `data/connectors/` (or an
explicitly declared dormant adapter), a truthful implementation state, and a
fail-closed activation model. No provider is claimed "production certified"
without credentials and runtime evidence.

Certification states used here:

```text
DECLARED          interface/capability contract only
IMPLEMENTED       adapter code exists
UNIT_VERIFIED     adapter logic covered by tests
DORMANT           requires credentials/flag; inactive without them
STAGING_VERIFIED  exercised against staging resources
PRODUCTION_CERTIFIED  live runtime evidence
BLOCKED_EXTERNAL  needs credentials/licence/legal approval
```

## Public / keyless foundation (active by default where safe)

| Provider | Use | Adapter | State | Notes |
|---|---|---|---|---|
| Coinbase Exchange | Crypto spot candles/quotes | `coinbase_adapter.py` | IMPLEMENTED + UNIT_VERIFIED | Public REST, no auth needed. `COINBASE_MARKET_DATA_ENABLED` (default on via registry presence). |
| OKX | Crypto spot/perp/futures | `okx_adapter.py` | IMPLEMENTED + UNIT_VERIFIED | Public channels; `OKX_MARKET_DATA_ENABLED`. |
| Kraken | Independent crypto confirmation | `kraken_adapter.py` | IMPLEMENTED | Registry-present; `KRAKEN_MARKET_DATA_ENABLED` gate is net-new (see manifest). |
| Hyperliquid | Perpetuals/spot, funding, OI, L2 | `hyperliquid_adapter.py` | **IMPLEMENTED + UNIT_VERIFIED (new)** | `HYPERLIQUID_MARKET_DATA_ENABLED=0` default → zero network calls. Mainnet/testnet separated. Execution NOT wired. |
| Deribit | BTC/ETH options, futures, perps | `deribit_adapter.py` | IMPLEMENTED | Public market data; authenticated execution later. |
| CoinGecko / GeckoTerminal | Token discovery, metadata, DEX pools | `providers.py` (`fetch_coingecko_*`) | IMPLEMENTED | Keyless public path; `COINGECKO_API_KEY` optional. Never the execution quote. |
| Coin Metrics Community | Network/market metrics | `DECLARED` (dormant) | DORMANT | `COIN_METRICS_ENABLED=1` community mode; no key required for community endpoints. |
| FRED | Macro: rates, yields, inflation | `DECLARED` (dormant) | DORMANT | `FRED_API_KEY` optional for community; vintage flags declared. |
| DefiLlama | TVL, stablecoins, protocols | `DECLARED` (dormant) | DORMANT | Free endpoints; Pro behind key. |
| Alpha Vantage | Low-frequency fallback | `alphavantage_adapter.py` | IMPLEMENTED | 25 req/day free cap; never for live delivery. |
| CryptoCompare | Crypto candles fallback | `cryptocompare_adapter.py` | IMPLEMENTED | Registry last-resort. |

## Credential providers (dormant until keys + market-data flag)

| Provider | Use | Adapter | State | Activation rule |
|---|---|---|---|---|
| OANDA | FX + commodity CFDs bid/ask | `oanda_adapter.py` | IMPLEMENTED (dormant) | `OANDA_API_KEY`/`OANDA_ACCOUNT_ID` + `OANDA_MARKET_DATA_ENABLED=1` → `missing_credentials` otherwise, never a failure. |
| Alpaca | US equities/ETFs/options/crypto | `alpaca_adapter.py` | IMPLEMENTED (dormant) | Key+secret pair required; paper-first. |
| Massive (Polygon) | US equities/options/indices confirmation | `polygon_adapter.py` | IMPLEMENTED (dormant) | `POLYGON_API_KEY` canonical; `MASSIVE_API_KEY` alias declared. |
| Twelve Data | Broad multi-asset history | `twelvedata_adapter.py` | IMPLEMENTED (dormant) | `TWELVEDATA_API_KEY` canonical alias; credit budgets declared; never sole live source when rate-limited. |
| Finnhub | Fundamentals, news, WS | `finnhub_adapter.py` | IMPLEMENTED (dormant) | `FINNHUB_API_KEY`. |
| Trading Economics | Calendar/consensus/macro | DECLARED | DORMANT | `TRADING_ECONOMICS_API_KEY`. |
| CoinGlass | Funding/OI/liquidations/LS | DECLARED | DORMANT | `COINGLASS_API_KEY`; capability flags per plan. |
| CryptoQuant | On-chain institutional | DECLARED | DORMANT | `CRYPTOQUANT_API_KEY`. |
| Kaiko | Institutional normalized data | DECLARED | DORMANT | `KAIKO_API_KEY`, region/version flags. |
| Glassnode | Advanced on-chain | DECLARED | DORMANT | `GLASSNODE_API_KEY` (paid add-on). |
| Dune | Custom SQL analytics | DECLARED | DORMANT | `DUNE_API_KEY`; `dune-client` declared. |
| Nasdaq Data Link | Specialist datasets | `nasdaq_data_link_adapter.py` | IMPLEMENTED (dormant) | Key + datasets JSON required. |
| Interactive Brokers | Global execution (later) | DECLARED | DORMANT | Contract interface documented in `data/provider_contracts.py`; never enabled. |
| MT5/MetaApi | FX/CFD execution bridge | `services/` MT5 client | IMPLEMENTED (dormant) | `META_API_TOKEN` guarded; execution fail-closed. |

## Existing exchange adapters (already in registry)

Binance, Bybit, KuCoin, EODHD, MarketStack, Tiingo, FMP, Stooq, Tradier, ECB —
present in `data/connectors/`. Binance is opt-in (`BINANCE_MARKET_DATA_ENABLED=0`
default) because Railway regions are often geo-blocked.

## Execution policy (unchanged, fail-closed)

```text
REAL_EXECUTION_ENABLED=0
AUTO_EXECUTION_ENABLED=0
AUTO_TRADE_ENABLED=0
COPY_TRADE_LIVE_ENABLED=0
REAL_PAYOUTS_ENABLED=0
GLOBAL_EXECUTION_KILL_SWITCH=1
```

Credentials alone never enable execution. Execution requires an explicit
`*_EXECUTION_ENABLED=1` flag AND provider certification AND tier entitlement
AND per-user opt-in AND risk approval — none of which this pass activates.

## Missing / intentionally deferred

- Hyperliquid testnet execution adapter: **declared**, not implemented — needs
  the `hyperliquid-python-sdk` signing boundary and wallet credentials
  (`BLOCKED_EXTERNAL`). Mainnet canary remains disabled.
- Options risk engine / Deribit Greeks: declared interface only.
- WebSockets for all providers: REST-first; WS declared behind
  `*_WEBSOCKET_ENABLED` flags, default 0.
