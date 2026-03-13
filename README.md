
#!/usr/bin/env
# SignalRankAI

Production-ready (in-progress) paid Telegram trading signals platform.

## Architecture (high level)

- `worker/worker.py`: async background worker loop (market data -> strategies -> controller -> dispatch)
- `engine/signal_controller.py`: single gatekeeper for approval (consensus, HTF alignment, scoring thresholds)
- `web/app.py`: FastAPI app for health/metrics + Paystack webhook verification

## Quick start (local, no secrets)

1) Create env file:

- Copy `.env.example` to `.env` and fill only what you have.

2) Install deps:

- `py -m pip install -r requirements.txt`

3) Run web API:

- `py -m uvicorn web.app:app --host 0.0.0.0 --port 8000`
- Health: `GET http://localhost:8000/health`
- Metrics: `GET http://localhost:8000/metrics`

4) Run worker:

- `py worker/worker.py`

5) Run Telegram bot (recommended):

- `set RUN_MODE=bot` then `py main.py` (Windows PowerShell: `$env:RUN_MODE="bot"; py main.py`)

## Legacy Telegram bot

The older implementation in `telegram/` is kept for backward compatibility, but it is guarded to prevent accidental production use.

- Recommended: `RUN_MODE=bot py main.py`
- Legacy opt-in: `ALLOW_LEGACY_TELEGRAM_BOT=true py -m telegram.bot`

## Secrets & safety

- Never commit `.env` (repo includes `.gitignore`).
- Webhook verification uses HMAC SHA-512 via `x-paystack-signature`.

## Disclaimer (mandatory)

SignalRankAI provides algorithmic market analysis for educational purposes only.
This is not financial advice. Trading involves risk.

## Performance policy

- No profit promises.
- We use language like: “historically filtered for high-probability setups” and “risk-managed signals”.
- We avoid: “guaranteed”, “100% win rate”, “daily profits”.

## Refund policy

Due to the digital and time-sensitive nature of the service, payments are non-refundable.
If technical issues prevent delivery, subscription time may be extended.

## Data & security

- We store Telegram IDs (no passwords).
- Payments are handled by Paystack.
- SignalRankAI never has access to your funds.

## Pricing (Nigeria + global)

- **Free**: 1–2 delayed summaries/day, limited outcomes & summaries.
- **Premium**: ₦10,000/month; ₦24,000/3 months; ₦40,000/6 months.
- **VIP**: ₦40,000/month (limited seats).
- VIP seats are capped by `VIP_SEAT_LIMIT` (default 15). Owners and bypassed users do not consume seats.
- **Owner**: internal only (OWNER_TELEGRAM_ID or `/unlock`).

Use `/pricing` and `/upgrade` in the bot.

### Paystack plan codes

Create Paystack plans and store these environment variables:

- `PAYSTACK_PLAN_CODE_PREMIUM_MONTHLY`
- `PAYSTACK_PLAN_CODE_PREMIUM_QUARTERLY`
- `PAYSTACK_PLAN_CODE_PREMIUM_SEMIANNUAL`
- `PAYSTACK_PLAN_CODE_VIP_MONTHLY`

## Payments (Paystack)

- Configure `PAYSTACK_WEBHOOK_SECRET` and `PAYSTACK_SECRET_KEY`.
- Local development can use `PAYMENTS_ENABLED=false` (webhook will be accepted after signature verification but will skip Paystack verify call).

## Notes

This repo is being upgraded from a SQLite + polling prototype into a production layout with FastAPI, worker process separation, and stricter signal governance.

A production-grade, rule-based trading signal platform enhanced with probabilistic ML filtering for quality control.

## Key Features

### Signal Generation & Quality
- ✅ **Real-time live market data** from Yahoo Finance (crypto + stocks)
- ✅ **Signal validation system** - Automatic rejection of invalid signals
- ✅ **Signal corrections** - Users notified when signals have errors
- ✅ **Deduplication** - No repeated signals to the same user
- ✅ **ML scoring** - XGBoost probability filter (0.79 AUC)
- ✅ **Multi-strategy consensus** - Momentum, Trend, Structure, Volatility
- ✅ **Advanced filters** - Regime detection, liquidity checks, correlation limits

### Market Coverage
- ✅ **Crypto trading** - BTCUSDT, ETHUSDT, SOLUSDT, etc. (Yahoo Finance)
- ✅ **Stock trading** - AAPL, MSFT, TSLA, etc. (enable with `STOCK_TRADING_ENABLED=true`)
- ✅ **FX trading** - EUR/USD, GBP/USD, etc. (AlphaVantage, optional)
- ✅ **Nigeria-optimized** - Works around Binance geo-blocking

### User Experience
- ✅ **Current prices** - Live price display in `/signal` and `/outcome`
- ✅ **Outcome tracking** - Automated TP/SL tracking with R-multiple
- ✅ **Performance stats** - 30-day win rate, avg R, total signals
- ✅ **Referral rewards** - Invite friends, earn bonus days
- ✅ **Extra signals** - Buy additional daily signals (₦300/signal, 24h)

