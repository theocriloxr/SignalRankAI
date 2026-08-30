# SignalRankAI v1.2.4 — Log-Driven Runtime Admission Release

Date: 2026-07-29

## Why this release exists

The v1.2.3 Railway log proved that the adaptive imports, Telegram handler registry,
and worker startup defects were fixed, but it exposed four remaining integration
problems:

1. Railway reported the deployment as staging while runtime safety used a stale
   `APP_ENV=production` first, so the main process disabled full-system staging.
2. Paper trading and adaptive candle persistence used background DB admission and
   were repeatedly deferred by the two-connection foreground reservation.
3. Strategy scoring produced scores around 95 but every final candidate was
   blocked before storage, preventing delivery and paper/execution proof.
4. The offline readiness checker falsely reported missing health routes because it
   matched one exact decorator spelling and ignored the Railway monolith routes.

## Corrections

- Railway environment identity now takes precedence over stale application-level
  environment variables.
- Runtime safety reports acknowledgement validity separately from whether staging
  mode is permitted.
- Full-system staging sets a validated active marker and enforces demo/testnet
  boundaries.
- Paper trading and adaptive candle capture receive interactive DB admission in
  validated full-system staging mode.
- Advanced filters receive real ATR percentage, EMA and session context.
- Advanced, ultra, production-quality and Gemini gates remain observable but become
  advisory for allowlisted staging-test traffic only.
- Test-only signals are marked `staging_test_only` and
  `exclude_from_production_performance`.
- Production mode retains hard quality gates.
- Gate heatmaps now run after every asset rather than only after a storage
  exception.
- Proxy validation is disabled automatically when no proxy provider URL exists.
- Readiness checks recognise the real health and metrics routes in both web and
  Railway entrypoints.

## External limitations

- Paystack payment and payout certification remains blocked until `sk_test_...`
  and `pk_test_...` credentials are configured.
- TradingView rate-limit circuit openings are non-fatal because other strategy
  engines continue, but provider quota certification is still required.
- The current WebSocket providers may remain unavailable from the Railway region;
  REST market data remains authoritative and healthy.
