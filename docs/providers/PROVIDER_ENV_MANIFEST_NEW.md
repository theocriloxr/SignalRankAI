# SignalRankAI — Net-New Provider Environment Manifest

Produced from a real repository audit (2026-08-05). This table contains **only**
variables that are not already represented by a canonical variable in code.
Where an equivalent exists, the canonical name is listed and no new variable is
introduced.

Legend:
- **Service**: `front` = front door, `engine` = signal engine, `worker` = worker/payments, `all`.
- **Secret**: whether the value must be treated as a secret.
- **Already existed?**: `yes` / `alias` (compatible alias in code) / `no`.
- **Activation effect**: what happens when set (credentials alone never activate execution).

## Market-data enablement (gates)

| Variable | Provider | Service | Secret | Req/Opt | Default | Already existed? | Canonical replacement | Activation effect | Railway env |
|---|---|---|---|---|---|---|---|---|---|
| `COINBASE_MARKET_DATA_ENABLED` | Coinbase | all | no | opt | 1 | no | — | Enables public REST candle path | all |
| `OKX_MARKET_DATA_ENABLED` | OKX | all | no | opt | 1 | no | — | Enables public REST candle path | all |
| `KRAKEN_MARKET_DATA_ENABLED` | Kraken | all | no | opt | 1 | no | — | Enables Kraken candle path | all |
| `HYPERLIQUID_MARKET_DATA_ENABLED` | Hyperliquid | all | no | opt | 0 | yes (new gate) | — | Zero network calls until 1; then public `/info` REST | all |
| `HYPERLIQUID_TESTNET` | Hyperliquid | all | no | opt | 0 | no | — | Routes `/info` to testnet API | staging/test |
| `OANDA_MARKET_DATA_ENABLED` | OANDA | all | no | opt | 0 | no | — | Enables FX/commodity candles + live pricing when key present | all |
| `ALPACA_MARKET_DATA_ENABLED` | Alpaca | all | no | opt | 0 | no | — | Enables equities/ETF data when key pair present | all |
| `DERIBIT_MARKET_DATA_ENABLED` | Deribit | all | no | opt | 0 | no | — | Enables options/futures public data | all |
| `MASSIVE_MARKET_DATA_ENABLED` | Massive | all | no | opt | 0 | no | `POLYGON_API_KEY` (alias) | Enables US equities/options confirmation | all |
| `TWELVE_DATA_MARKET_DATA_ENABLED` | Twelve Data | all | no | opt | 0 | no | `TWELVEDATA_API_KEY` | Enables secondary history when key present | all |
| `FINNHUB_MARKET_DATA_ENABLED` | Finnhub | all | no | opt | 0 | no | — | Enables fundamentals/news/WS | all |
| `COINGECKO_ENABLED` | CoinGecko | all | no | opt | 1 | no | `COINGECKO_API_KEY` | Keyless public discovery path | all |
| `COIN_METRICS_ENABLED` | Coin Metrics | all | no | opt | 1 | no | — | Community endpoints (keyless) | all |
| `FRED_ENABLED` | FRED | engine/worker | no | opt | 1 | no | — | Macro series (vintage-aware) | all |
| `DEFILLAMA_ENABLED` | DefiLlama | engine | no | opt | 1 | no | — | TVL/on-chain context | all |
| `ALPHA_VANTAGE_ENABLED` | Alpha Vantage | all | no | opt | 0 | yes | `ALPHAVANTAGE_ENABLED` | Reuse existing gate; keep off for live delivery | all |
| `TRADING_ECONOMICS_ENABLED` | Trading Economics | engine | no | opt | 0 | no | — | Calendar/consensus data | all |
| `COINGLASS_ENABLED` | CoinGlass | engine | no | opt | 0 | no | — | Funding/OI/liquidations | all |
| `DUNE_ENABLED` / `GLASSNODE_ENABLED` / `CRYPTOQUANT_ENABLED` / `KAIKO_ENABLED` | on-chain | engine | no | opt | 0 | no | — | Declared dormant adapters | all |
| `NASDAQ_DATA_LINK_ENABLED` | Nasdaq Data Link | all | no | opt | 0 | no | `NASDAQ_DATA_LINK_API_KEY` | Reuse existing key; gate only | all |