### Technical Excellence
- ✅ **Deterministic pipeline** - Rule-based, explainable signals
- ✅ **Owner controls** - Kill switch, manual corrections, revenue tracking
- ✅ **Tiered access** - FREE (delayed), PREMIUM (instant), VIP (ultra-quality)
- ✅ **Railway-ready** - Single-service deployment with `RUN_MODE=all`
- ✅ **Auto-migrations** - Alembic database migrations on boot
- ✅ **Secure payments** - Paystack integration with webhook verification

## Local Testing
1. Copy `.env.example` to `.env` and fill in your values.
2. Set `DRY_RUN=true` and `PAYMENTS_ENABLED=false` for safe local testing.
3. Run `python main.py`.
4. Simulate signals, payments, expiry, and admin actions.

## Deployment

### Railway (recommended)

Create **one Railway project** and add **4 services** from the same repo (same codebase), each with a different `RUN_MODE`.

**1) Add Postgres**

- Add a Railway Postgres plugin.
- Copy its `DATABASE_URL` to each service as an environment variable.
- Migrations are run automatically on boot when `DATABASE_URL` is set.
	- You can still run them manually: `python -m alembic upgrade head`

**2) Create services**

Each service uses the same start command: `python main.py`.

- **web**: `RUN_MODE=web`
- **bot**: `RUN_MODE=bot`
- **engine**: `RUN_MODE=engine`
- **worker**: `RUN_MODE=worker`

**3) Required environment variables**

- `DATABASE_URL` (Railway Postgres)
- `TELEGRAM_TOKEN`
- `PAYSTACK_SECRET_KEY`
- `PAYSTACK_WEBHOOK_SECRET` (or reuse `PAYSTACK_SECRET_KEY`)
- `OWNER_TELEGRAM_ID` (or `OWNER_IDS` comma-separated)
- `BYPASS_KEY` (used by `/unlock <key>`)
- `PUBLIC_BASE_URL` (your Railway web domain; used for Paystack callbacks)
- `ADMIN_API_TOKEN` (protects `/admin/killswitch` endpoints)

Optional (recommended):
- `AUTO_MIGRATE=true` (default) runs Alembic upgrades automatically on boot.
- `FRESH_START=true` (dangerous) wipes Postgres data ONCE on the next web boot and starts with an empty database.
	- This resets bot-side history (users/subscriptions/signals/referrals/deliveries/queues).
	- It does NOT delete Telegram chat history in users' apps (Telegram does not allow bots to do that).

**4) Recommended environment variables**

- `VIP_SEAT_LIMIT` (default 15)
- `TRADABLE_ASSETS` (comma-separated fallback list; no demo symbols are hardcoded)
- `CRYPTO_TRENDING_TOP_N` (default 10; limits Binance auto-discovery)
- `FX_PAIRS` + `ALPHAVANTAGE_API_KEY` (optional; required only if FX is enabled)
- **AlphaVantage free-tier safety** (recommended):
	- `FX_MAX_PAIRS=3`
	- `FX_TIMEFRAMES=1d`
	- `ALPHAVANTAGE_MIN_SECONDS_BETWEEN_CALLS=15`

**5) Paystack webhook**

- In Paystack dashboard, set webhook URL to:
	- `https://<your-railway-web-domain>/webhooks/paystack`

Notes:
- `/signals` uses Postgres-backed delivery history (today’s signals sent to you).
- Signal delivery is deduped per user, and signal generation is deduped for ~24h using a fingerprint.

### Railway (single service)

If you prefer a simpler setup (one container, one deploy), you can run everything under a single Railway service.

**Start command**

- `python main.py`

**Service variables**

- `RUN_MODE=all`
- `PORT` is provided by Railway (do not hardcode unless required)
- All variables listed under “Required environment variables” above

**What it runs**

- FastAPI web server (health/metrics + Paystack webhook)
- Telegram bot polling
- Engine loop
- Worker loop

**Tradeoffs**

- Higher CPU/RAM usage than splitting into 4 services (Railway free tier may be tighter).
- If one component crashes, the whole service restarts.

## Legal & Transparency
- No profit guarantees
- No black-box trading
- All signals are risk-aware and explainable

---

For more, see the full documentation and deployment checklist.
For more details, see `deploy_checklist.txt` and `.env.example`.

## Documentation

- Comprehensive technical documentation: [docs/PROJECT_DOCUMENTATION.md](docs/PROJECT_DOCUMENTATION.md)
- Functional specification: [docs/FUNCTIONAL_SPEC.md](docs/FUNCTIONAL_SPEC.md)
- Implementation status matrix: [docs/IMPLEMENTATION_STATUS.md](docs/IMPLEMENTATION_STATUS.md)
