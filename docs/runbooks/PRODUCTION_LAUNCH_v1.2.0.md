# SignalRankAI v1.2.0 Production Launch

## Scope

This release launches the Telegram signal, lifecycle, subscription, adaptive-observation, and per-user paper-trading product. Existing deterministic strategies remain authoritative. Adaptive research is additive and cannot auto-promote.

## Deploy

1. Deploy the complete v1.2.0 source archive.
2. Run `alembic upgrade head` and verify revision `0027_launch_paper_trading`.
3. Apply `SignalRankAI_v1.2.0_Railway_Production_Launch.env.example` without committing secrets.
4. Verify `/healthz`, `/livez`, and `/readyz` return 200.
5. Verify Telegram command scopes are republished and no ordinary user sees Admin or Owner commands.

## Required runtime evidence

- `[boot] SignalRankAI v1.2.0`
- `[worker] PaperTradingWorker started`
- `[paper_worker] started`
- `[bot_commands] global launch catalogue published`
- `[bot_commands] per-user scopes complete`
- `[worker] AdaptiveStrategyLearning started`
- `[worker] AdaptiveCandleCapture started`
- `delivery_proof_write ... state=CONFIRMED`

## Paper trading

Paper trading uses virtual funds only. It consumes only Telegram-confirmed deliveries belonging to the user. Users control it through `/paper_balance`, `/paper_settings`, `/paper_positions`, `/paper_history`, `/paper_performance`, and `/paper_reset`.

## Broker execution

Demo execution may be used after per-user account linking, consent, encryption, risk, quote, market, and reconciliation preflight. Real accounts, automatic execution, and copy trading remain independently gated until live certification is complete.

## Payments

Public payments require valid live Paystack keys, verified webhook signatures, successful transaction reconciliation, and receipt proof. Real payouts remain disabled.

## Rollback

Rollback application code to v1.1.1 only after disabling the paper worker. Migration 0027 is additive; do not downgrade while paper records exist. Restore the previous application package and retain database data for audit.
