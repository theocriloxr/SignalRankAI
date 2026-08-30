# Phase 4 Pass 1 — Signal Correctness and Live Validation

Date: 2026-07-14

Accepted parent baseline: `ca616b11043683aaa5a5c01702f292a5a5c42591` (`fix-2`)

Current local checkpoint: `3a0dad6a47065cf94aa2f36fe486fd06b48a7243`

Scope: Phase 4 Pass 1 only; Passes 2–10 were not started.

## Outcome

Pass 1 is implemented and its automated exit gate is satisfied. The final Telegram send boundary no longer treats a cached float or local fetch time as proof of a live market quote. It now fails closed unless a newly fetched, source-timestamped provider quote passes the versioned quote, session, drift, target, stop, and risk/reward rules.

No database migration, dependency, payment, execution, tier entitlement, or deployment-role behavior was changed.

## Implemented contracts

### Typed provider result

`data/provider_types.py` defines:

- `LivePriceQuote` with canonical/provider symbols, asset class, price/bid/ask, source/receive/complete times, latency, quote kind, provider/breaker health, confidence reasons, request ID, session metadata, and optional cross-provider deviation;
- `LivePriceFailure` so the typed provider path returns an explicit reason rather than an ambiguous `None`;
- `FinalQuotePolicy` version `phase4-pass1-v1`;
- a pure `validate_quote_for_final_delivery` decision with exact lifecycle block states.

Initial source-age ceilings match the Phase 3 plan:

| Asset class | Maximum source age |
|---|---:|
| Crypto | 10 seconds |
| FX | 15 seconds |
| Commodity | 15 seconds |
| Stock | 30 seconds |
| Index | 30 seconds |

Previous close is analysis-only. A DB tick without a source timestamp is rejected. Missing source time, an unhealthy provider, open breaker, low confidence, excessive cross-provider deviation, future clock error, unsupported class, and unknown market state all fail closed.

### Provider adapters and compatibility

`data/get_live_price.py` now has typed Binance, Bybit, CryptoCompare, Yahoo, and Polygon quote adapters:

- Binance uses the 24-hour ticker payload for last/bid/ask and provider `closeTime`;
- Bybit parses the V5 ticker list and response source time;
- CryptoCompare uses the full raw payload and `LASTUPDATE`;
- Yahoo accepts `regularMarketPrice` only with `regularMarketTime`; previous close remains tagged analysis-only while failover continues;
- Polygon uses last-trade data for supported equity/index routes;
- failover has an overall bounded deadline and typed terminal failure.

The existing `get_live_price_quote`, `get_live_price`, and cached-float interfaces remain available for analysis and legacy callers. Only the consequential final-send path requires the strict typed contract.

### Canonical instruments and sessions

`services/asset_mapper.py` now provides `InstrumentSpec`, canonical aliases, provider symbols, tick-size defaults, session calendar names, and first-class index mappings. Required fixtures cover BNB, META, XAUUSD, EURUSD, and US500/SPX500. Punctuation in legitimate stock tickers such as `BRK-B` is preserved.

`data/market_hours.py` now provides a typed authoritative session result with:

- crypto 24/7;
- FX weekend and major-holiday closure;
- commodity weekend and daily maintenance windows;
- US equity/cash-index hours using `America/New_York` for DST;
- index cash-versus-CFD modes;
- fail-closed unsupported/missing instruments.

`data.fetcher.market_closed_reason` delegates to this contract and retains its legacy rules only as an exception fallback.

### Final delivery gate

`engine/delivery_freshness.py` adds explicit `final_send=True` behavior:

1. validates signal and queue age;
2. ignores cached/naked prices;
3. fetches a new typed quote;
4. validates quote source age, kind, provider trust, and market session;
5. validates direction, stop placement, monotonic TP ordering, TP/SL already reached, stop-distance drift, current RR, and class drift;
6. returns exact states including `BLOCKED_STALE`, `BLOCKED_PROVIDER_UNTRUSTED`, `BLOCKED_MARKET_CLOSED`, `BLOCKED_RISK_INVALID`, `MISSED_ENTRY`, `EXPIRED_IN_QUEUE`, or `LIVE_CHECK_PASSED`;
7. records policy version, quote/request provenance, source age, and rule results.

