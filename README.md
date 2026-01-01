
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
- **Premium**: ₦5,000/month; ₦12,000/3 months; ₦20,000/6 months.
- **VIP**: ₦20,000/month (limited seats).
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
- Deterministic, explainable signal pipeline
- ML probability filter (never generates signals)
- Tiered access and secure payments
- Owner/admin controls and kill-switch
- Railway-ready, scalable, and testable

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
- Run migrations once: `python -m alembic upgrade head` (Railway shell on any service).

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

**4) Recommended environment variables**

- `VIP_SEAT_LIMIT` (default 15)
- `TRADABLE_ASSETS` (comma-separated fallback list; no demo symbols are hardcoded)
- `FX_PAIRS` + `ALPHAVANTAGE_API_KEY` (optional; required only if FX is enabled)

**5) Paystack webhook**

- In Paystack dashboard, set webhook URL to:
	- `https://<your-railway-web-domain>/webhooks/paystack`

Notes:
- `/signals` uses Postgres-backed delivery history (today’s signals sent to you).
- Signal delivery is deduped per user, and signal generation is deduped for ~24h using a fingerprint.

## Legal & Transparency
- No profit guarantees
- No black-box trading
- All signals are risk-aware and explainable

---

For more, see the full documentation and deployment checklist.
For more details, see `deploy_checklist.txt` and `.env.example`.