## Credentials (secrets)

| Variable | Provider | Service | Secret | Req/Opt | Default | Already existed? | Canonical replacement | Activation effect | Railway env |
|---|---|---|---|---|---|---|---|---|---|
| `COINBASE_ADVANCED_API_KEY` / `..._SECRET` | Coinbase | worker | **yes** | opt | — | no | — | Authenticated SDK; execution still gated | worker |
| `OKX_API_KEY` / `OKX_API_SECRET` / `OKX_API_PASSPHRASE` | OKX | worker | **yes** | opt | — | no | — | Auth; execution gated | worker |
| `KRAKEN_API_KEY` / `KRAKEN_API_SECRET` | Kraken | worker | **yes** | opt | — | no | — | Auth; execution gated | worker |
| `HYPERLIQUID_API_WALLET_ADDRESS` / `HYPERLIQUID_API_WALLET_PRIVATE_KEY` | Hyperliquid | worker | **yes** | opt | — | no | — | Signing boundary only; **never logged**; execution gated | worker |
| `DERIBIT_CLIENT_ID` / `DERIBIT_CLIENT_SECRET` | Deribit | worker | **yes** | opt | — | no | — | Auth; execution gated | worker |
| `OANDA_ACCESS_TOKEN` / `OANDA_ACCOUNT_ID` | OANDA | all | **yes** | opt | — | alias | `OANDA_API_KEY` + `OANDA_ACCOUNT_ID` | Reuse existing key; pricing requires account | all |
| `MASSIVE_API_KEY` | Massive | all | **yes** | opt | — | alias | `POLYGON_API_KEY` | Alias only; one resolved secret internally | all |
| `TWELVE_DATA_API_KEY` | Twelve Data | all | **yes** | opt | — | alias | `TWELVEDATA_API_KEY` | **Consolidate: keep one key, deprecate alias** | all |
| `TRADING_ECONOMICS_API_KEY` | Trading Economics | engine | **yes** | opt | — | no | — | Enables calendar data | engine |
| `COINGLASS_API_KEY` | CoinGlass | engine | **yes** | opt | — | no | — | Enables funded endpoints per plan | engine |
| `COIN_METRICS_API_KEY` | Coin Metrics | engine | **yes** | opt | — | no | — | Pro endpoints | engine |
| `FRED_API_KEY` | FRED | engine | **yes** | opt | — | no | — | Higher-rate macro series | engine |
| `CRYPTOQUANT_API_KEY` / `GLASSNODE_API_KEY` / `DUNE_API_KEY` / `KAIKO_API_KEY` | on-chain | engine | **yes** | opt | — | no | — | Dormant until set | engine |

## Behavioural / budget flags (all optional, non-secret)