The original drift defaults are now active even when no environment override exists:

| Asset class | Maximum entry drift |
|---|---:|
| Crypto | 0.20% |
| FX | 0.08% |
| Stock | 0.35% |
| Commodity | 0.20% |
| Index | 0.25% |

`signalrank_telegram/bot.py` invokes this strict mode after delivery reservation and before render/send. Cached signal prices are not passed. Final-validation timeout and exception flags can no longer fail open. Successful validation attaches quote provenance to the delivery payload.

The older stale-signal validator still serves compatibility callers. At final send it does not perform an additional unbounded secondary network request because the typed quote has already passed the provider policy; optional cross-provider deviation is evaluated by that policy.

## Test evidence

### Pre-change focused baseline

Command:

```text
python -m pytest tests/test_delivery_freshness.py tests/test_phase4_pass1_live_validation.py tests/test_indices_asset_support.py tests/test_signal_delivery_ack.py -q
```

Result: **19 passed**, 2 warnings.

### Pass 1 focused/impacted verification

The focused and impacted suites cover:

- source-age boundaries for every supported asset class;
- previous-close and DB-tick rejection;
- provider health, breaker, confidence, and cross-provider divergence;
- BNB/META/XAUUSD/EURUSD/index mappings;
- DST, holidays, weekends, FX open, commodity maintenance, crypto 24/7, and index modes;
- final fresh-fetch enforcement and cached-price rejection;
- risk geometry, drift defaults, RR, TP/SL, TTT, and provenance;
- Binance/Yahoo payload contracts and typed provider failure;
- Telegram final-send invocation and acknowledgement compatibility;
- adjacent tracker, engine, strategy, risk, routing, governance, and profile behavior.

Latest focused result: **48 passed**, 2 warnings, in 6.57 seconds.

Latest impacted command result: **111 passed, 2 deselected**, 9 warnings. The two deselections were unrelated inherited checks: one source-string assertion already absent at the accepted parent and one `tmp_path` test blocked by Windows ACLs.

### Source compilation

```text
python -m compileall -q core data db engine ml payments paystack services signalrank_telegram web
```

Result: **passed**.

### Exact collection

Result: **468 tests collected, 1 collection error**. The inherited blocker remains:

```text
ImportError: cannot import name 'verify_api_key' from 'web.app'
```

### Otherwise collectable repository suite

The suite was run using all `tests/test_*.py` files except the single collection-blocking broker-permission file.

Result: **435 passed, 31 failed, 2 errors**, 30 warnings, in 83.38 seconds.

The accepted Phase 1 baseline was **406 passed, 31 failed, 2 errors**. Pass 1 adds 29 passing tests while preserving the same 31 failures and 2 environment/test-fixture errors. The failures remain in previously identified web/payment, readiness, DB-pool expectation, lifecycle, outcome-test-mock, encoding, and source-contract areas. The two errors are Windows ACL failures for pytest `tmp_path`.

## Exit gate and limitations

Automated Pass 1 exit gate:

- typed final quote contract: **passed**
- required asset mappings: **passed**
- market/session boundary matrix: **passed**
- stale/provider/closed-market fail-closed decisions: **passed**
- TP/SL/drift/TTT/risk geometry: **passed**
- Premium/VIP cannot send through the normal Telegram boundary without `LIVE_CHECK_PASSED`: **passed**
- focused and adjacent regression suites: **passed**
- repository-wide failure count increased: **No**

Operational canary and live-provider soak evidence are still required before public production readiness. This pass does not claim provider SLAs, live profitability, or launch readiness.

Phase status:

- Phase 4: **in progress**
- Pass 1 — Signal Correctness and Live Validation: **complete**
- Passes 2–10: **not started**
- Public production readiness: **No**
- Permitted next action: **Phase 4 Pass 2 — DB Priority and Command Speed**
