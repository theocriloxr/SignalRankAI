# SignalRankAI v1.2.8 Production Launch Gate

Do not open public onboarding until every required item is proven by the v1.2.8 Railway deployment.

## Deployment identity

- [ ] Boot reports `SignalRankAI v1.2.8`.
- [ ] Release fingerprint is `v1.2.8-outcome-perf-readiness-hotfix-20260730`.
- [ ] Alembic head is `0027_launch_paper_trading`.
- [ ] Exactly one Railway application replica is used during certification.

## Outcome and user performance

- [ ] No `name 'func' is not defined` warning appears.
- [ ] No legacy `Error updating user performance for signal` warning appears.
- [ ] Proof-backed active deliveries are discovered.
- [ ] Entry/TP/SL/expiry lifecycle transitions persist correctly.
- [ ] User-performance recipients require `sent_ok`, Telegram IDs and a recognised proof state.
- [ ] A recipient-query failure emits `recipient_lookup_failed` without cancelling lifecycle processing.
- [ ] A lifecycle failure emits `signal_check_failed` with signal and asset context.
- [ ] Duplicate recipient IDs do not cause duplicate performance updates.

## Railway observability

- [ ] `/healthz` returns HTTP 200.
- [ ] `/metrics/prometheus` returns HTTP 200 directly from `railway_main.py`.
- [ ] Prometheus response includes `signalrank_service_up`.
- [ ] Prometheus response includes HTTP request metrics.
- [ ] `railway_direct_observability_routes` passes.
- [ ] All nine production-readiness checks pass.

## v1.2.7 regression protection

- [ ] Outcome reconciliation processes proof-backed historical signals.
- [ ] Adaptive candle persistence succeeds without parameter ambiguity.
- [ ] `/adaptive_status` succeeds.
- [ ] Trusted live-price provider, symbol and source age remain visible.
- [ ] WTI ghost-instrument prices remain rejected.
- [ ] Redis enqueue timeouts do not cause dual local/Redis processing.
- [ ] `/system` reports credible Redis and proof-backed backlog status.

## Telegram runtime

- [ ] Handler readiness is true with the expected handler count.
- [ ] Monitor and Check Outcome buttons acknowledge immediately.
- [ ] Callback queries produce one response each.
- [ ] Outcome notifications are idempotent.
- [ ] The deployed environment contains `python-telegram-bot` and APScheduler.

## Payments and execution safety

- [ ] Live Paystack staging is owner-allowlisted and amount-capped.
- [ ] Webhook signature and idempotency checks pass.
- [ ] `REAL_EXECUTION_ENABLED=0` for initial public launch.
- [ ] `AUTO_EXECUTION_ENABLED=0`.
- [ ] `AUTO_TRADE_ENABLED=0`.
- [ ] `COPY_TRADE_ENABLED=0`.
- [ ] `MT5_ALLOW_LIVE_ACCOUNTS=0`.
- [ ] `BYBIT_EXECUTION_ENABLED=0`.
- [ ] `REAL_PAYOUTS_ENABLED=0`.

Public subscriptions, signal delivery, callbacks, lifecycle notifications, paper trading and demo/manual execution may be opened only after all required evidence passes.
