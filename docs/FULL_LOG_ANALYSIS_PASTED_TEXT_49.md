# SignalRankAI full Railway log analysis — Pasted text (49)

Date analysed: 2026-07-25

## Evidence-based verdict

The deployment starts, the database and Redis connect, Telegram webhook mode is
healthy, and the OHLC pipeline now returns usable data. The user day profile was
eligible. No signal was received because the delivery lifecycle corrupted fresh
candidate entries through a second legacy price path and then rejected them
against the canonical final quote. Sequential per-user fanout later exceeded the
75-second queue-age gate. Signals were also entered into the legacy in-memory
portfolio before Telegram proof or entry touch, which falsely exhausted exposure
limits.

## What the log proved

- PostgreSQL public-test pool: 2/0.
- Health endpoint: HTTP 200.
- Telegram webhook: registered, zero pending errors.
- Handler readiness: 164 handlers.
- OHLC: six of six assets usable in two observed batches; effective concurrency 2;
  no orphan tasks.
- Cycle 1: 156 strategy outputs, 6 final candidates, 1 stored LINKUSDT signal.
- Cycle 2: 182 strategy outputs, 4 final candidates, 1 stored XRPUSDT signal.
- The day profile was explicitly eligible for LINKUSDT.
- No telegram_send_ok, delivery proof, active-message persistence, or completed
  delivery appeared in the supplied log.

## Root causes corrected in this package

1. Stale candidates are no longer partially rebased and resent.
2. Every stale/rejected candidate is persisted as SHADOW_REJECTED learning data
   with original entry, trusted quote, drift, provider provenance, strategy,
   score, regime, and reason.
3. Shadow outcome evaluation fetches prices outside DB sessions.
4. The legacy trade tracker is disabled by default, so storage cannot create an
   active/open trade.
5. Segment-quarantine analytics timeouts no longer masquerade as signal-storage
   failures.
6. Optional timeframe enrichment uses phase-scoped diagnostics and no longer
   emits false missing-required-timeframe failures.
7. Provider network calls use provider semaphores and a strict attempt budget.
8. Missing API keys are skipped before they can consume the fallback budget.
9. Queue-age limits for the owner soak are increased without weakening the final
   live-quote fail-closed gate.
10. All-asset learning is moved to a bounded analytics role.
11. ML training uses labelled background DB admission and delayed analytics
    ownership.
12. The optional Railway scheduler import no longer disables startup when a
    legacy web-only job symbol is absent.

## Learning categories

- LIVE_DELIVERED: delivery-proof-backed signals only.
- SHADOW_REJECTED: stale, risk-rejected, quality-rejected, provider-blocked and
  other non-delivered decisions.
- PAPER: paper execution only.
- BACKTEST / WALK_FORWARD: research results only.
- LEGACY_UNVERIFIED: historical rows without complete delivery evidence.

Only LIVE_DELIVERED may contribute to live performance.

## Recommended Railway roles

1. Gateway: public FastAPI + Telegram webhook and command/callback scheduler.
2. Engine: market data, strategies, scoring and candidate/outbox creation.
3. Worker: expiry, maintenance and initial live outcome ownership.
4. Analytics: stale/rejected shadow outcomes, all-asset candle learning and
   delayed ML training.
5. Optional delivery: durable receipt reconciliation.
6. Optional outcome: dedicated live outcomes only after worker ownership is
   disabled.

Never run duplicate outcome or shadow owners.

## 24-hour soak acceptance evidence

- no premature `Trade opened` event;
- `[rejection_learning] stored` for stale/rejected candidates;
- `[shadow_tracker] processed` after price outcomes become resolvable;
- `[asset_learning] assets=... candles=...` across asset classes when markets are
  open;
- `[telegram_send_ok]`;
- `[delivery_proof_write]`;
- `[active_message_saved]`;
- `[delivery_completed]`;
- DELIVERED -> WATCHING_ENTRY -> ENTRY_TOUCHED -> ACTIVE;
- no DB admission timeout;
- no orphan OHLC tasks;
- no duplicate Telegram delivery.

Because the supplied run occurred on Saturday, live FX, stock, cash-index and
most commodity validation was market-closed. A full all-class soak must include
at least one weekday market session.
