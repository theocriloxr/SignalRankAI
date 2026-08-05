# CURRENT_STATE_AUDIT — SignalRankAI

**Audit date:** 2026-08-05
**Branch:** `fix/railway-alembic-url`
**HEAD:** `62f6593` (prior parity/repair commits `76d9a05`, `03cb544`)
**Method:** machine-derived inventory (git grep, AST counts) + full test suite + compile checks.

## Repository summary

| Area | Count / value |
|---|---|
| Source modules | `core/`, `data/`, `db/`, `engine/`, `payments/`, `paystack/`, `services/`, `signalrank_telegram/`, `worker/`, `railway_main.py` |
| Telegram command registrations | 175 `CommandHandler(...)` sites |
| Callback patterns | 15 focused + global fallback router |
| SQLAlchemy models | 61 |
| Alembic migrations | 35 (single head `0034_production_integrity`) |
| Scheduler/loop sites | 33 `add_job` sites (bot) + 15 `_register_task` loops (worker) |
| Test suite (this branch, this pass) | 1226 passed, 4 failed (3 pre-existing test/impl drift + 1 network-flaky; see EXISTING_FAILURES.md) |
| Python | 3.13.7 |

## Already present (audited, not reimplemented)

* **Payments** — canonical resolver (`payments/payment_config.py`), plan catalogue with price validation, type-safe `CheckoutInitializationResult`, idempotent signed webhook, worker recovery.
* **Environment parity** — `core/capability_resolver.py` (environment/service/payments/telegram/trading/payout/provider/migration modes), staging fails closed (never falls back to the production bot token).
* **Event transport** — `core/durable_event_stream.py` (partitioned Redis Streams, consumer groups, DLQ, reclaim) and `core/redis_streams.py` (recoverable queues, dedupe, retry, DLQ).
* **Provider contracts** — `data/provider_contracts.py` (capability manifest, certification states, canonical instrument id), `data/provider_types.py` (typed quotes/failures, quote trust policy), circuit breakers, asset allowlist.
* **Paper trading** — `core/paper_trading_service.py`, `core/paper_ledger.py`, `core/paper_sizing.py` (decimal-safe fee-aware sizing).
* **Signal integrity** — `core/signal_identity.py` (thesis identity), `core/signal_lifecycle.py`, `core/outcome_ordering.py`, partial-exit accounting, outcome outbox repair, production-integrity guard.
* **Ops commands** — `/outcome_rebuild`, `/outcome_audit`, `/performance_rebuild`, `/performance_audit`, `/dedup_audit`, `/notification_audit`, `/paper_audit`, `/queue_status`, `/queue_replay`, `/dead_letter_status`, `/dead_letter_replay`, `/ledger_audit`, `/payment_reconcile`, `/system_health`, `/release_status`, `/kill_switch`, `/provider_status`, `/capabilities`.
* **Observability** — `core/telemetry.py` (Prometheus metrics, OpenTelemetry tracing), structured logging, `core/redis_global_stats.py`.

## New in this V2.0 pass (commit to follow)

| Module | Purpose |
|---|---|
| `core/event_catalogue.py` | Canonical event registry (full §6.1 core list), aggregate mapping, validation |
| `core/transactional_outbox.py` | Outbox/inbox contract, memory implementation, bounded relay with backoff + DLQ |
| `core/durable_event_stream.py` (extended) | `EventEnvelope` upgraded to the full §6.1 identity set + tamper-evident `payload_hash` |
| `data/provider_failures.py` | Typed provider-failure taxonomy (§8), HTTP classification, retry policy |
| `data/canonical_instruments.py` | Rich canonical instrument model (tick/minimum/calendar/status/aliases), split adjustment, alias registry |
| `core/risk_authority.py` | Portfolio risk authority: exposure limits, loss/drawdown/spread/slippage/volatility breakers, kill switch |
| `core/slo_registry.py` | SLO registry (§26), error budgets, typed degradation decisions |
| `core/financial_ledger.py` | Append-only decimal ledger, compensating corrections, double-entry, imbalance/orphan detection, daily snapshots |

## Certification posture

No connector, provider, live-execution or real-money capability is claimed
production-certified in this document. Everything externally dependent is
declared in `BLOCKED_EXTERNAL_REQUIREMENTS.md`.
