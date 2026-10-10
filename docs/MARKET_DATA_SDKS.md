# Optional market-data SDKs

The canonical provider waterfall now supports Alpaca's official Python SDK,
Market Data's official `marketdata-sdk-py`, public CCXT spot candles, and IBKR
historical candles through TWS/IB Gateway. `websocket-client` supplies bounded
Coinbase ticker observations to the existing typed quote path. These adapters
add sources to the existing integrations; they never place orders.

`pandas`, `alpha_vantage`, and `yfinance` already belong to the main runtime.
Installing an SDK does not grant market-data subscriptions or certify trading.
Yahoo data remains analysis only in staging/production decisions.

## Install and verify

Use Python 3.11 and a separate environment: MarketData needs `httpx>=0.28.1`,
which conflicts with the application's pinned Telegram client. Do not install
this profile into the application's environment.

```sh
python3.11 -m venv /opt/signalrank-data-sdks
/opt/signalrank-data-sdks/bin/python -m pip install --require-hashes -r requirements-market-data-sdk.lock
/opt/signalrank-data-sdks/bin/python -m pip check
/opt/signalrank-data-sdks/bin/python -m unittest discover -s tests_sdk -v
```

On Windows, use the environment's `Scripts/python.exe` instead of `bin/python`.
Set `MARKET_DATA_SDK_PYTHON` to its absolute path in the application environment.
The main Dockerfiles include this isolated profile at `/opt/market-data-sdk`.
Tests exercise installed vendor request models and parsers with controlled
transports; they are not evidence of a live subscription or broker connection.

The universal hash lock was resolved with a seven-day release-age cutoff:

```sh
uv pip compile requirements-market-data-sdk.txt --universal --python-version 3.11 --generate-hashes --exclude-newer 2026-10-03T00:00:00Z --no-emit-index-url --output-file requirements-market-data-sdk.lock
```

CCXT is pinned to 4.5.60: inspected newer versions pin vulnerable
`multidict==6.7.1`. This profile uses compatible 6.6.4, outside the affected
range in [CVE-2026-104874](https://github.com/advisories/GHSA-54p9-h82j-f925).
Requalify the lock and installed consumer tests before upgrading.

## Provider configuration

| Source | Configuration | Boundaries |
| --- | --- | --- |
| Alpaca | Existing `ALPACA_API_KEY` and `ALPACA_API_SECRET` (or APCA aliases); `ALPACA_DATA_TRANSPORT=sdk`; `ALPACA_DATA_FEED=iex` or `sip` | Default transport remains REST. IEX covers one exchange; SIP needs entitlement. `delayed_sip` is excluded from decision data. Exact crypto quote currency is preserved. |
| Market Data | `MARKETDATA_ENABLED=1`, `MARKETDATA_TOKEN`, `MARKETDATA_MODE=live` | Stock candles only in this adapter. `cached`/`delayed` modes are analysis only; they cannot pass execution-data certification. Options SDK availability is not an implemented option candle route. |
| CCXT | `CCXT_MARKET_DATA_ENABLED=1`, `CCXT_MARKET_DATA_EXCHANGE=kraken` | Public active spot markets only. Allowed venues: kraken, coinbase, okx, bybit, binance, kucoin. No API keys, trading calls, currency substitution, or custom URLs. Venue/timeframe/region limits still apply. |
| IBKR | `IBKR_MARKET_DATA_ENABLED=1`, host, port, client ID, and explicit contract JSON below | Requires authenticated TWS/IB Gateway, subscriptions and network access. Use TWS/Gateway's read-only API setting. Real-time market-data type must be confirmed before history is accepted. No automatic delayed/frozen fallback. |
| Coinbase WebSocket | `COINBASE_QUOTE_TRANSPORT=websocket` | Exact spot product, source time, finite bid/ask/last, sequence and bounded receive. Quotes older than 30 seconds or over 5 seconds in the future fail. Final delivery/account safety checks still apply. Default transport remains REST. |

Set provider priority through the existing class allowlists, for example
`STOCK_MARKET_DATA_PROVIDERS=alpaca,marketdata,ibkr,polygon` or
`CRYPTO_MARKET_DATA_PROVIDERS=okx,bybit,ccxt`. An explicit list does not fall
through to unrelated providers when configuration or credentials are missing.

An IBKR contract map can begin with:

```json
{
  "AAPL": {"symbol": "AAPL", "secType": "STK", "exchange": "SMART", "currency": "USD"},
  "EURUSD": {"symbol": "EUR", "secType": "CASH", "exchange": "IDEALPRO", "currency": "USD"}
}
```

Store that JSON in `IBKR_MARKET_DATA_CONTRACTS_JSON`; do not put credentials
there. Choose a unique `IBKR_MARKET_DATA_CLIENT_ID` per application service.
Cash indices and commodities need their exact qualified contract IDs; a futures
contract is rejected as a replacement for a cash index or spot commodity.
MIDPOINT candles carry `price_type=midpoint` and `volume_available=false`;
their volume field is zero because that series has no traded volume.

The locked PyPI `ibapi` version is **9.81.1.post1**, a legacy official package,
not the current TWS API release. The [current official distribution](https://download2.interactivebrokers.com/installers/tws-api/index.html)
must be qualified separately against the selected Gateway. Its download alone
does not establish compatibility with this profile. IBKR also restricts market
data redistribution; verify the platform's agreement before distributing its
feed to customers.

## Verification and failure behavior

Run `scripts/certify_providers.py --live --providers marketdata,ccxt,ibkr` only
after configuring subscriptions/Gateway access. Each class still needs the
canonical market-class certification and account-specific execution checks.
Market closure, stale bars, denied subscriptions, missing packages, malformed
data and timeouts return no usable data; they never generate synthetic candles.

The gateway accepts only five read operations, runs a fixed worker with `-I`
in a fresh empty working directory (preventing implicit application `.env` reads),
passes operation-specific credentials, suppresses vendor output, and kills and
reaps timed-out children. It is process isolation for dependency compatibility,
not an operating-system security sandbox. Configure only a trusted interpreter.

Coinbase Exchange has no native four-hour candles. The adapter now rejects
that interval rather than labeling six-hour data as four-hour data. Use another
provider for four-hour candles. Exact USD/USDT/USDC pairs are distinct on both
Alpaca and Coinbase; an unavailable pair fails instead of substituting a price.

Official references: [Alpaca feed coverage](https://docs.alpaca.markets/us/docs/market-data-faq),
[MarketData SDK](https://github.com/MarketDataApp/sdk-py),
[CCXT](https://docs.ccxt.com/),
[Alpha Vantage plan limits](https://www.alphavantage.co/documentation/),
[yfinance project scope](https://github.com/ranaroussi/yfinance),
[websocket-client](https://websocket-client.readthedocs.io/).
