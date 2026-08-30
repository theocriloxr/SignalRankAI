# Performance Ledger and Paper-Trading Reliability

## Scope and source of truth

Migration `0031_perf_paper_reliability` introduces the canonical user-performance ledger and the paper-attempt ledger. The domains remain separate:

- `outcomes`: global signal outcome and canonical terminal result.
- `performance_ledger_entries`: proof-backed live user-delivery cohort, one row per user/signal/environment.
- `user_signal_monitoring`: user-specific Stop result, preferred over the global outcome for that user.
- `paper_positions`, `paper_trade_attempts`, and `paper_ledger_entries`: simulated execution only.
- ML shadow/training tables: model provenance only; unproven rows are marked excluded from proof-backed live use.
- Backtests and shadow predictions are never mixed into user live performance.

A live-user row requires all durable Telegram proof fields: `sent_ok=true`, a confirmed delivery state, `delivery_confirmed_at`, `telegram_chat_id`, and `telegram_message_id`. The cohort starts inclusively and ends exclusively in UTC.

Finalized outcome and performance rows are immutable during ordinary operation. An outcome correction requires `audited_correction=true`, `corrected_by`, and `correction_reason`. The performance ledger database trigger additionally rejects finalized row changes without correction attribution.

## Canonical formulas

For included completed realized results `R_i`:

- Net R: `sum(R_i)`
- Average R: `sum(R_i) / n`
- Median R: statistical median of `R_i`
- Standardized simple return at 1% risk: `sum(R_i) * 1%`
- Average standardized return: `(sum(R_i) / n) * 1%`
- Standardized compounded return: `(product(1 + R_i * 0.01) - 1) * 100%`

The standardized returns are illustrations, not account returns. `/performance` labels this explicitly and does not fall back to unverified SQL estimates.

Primary buckets are mutually exclusive: `PENDING_ENTRY`, `ACTIVE`, `STOPPED_AT_TP1`, `STOPPED_AT_TP2`, `TP3`, `SL`, `BREAKEVEN`, `TIME_STOP`, `MISSED_ENTRY`, `EXPIRED`, `CANCELLED`, `TRACKING_FAILED`, or `PROVIDER_UNAVAILABLE`. For each report, confirmed deliveries must equal the sum of all buckets.

## Paper sizing and state model

Sizing uses `Decimal` throughout:

```text
fee_rate = fee_bps / 10000
configured_cap = cash * max_notional_pct / 100
fee_adjusted_cash_cap = cash / (1 + fee_rate)
affordable_notional = min(configured_cap, fee_adjusted_cash_cap)
risk_quantity = (cash * risk_pct / 100) / abs(fill - stop)
quantity = min(risk_quantity, affordable_notional / fill)
required_cash = quantity * fill + entry_fee
```

Admission requires `required_cash <= cash + PAPER_CASH_TOLERANCE`. Exit fees are deducted from closing proceeds before realized P/L is credited. A skipped/deferred decision is stored in `paper_trade_attempts`; `paper_positions` contains only genuine open/closed positions plus preserved legacy placeholders. Retryable provider and entry-watch decisions have `next_retry_at` and a delivery-freshness deadline. Permanent filters require an explicit `/paper_retry` override.

## Environment variables

```dotenv
PAPER_TRADING_ENABLED=1
PAPER_AUTO_TRADE_DEFAULT_ENABLED=0
PAPER_TRADING_START_BALANCE_USD=10000
PAPER_DEFAULT_RISK_PCT=1
PAPER_DEFAULT_MAX_OPEN_POSITIONS=5
PAPER_DEFAULT_MIN_SIGNAL_SCORE=80
PAPER_DEFAULT_TARGET_MODE=TP1
PAPER_DEFAULT_SPREAD_BPS=2
PAPER_DEFAULT_SLIPPAGE_BPS=2
PAPER_DEFAULT_FEE_BPS=5
PAPER_AUTO_ENTRY_MAX_AGE_SECONDS=900
PAPER_TRADING_WORKER_INTERVAL_SECONDS=20
PAPER_TRADING_DELIVERY_BATCH_SIZE=200
PAPER_TRADING_MARK_BATCH_SIZE=100
PAPER_MAX_NOTIONAL_PCT=95
PAPER_CASH_TOLERANCE=0.00000001
PAPER_ENTRY_RETRY_SECONDS=15
```

Auto trading is opt-in. Existing accounts retain their persisted choice. `/paper_settings auto on|off` confirms success only after the stored value is read back.

## User and operator commands

- `/paper_status`: account configuration, worker heartbeat, and recent activity summary.
- `/paper_activity`: recent attempts and real positions.
- `/paper_skips`: recent skipped/deferred reasons.
- `/paper_retry <signal-id>`: explicit retry intent within the delivery freshness window.
- `/performance 7d|30d|90d`: canonical cohort report.
- `/performance details`: recent reconciled rows.
- `/performance audit`: owner/admin invariant report.

## Deployment procedure

1. Back up PostgreSQL and capture `alembic current`.
2. Deploy the code with paper auto-entry still off by default.
3. Run `alembic upgrade head`; expected head is `0031_perf_paper_reliability`.
4. Run a read-only user audit:
   `python scripts/audit_performance_ledger.py TELEGRAM_USER_ID --days 30`.
5. Preview historical ledger materialization:
   `python scripts/reconcile_performance_ledger.py TELEGRAM_USER_ID --days 90`.
6. Apply only after reviewing the reconciliation ID and invariant:
   `python scripts/reconcile_performance_ledger.py TELEGRAM_USER_ID --days 90 --apply`.
7. Preview the fee-sizing repair:
   `python scripts/repair_paper_fee_sizing_skips.py`.
8. Apply it after reviewing every proposed action:
   `python scripts/repair_paper_fee_sizing_skips.py --apply`.
9. Opt selected users into auto paper trading and verify `/paper_status`, one eligible delivered signal, the attempt row, cash, fees, and worker-cycle logs.

The repair command never opens a trade. The normal worker revalidates proof, freshness, terminal state, account settings, current entry conditions, and available cash.

## Rollback and incident response

Turn off `PAPER_TRADING_ENABLED` first to stop paper processing. Preserve attempt, position, ledger, and correction rows for forensics. Prefer a forward fix; migration downgrade can be unsafe after an invalidated legacy placeholder and a genuine position coexist for the same user/signal because the old full unique constraint cannot represent both. Restore from backup if schema rollback is mandatory.

If `/performance` reports an invariant failure, do not display estimates. Capture the reconciliation ID, run the read-only audit, and correct source lifecycle/monitoring data through an attributed repair. Never edit finalized ledger rows directly.
