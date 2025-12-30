
# SignalRankAI

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