| Variable | Provider | Default | Activation effect |
|---|---|---|---|
| `HYPERLIQUID_WEBSOCKET_ENABLED` / `..._PAPER_ENABLED` / `..._TESTNET_EXECUTION_ENABLED` / `..._MAINNET_EXECUTION_ENABLED` / `..._OWNER_CANARY_ENABLED` / `..._MAX_LEVERAGE` / `..._MAX_NOTIONAL_USD` / `..._INSTRUMENT_ALLOWLIST` | Hyperliquid | 0 / — | Execution/canary stay 0; paper=1 allows perpetual paper models |
| `OANDA_STREAMING_ENABLED` / `OANDA_PAPER_ENABLED` / `OANDA_LIVE_EXECUTION_ENABLED` / `OANDA_INSTRUMENT_ALLOWLIST` / `OANDA_MAX_NOTIONAL` | OANDA | 0 | Live execution default 0 |
| `ALPACA_PAPER_TRADING_ENABLED` / `ALPACA_LIVE_TRADING_ENABLED` / `ALPACA_DATA_FEED` / `ALPACA_OPTIONS_DATA_FEED` / `ALPACA_MAX_NOTIONAL_USD` / `ALPACA_INSTRUMENT_ALLOWLIST` | Alpaca | 1 / 0 / iex / indicative | Paper-first; data-feed upgrade without code change |
| `TWELVE_DATA_CREDIT_BUDGET_PER_MINUTE` / `TWELVE_DATA_DAILY_CREDIT_BUDGET` / `TWELVE_DATA_COMMERCIAL_DISPLAY_LICENSED` | Twelve Data | — / — / 0 | Credit accounting; no external display without licence |
| `MASSIVE_WEBSOCKET_ENABLED` / `MASSIVE_MAX_REQUESTS_PER_MINUTE` | Massive | 0 / — | Rate-limit guard |
| `FRED_MAX_REQUESTS_PER_SECOND` / `FRED_VINTAGE_DATA_ENABLED` / `FRED_POINT_IN_TIME_REQUIRED_FOR_BACKTESTS` | FRED | 2 / 1 / 1 | Point-in-time macro discipline |
| `TRADING_ECONOMICS_POINT_IN_TIME_ENABLED` | Trading Economics | 1 | Backtest correctness |
| `COINGLASS_FUNDING_ENABLED` / `..._OPEN_INTEREST_ENABLED` / `..._LIQUIDATIONS_ENABLED` / `..._LONG_SHORT_ENABLED` / `..._MAX_REQUESTS_PER_MINUTE` | CoinGlass | 1 / 1 / 1 / 1 / — | Capability flags per subscribed plan |
| `ALPHA_VANTAGE_DAILY_REQUEST_BUDGET` / `ALPHA_VANTAGE_USE_FOR_LIVE_DELIVERY` | Alpha Vantage | 25 / 0 | Free tier never used for high-frequency scans |
| `PROVIDER_*` generic controls (`PROVIDER_REGISTRY_ENABLED`, `PROVIDER_AUTO_DISCOVERY_ENABLED`, `DYNAMIC_INSTRUMENT_DISCOVERY_ENABLED`, `DYNAMIC_UNIVERSE_ENABLED`, `PROVIDER_DEFAULT_TIMEOUT_SECONDS`, `PROVIDER_DEFAULT_MAX_RETRIES`, `PROVIDER_DEFAULT_CIRCUIT_FAILURE_THRESHOLD`, `PROVIDER_HEALTHCHECK_ENABLED`, `PROVIDER_COST_BUDGET_ENABLED`, `PROVIDER_DISAGREEMENT_CHECK_ENABLED`, `PROVIDER_STALE_DATA_REJECTION_ENABLED`, `MARKET_DATA_PUBLIC_AUTO_ENABLE`, `EXECUTION_AUTO_ENABLE_FROM_CREDENTIALS=0`, `EXECUTION_REQUIRE_EXPLICIT_ENABLE=1`, `PROVIDER_SECRET_LOGGING_ENABLED=0`) | global | as listed | Fail-closed defaults; execution never auto-enables from credentials |

## Explicitly NOT added (already exist)

`PAYSTACK_*`, `TELEGRAM_BOT_TOKEN`, `DATABASE_URL`, `REDIS_URL`/`REDIS_STATE_URL`,
`PAPER_*`, `EXECUTION_*` safety flags, `QUALITY_*`, `BINANCE_API_KEY`/`SECRET`,
`BYBIT_API_KEY`/`SECRET`, `ALPACA_API_KEY`/`SECRET`, `POLYGON_API_KEY`,
`TWELVEDATA_API_KEY`, `FINNHUB_API_KEY`, `OANDA_API_KEY`, `COINGECKO_API_KEY`,
`NASDAQ_DATA_LINK_*`, `EODHD_*`, `MARKETSTACK_API_KEY`, `TIINGO_API_KEY`,
`FMP_API_KEY`, `TRADIER_*`, `CRYPTOCOMPARE_API_KEY`.

## v2.2 additions (adapters implemented 2026-08-05)

