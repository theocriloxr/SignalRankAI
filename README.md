
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
- Set all secrets as Railway environment variables.
- Use PostgreSQL for production DB.
- Start command: `python main.py`

## Legal & Transparency
- No profit guarantees
- No black-box trading
- All signals are risk-aware and explainable

---

For more, see the full documentation and deployment checklist.
For more details, see `deploy_checklist.txt` and `.env.example`.
