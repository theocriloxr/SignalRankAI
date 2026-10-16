# Feature inventory

The exact route, endpoint, command, callback, provider, broker, strategy callable
and timeframe rows are generated in [requirements.json](requirements.json) and
[REQUIREMENTS_TRACEABILITY.md](REQUIREMENTS_TRACEABILITY.md). This index does not
equate source presence with functional or production acceptance.

| Product area | Current foundation | Gap / acceptance still required |
| --- | --- | --- |
| Assets and providers | 37 provider catalogue entries; discovery, instrument metadata, asset classification, candle adapters and quality gates | Per-provider entitlement, environment, freshness, market session and rate-limit proof; catalogue membership is not live data evidence |
| Universe scheduling | Complete database keyset paging, then recovered fair scanner scheduling | Sustained full-universe throughput and fairness under actual provider budgets |
| Strategies | Trend, momentum, volatility, structure, liquidity, Fibonacci, TradingView and stock capability families; IMP and fallback dispatch; adaptive components | Strategy-by-asset/regime/timeframe dispatch and causal quantitative acceptance; no guaranteed win-rate claims |
| Timeframes | Engine: 1m, 5m, 15m, 1h, 4h, 1d; stock capability: 15m, 1h, 4h, 1d | Provider timeframes may be broader or narrower; resampling/closed-bar/session evidence must match each path |
| AI and ML | AI review/operator controls, chronological fit/calibration/validation, immutable research inputs/datasets, health/promotion safeguards | Every research source clause, genuine independent quantitative/forward evidence and configured AI round trips |
| Accounts | Canonical multi-user identity, account ownership, paper/demo/prop/personal concepts and native/web/Telegram session adapters | Cross-account concurrency, lifecycle and device proof; a connected account is not an authorized execution account |
| Brokers | mt4, mt5, bybit declare ready adapters; binance, binanceus, ctrader, ibkr, tradovate, oanda declare integration; okx, coinbase, kraken connection-only; custom_api custom | Broker-by-broker demo receipts and reconciliation; integration/connection-only entries are NOT_IMPLEMENTED at execution scope |
| Execution and risk | Central routing, confirmations, safety flags, loss/exposure controls and kill switches retained | Exact-account demo concurrency/retry/restart/partial-fill/emergency tests and separate live authorization |
| Telegram | 192 command declarations, 28 callback patterns, tier/role mappings and owner diagnostics | Actual dedicated staging bot journeys, stale/cross-user callbacks and per-role permission denial |
| Web/public | Next public/account routes, retained workstation, public policies and canonical API | Browser/keyboard/responsive and returning PWA proof in both workspace modes; the public root GET alone does not establish website health |
| Native | 14 declared destinations, including the default account screen; secure session family and design preserved; Android/iOS bundles export | Signed device installation, deep links, push, offline/expired-session and accessibility proof; unresolved Expo/node-forge advisory |
| Billing/onboarding | Consent gates, optional marketing, explicit recurring acknowledgement, opt-in default migration, verified-payment handling | Provider test-mode charge/renewal/webhook reconciliation; legal/content review; cancellation must be provider-confirmed |
| Cancellation/refunds/privacy | Pending cancellation states and authenticated review-ticket controls | Tickets do not automatically refund, export or erase data; operator fulfillment and retention evidence required |
| Notifications/reports | Delivery receipts, paper/shadow/real provenance, analytics and native preferences | SMTP/APNs/FCM/Telegram configuration, delivery proof and correct eligible-outcome/account-currency totals |
| Administration | Owner/operator diagnostics, controlled scans, force-signal, queues and maintenance surfaces | Role/confirmation/audit/recovery proof; diagnostic generation cannot bypass risk gates |
| Operations | Role-separated Railway runtime, schema migrations, manifest, backup/restore and monitoring tools | Current exact-SHA CI, staging/production observation, restore drill, broker proof and stable soak |

The new requirement matrix also includes both Python handler declarations and
mounted OpenAPI operations. They overlap intentionally: declarations identify
code that may not be mounted; OpenAPI identifies the schema exported by the
canonical app. A schema omits static/health/WebSocket routes, which remain in the
declaration/client inventory. None of these counts is a tested workflow count.

Current accounting: 175 Python handlers, 163 OpenAPI operations, 54 web rows
(including 31 concrete routes expanded from catch-all allowlists), 14 native
destinations, 192 commands, 28 callbacks, 37 providers, 13 brokers, 48 strategy
and component callables, eight strategy families and six engine timeframes.
Clean local browser runs cover both workspace modes; their exact routes and
scenario scope are retained in COMPLETION_EVIDENCE.md.

## Required versus optional

Required behavior derives from the preserved sources and current mission. Missing
broker execution adapters, complete research acceptance, real user journeys,
operational recovery and safe live-release gates are required open work.

Potential improvements such as personalized dashboard layouts, additional
unrequested broker integrations, new strategy families, localization beyond
supplied requirements, or changing hosting providers are optional proposals.
They must not displace source requirements or silently expand Stage 1 scope.

## Misleading completion patterns corrected or retained as blockers

- Old reports and passed-looking URLs cannot produce VERIFIED: receipt validation
  now checks retained artifact content and scope.
- A successful provider HTTP response cannot falsely mark recurring billing
  cancelled; the provider must affirm success and the subscription binding must
  still match after I/O.
- Missing plan prices are displayed as unavailable through the shared currency
  formatter instead of being invented as zero.
- An alphabetical database result cap could starve later instruments even with
  a fair downstream scanner; complete keyset retrieval removes that upstream cap.
- Broker catalogue readiness, review tickets, mock fills and static source tests
  remain explicitly narrower than execution, refund/privacy fulfillment and
  end-to-end evidence.