| Variable | Provider | Service | Secret | Req/Opt | Default | Already existed? | Canonical replacement | Activation effect | Railway env |
|---|---|---|---|---|---|---|---|---|---|
| `MASSIVE_API_KEY` | Massive (Polygon.io) | all | **yes** | opt | — | alias | `POLYGON_API_KEY` | One consolidated secret; MASSIVE wins, POLYGON alias kept. Credentials alone never enable execution | all |
| `MASSIVE_API_BASE_URL` | Massive | all | no | opt | api.massive.com | no | — | Overrides REST base URL | all |
| `MASSIVE_MARKET_DATA_ENABLED` | Massive | all | no | opt | 1 | no | — | Gates polygon adapter candles | all |
| `COINGECKO_ENABLED` / `COINGECKO_ACCESS_MODE` | CoinGecko | all | no | opt | 1 / keyless | yes (partial legacy) | `COINGECKO_API_KEY` legacy alias | Keyless public discovery + last-resort candles; `pro` upgrades base URL | all |
| `COINGECKO_PRO_API_KEY` / `COINGECKO_DEMO_API_KEY` | CoinGecko | all | **yes** | opt | — | no | — | Upgrade to Pro/Demo endpoints; never activates execution | all |
| `COINGECKO_USE_FOR_EXECUTION_QUOTE` | CoinGecko | all | no | opt | 0 | no | — | Must stay 0 (context only) | all |
| `GECKOTERMINAL_API_URL` | GeckoTerminal | all | no | opt | api.geckoterminal.com/api/v2 | no | — | DEX pool metadata base URL | all |
| `COIN_METRICS_ENABLED` / `COIN_METRICS_ACCESS_MODE` | Coin Metrics | all | no | opt | 1 / community | no | — | Keyless Community market candles + network metrics | all |
| `COIN_METRICS_API_KEY` | Coin Metrics | all | **yes** | opt | — | no | — | Upgrades to Pro API; never activates execution | all |
| `DEFILLAMA_ENABLED` / `DEFILLAMA_PRO_ENABLED` | DefiLlama | all | no | opt | 1 / 0 | no | — | Keyless TVL/stablecoin/yield context + discovery | all |
| `FRED_ENABLED` / `FRED_API_KEY` | FRED | engine | **yes** | opt | 1 / — | no | — | Dormant without key; macro series + vintages | engine |
| `TRADING_ECONOMICS_ENABLED` / `TRADING_ECONOMICS_API_KEY` | Trading Economics | engine | **yes** | opt | 0 / — | no | — | Dormant without key; economic calendar | engine |
| `COINGLASS_ENABLED` / `COINGLASS_API_KEY` | CoinGlass | engine | **yes** | opt | 0 / — | no | — | Dormant without key; funding/OI/liquidations | engine |
| `DUNE_ENABLED` / `DUNE_API_KEY` | Dune | worker | **yes** | opt | 0 / — | no | — | Dormant without key; scheduled SQL results | worker |
| `KAIKO_ENABLED` / `KAIKO_API_KEY` / `KAIKO_REGION` | Kaiko | engine | **yes** | opt | 0 / — / us | no | — | Dormant without key; institutional data | engine |
| `GLASSNODE_ENABLED` / `GLASSNODE_API_KEY` | Glassnode | worker | **yes** | opt | 0 / — | no | — | Dormant without key; on-chain metrics | worker |
| `CRYPTOQUANT_ENABLED` / `CRYPTOQUANT_API_KEY` | CryptoQuant | worker | **yes** | opt | 0 / — | no | — | Dormant without key; on-chain metrics | worker |
| `EXECUTION_AUTO_ENABLE_FROM_CREDENTIALS` | global | all | no | opt | 0 | no | — | Must stay 0; credentials never enable execution | all |
| `EXECUTION_REQUIRE_EXPLICIT_ENABLE` / `EXECUTION_REQUIRE_PROVIDER_CERTIFICATION` / `EXECUTION_REQUIRE_USER_OPT_IN` | global | all | no | opt | 1 | no | — | Guarded execution gates | all |
