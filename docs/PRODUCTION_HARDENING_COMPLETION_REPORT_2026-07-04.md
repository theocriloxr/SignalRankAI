# SignalRankAI Production Hardening Report - 2026-07-04

## Scope

This pass completed the interrupted Telegram delivery-proof work and addressed
the concrete defects described in the July 4 review: false delivery success,
stale reservations, incomplete partial-win learning, blank explanations, Gemini
review persistence, inconsistent active-signal commands, and Binance-only
microstructure dependencies.

## Delivery Integrity

- A delivery can be successful only after Telegram returns both `chat_id` and
  `message_id`.
- Realtime, resend, extra-signal, free-random, FOMO unlock, edited-signal, and
  delayed-digest paths all use the same proof contract.
- Skipped, filtered, blocked, failed, and stale deliveries remain unsuccessful.
- One API attempt increments `attempt_count` once at reservation, not again at
  confirmation.
- Startup repairs legacy `sent_ok=true` rows that have no Telegram proof.
- Reservations stuck for more than five minutes are released to `retry`.
- `/delivery_debug <signal_ref> [telegram_user_id]` shows the complete owner
  audit trail: state, proof, Telegram IDs, attempts, timestamps, error, and
  outcome.

## Signal Lifecycle And Commands

- `get_delivered_signal_by_ref()` now requires confirmed Telegram proof.
- Active lists exclude archived, expired, and past-deadline signals.
- Active results collapse to the newest signal per asset/timeframe bucket.
- A new accepted signal supersedes older unresolved rows in the same market
  bucket, preventing simultaneous opposing active ideas.
- `/signals` returns a compact ten-row index instead of up to fifty full cards.
- The first five rows include buttons that reopen the confirmed Telegram signal
  message; `/signal <ref>` remains the detailed view.
- `/signal <ref>` no longer rejects a completed signal before outcome handling,
  and its live position variables are initialized before use.

## Outcome And Learning Integrity

- TP1 and TP2 are persisted as `partial_win` rather than `pending`.
- A later stop after TP progress preserves the partial-win classification and
  `reversed_after_tp` evidence.
- Outcome metadata records TP progression, MFE, MAE, and last event price.
- Signal rows receive MFE/MAE updates, allowing strategy and regime attribution.
- Dashboard outcome coverage separates completed win rate from tracking
  coverage; incomplete tracking is no longer presented as complete performance.

## Explanations And Governance

- VIP signal formatting always emits a nonempty `Why:` explanation, using a
  deterministic technical fallback when AI text is unavailable.
- `get_last_gemini_review()` exists and reads typed `RuntimeState` JSON.
- Gemini reviews are persisted without raw `:value::jsonb` bind syntax.
- Governance win/loss aggregation uses `canonical_outcome`.

## News And Economic Events

`NewsAPI` is used for headlines and sentiment. It is not treated as an economic
calendar. Scheduled macro risk uses this waterfall:

1. Redis/DB normalized event cache.
2. Free Fair Economy/Forex Factory weekly JSON feed.
3. Optional Finnhub calendar fallback.
4. Static timing hints only when all timed sources are unavailable.

The normalized event layer provides event time, currency, impact, forecast,
previous, actual, minutes to event, and a news-risk score. TradingEconomics is
not required.

## Free Market Intelligence Coverage

- OHLCV: multi-provider market-data waterfall.
- Order book and spread: Bybit, then OKX, then Binance public endpoints.
- Funding: Bybit, then OKX, then Binance public endpoints.
- Open interest: Bybit public linear endpoint.
- VWAP: computed from normalized OHLCV.
- Correlation and sessions: computed locally.
- MFE/MAE and TP journey: computed by lifecycle tracking.
- News sentiment: NewsAPI, optional X, and CryptoCompare news fallback.
- Economic calendar: free Fair Economy feed plus optional Finnhub.

Options volatility, ETF flows, dark-pool data, and institutional order flow are
not fabricated when unavailable. Their feature weights must remain absent or
low-confidence until a reliable source is configured.

## Railway Variables

### Secrets To Supply

```text
NEWSAPI_KEY=<NewsAPI key>
GEMINI_API_KEY=<Gemini key>
TWELVEDATA_API_KEY=<recommended multi-asset OHLC key>
POLYGON_API_KEY=<recommended stock/index/FX fallback key>
ALPHAVANTAGE_API_KEY=<recommended FX/macro/corporate-data key>
CRYPTOCOMPARE_API_KEY=<recommended crypto fallback key>
```

Optional coverage keys:

```text
FINNHUB_API_KEY=<optional calendar fallback>
COINGECKO_API_KEY=<optional higher-limit CoinGecko access>
FMP_API_KEY=<optional stocks/fundamentals/corporate events>
FCS_API_KEY=<optional FX/commodities fallback>
TIINGO_API_KEY=<optional equities fallback>
X_BEARER_TOKEN=<optional social-news source>
```

### Non-Secret Settings

```text
FOREX_FACTORY_CALENDAR_URL=https://nfs.faireconomy.media/ff_calendar_thisweek.json
ECONOMIC_CALENDAR_CACHE_TTL_SECONDS=3600
ECONOMIC_CALENDAR_TIMEOUT_SECONDS=8
NO_TRADE_BUFFER_MINUTES=30
NEWS_VOLATILITY_BUFFER_MULTIPLIER=1.0
CRYPTO_MICROSTRUCTURE_PROVIDERS=bybit,okx,binance
CRYPTO_DERIVATIVES_PROVIDERS=bybit,okx,binance
ORDER_BOOK_IMBALANCE_THRESHOLD=1.5
SQUEEZE_FUNDING_THRESHOLD=0.0005
GEMINI_MODEL=gemini-2.0-flash
```

Bybit, OKX, Coinbase Exchange, Kraken, Yahoo Finance, and the default economic
calendar feed use public market-data endpoints and require no API secret.

## Verification

- Python compilation passed for every changed Python module.
- Focused hardening suite: 54 passed.
- Full suite: 401 passed, 33 non-blocking deprecation warnings.
- `git diff --check` passed.

## Deployment Evidence Still Required

Automated tests cannot prove external production state. Before declaring the
service healthy, deploy the migration and verify on Railway:

1. Run `/delivery_debug <new_signal_ref> <owner_telegram_id>` and confirm a real
   Telegram `chat_id`, `message_id`, `sent_ok=true`, and confirmed timestamp.
2. Confirm startup logs report legacy invariant repairs and then stop increasing.
3. Confirm new signal, TP1, TP2, SL-after-TP1, and final TP events persist with
   correct lifecycle metadata.
4. Run at least a 12-24 hour soak test and monitor DB pool waits, provider health,
   Telegram RetryAfter events, stale reservations, and outcome coverage.
5. Do not advertise a win rate until outcome coverage is representative.

The code is test-clean. “Everything works perfectly” still requires the live
evidence above; no local test can validate Railway credentials, network policy,
Telegram account state, or real provider availability.
