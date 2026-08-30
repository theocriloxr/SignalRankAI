# SignalRankAI v1.3.0 Production Launch Gate

Do not mark the launch complete unless every required item below is true.

## Railway environment

- [ ] Deploy into a Railway environment whose actual name is `production` or `prod`.
- [ ] Deploy the full v1.3.0 ZIP; do not overlay individual files on v1.2.9.
- [ ] Apply `SignalRankAI_v1.3.0_Railway_Production_Launch.env.example` using Railway variables.
- [ ] Replace every `<...>` placeholder with the correct secret or private service reference; the launch must contain zero placeholder values.
- [ ] Remove old staging variables and allowlists, including `FULL_SYSTEM_TEST_USER_IDS`.
- [ ] Do not set `WEBHOOK_DOMAIN`, `WEBHOOK_URL`, or `APP_BASE_URL` to the old staging URL.
- [ ] Confirm Railway injects the intended production `RAILWAY_PUBLIC_DOMAIN`.
- [ ] Confirm `STATE_REDIS_URL` and `DELIVERY_REDIS_URL` reference distinct Redis services.
- [ ] Keep one Uvicorn worker and one Railway application replica until distributed job ownership is separately certified.

## Mandatory variables

- [ ] `APP_ENV=production`
- [ ] `APP_VERSION=1.3.0`
- [ ] `PUBLIC_TESTING_MODE=0`
- [ ] `FULL_SYSTEM_STAGING_TEST_MODE=0`
- [ ] `DELIVERY_AUDIENCE_ALLOWLIST=` is empty
- [ ] `RESEND_AUDIENCE_ALLOWLIST_ONLY=0`
- [ ] `RUN_ENGINE_LOOP=1`
- [ ] `RUN_WORKER_LOOP=1`
- [ ] `WORKER_OUTCOME_TRACKER_ENABLED=1`
- [ ] `ENGINE_OUTCOME_TRACKER_ENABLED=0`
- [ ] `FREE_SIGNAL_DISTRIBUTION_ENABLED=1`
- [ ] `TRADINGVIEW_ENABLED=0`
- [ ] `REAL_EXECUTION_ENABLED=0`
- [ ] `AUTO_EXECUTION_ENABLED=0`
- [ ] `AUTO_TRADE_ENABLED=0`
- [ ] `COPY_TRADE_ENABLED=0`
- [ ] `MT5_ALLOW_LIVE_ACCOUNTS=0`
- [ ] `BYBIT_EXECUTION_ENABLED=0`
- [ ] `REAL_PAYOUTS_ENABLED=0`
- [ ] `PORTFOLIO_EXPOSURE_FAIL_OPEN=0`

## Secrets and integrations

- [ ] `DATABASE_URL` points to the intended production PostgreSQL database.
- [ ] Telegram bot token, webhook secret, owner ID, Gemini key, and encryption key are populated through Railway secrets.
- [ ] If public payments are enabled, both Paystack keys are a matching live pair and the production webhook is verified.
- [ ] Never paste secret values into logs, source files, or support messages.

## Migration proof

- [ ] Railway pre-deploy migration succeeds.
- [ ] Log or SQL reports Alembic revision `0028_outcome_projection_guard`.
- [ ] `outcomes` contains zero duplicate `signal_id` groups.
- [ ] PostgreSQL contains unique index `uq_outcomes_signal_id`.
- [ ] Deployment diagnostics report `outcome_guard_unique_index=1`.
- [ ] No `InvalidColumnReferenceError` or outcome `ON CONFLICT` error appears.

## Runtime proof

- [ ] Boot banner reports v1.3.0, production, and the correct fingerprint.
- [ ] `/livez` returns HTTP 200.
- [ ] `/healthz` returns HTTP 200.
- [ ] `/readyz` returns HTTP 200 and `production_cutover.detail=public_production`; any missing/example credential, non-live Paystack pair, or shared Redis URL must keep it at HTTP 503.
- [ ] `/metrics/prometheus` returns HTTP 200.
- [ ] Outcome tracker persists or reconciles the historical eight delivered signals.
- [ ] Terminal signals become archived and no longer consume portfolio exposure.
- [ ] A high-scoring eligible candidate produces `stored=1` or greater and a successful dispatch.
- [ ] No `delivery audience allowlist active` message appears.
- [ ] A brand-new Telegram user can run `/start`, `/profile`, update profile settings, and receive eligible public/free signals.
- [ ] Inline buttons acknowledge immediately and complete their action.

## Release decision

- [ ] Signal delivery and manual/paper usage may be public after all gates above pass.
- [ ] Live broker execution, copy trading, and payouts remain disabled until their separate external certification gates pass.
