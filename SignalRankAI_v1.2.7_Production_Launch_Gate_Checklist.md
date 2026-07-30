# SignalRankAI v1.2.7 Production Launch Gate

Do not open public onboarding until every required item below is proven by the new Railway deployment.

## Deployment identity

- [ ] Boot reports `SignalRankAI v1.2.7`.
- [ ] Release fingerprint is `v1.2.7-outcome-price-production-gate-20260730`.
- [ ] Environment is staging for certification, then production for launch.
- [ ] Exactly one Railway application replica is running.
- [ ] Alembic head is `0027_launch_paper_trading`.

## Telegram

- [ ] Callback ACK guard registered.
- [ ] At least 60 handlers registered and readiness is true.
- [ ] Monitor, Check Outcome, Help navigation and settings buttons respond.
- [ ] Webhook pending count is zero.
- [ ] A forced Redis enqueue timeout returns retryable 503 and does not create a duplicate local copy.
- [ ] One Telegram command update produces exactly one reply.
- [ ] Delivery stream pending, lag and DLQ are zero or within approved limits.

## Outcomes

- [ ] Outcome worker reports `active_scan fetched=>0` when delivered signals exist.
- [ ] Historical uppercase `CONFIRMED` rows are discovered.
- [ ] XAUTUSDT signal `b15e7d94-9bf5-4cf6-8eaa-da842ccd9d7d` reconciles.
- [ ] Entry, TP1 and TP2 events are persisted sequentially.
- [ ] Each lifecycle notification is sent once and marked sent.
- [ ] `/check_outcome` and `/monitor` agree with durable lifecycle state.

## Market prices

- [ ] Monitor displays provider and provider symbol.
- [ ] Monitor displays source age within the trust threshold.
- [ ] XAUTUSDT uses the intended XAUT/USDT venue mapping.
- [ ] No stale legacy Redis tick is displayed as current.
- [ ] Commodity ghost-price protection remains active.

## Adaptive system

- [ ] `/adaptive_status` succeeds with and without an asset argument.
- [ ] Candle upserts succeed without `AmbiguousParameterError`.
- [ ] Candle writes are bounded and incremental.
- [ ] Human approval remains required for promotion.

## Database and Redis

- [ ] PostgreSQL schema/admission check passes.
- [ ] PostgreSQL capacity-headroom check passes.
- [ ] State Redis ping and roundtrip pass.
- [ ] Delivery Redis ping and roundtrip pass.
- [ ] `/system` reports Redis connected.
- [ ] No command is mislabelled as DB pressure when it is a query defect.
- [ ] No second writable database is introduced.

## Paper and simulation

- [ ] Paper worker starts and reports delivery/marking activity.
- [ ] Confirmed eligible deliveries can open paper positions.
- [ ] Paper exits record realised P/L and R multiple.
- [ ] `/simulate` separates terminal outcomes, pending deliveries and TP1/TP2 milestones.
- [ ] No invented win-rate assumption is used.

## Payments

- [ ] Railway contains one valid `sk_live_` and `pk_live_` Paystack pair.
- [ ] Webhook signature verification passes with the server-side secret.
- [ ] A low-value live checkout is initialised and verified end to end.
- [ ] Subscription activation is idempotent.
- [ ] Automatic payouts remain disabled.

## Initial public boundary

- [ ] `REAL_EXECUTION_ENABLED=0`
- [ ] `AUTO_EXECUTION_ENABLED=0`
- [ ] `AUTO_TRADE_ENABLED=0`
- [ ] `COPY_TRADE_ENABLED=0`
- [ ] `MT5_ALLOW_LIVE_ACCOUNTS=0`
- [ ] `BYBIT_EXECUTION_ENABLED=0`
- [ ] `REAL_PAYOUTS_ENABLED=0`

Public subscriptions, signal delivery, callbacks, outcome notifications, paper trading and demo/manual execution may be opened only after all other required checks pass.
