# ARCHITECTURE_BASELINE — SignalRankAI

Reference architecture recorded from the checked-out repository on 2026-08-05.
This is the baseline the V2.0 programme extends; existing abstractions are
preserved and repaired rather than replaced.

## Service boundaries (deployed roles)

| Role | Owner | Responsibilities |
|---|---|---|
| Front door | `railway_main.py` + `signalrank_telegram/bot.py` | Telegram webhook, command/callback routing, Paystack webhook route, health/readiness, capability startup diagnostics |
| Engine | `engine/` + `railway_main.py` | Strategy scan cycles, scoring, geometry validation, tier eligibility, canonical signal persistence |
| Worker | `worker/worker.py` + `worker/*` | Outcome tracker, performance reconciliation, outbox repair, adaptive learning, market monitor, news sync, resend recovery |
| Delivery | bot broadcaster + `core/redis_streams.py` | Immediate fanout, claims, freshness validation, Telegram send, proof writes |
| Migration | one designated Railway pre-deploy job | `alembic upgrade head` only (never raced across services) |

## Data flow (signal pipeline)

```
market data providers
  -> strategy candidates
  -> canonical geometry builder (stop < entry < target validation)
  -> base production-quality gate
  -> canonical signal persistence (final_signals/stored)
  -> tier eligibility (premium/vip/ultra) — never a universal reject
  -> delivery eligibility (dedup, four-hour lock, freshness, profile)
  -> immediate fanout / recoverable resend
  -> outcomes -> performance ledger -> notifications
```

## Event flow (V2.0)

```
business write commits
  -> transactional outbox (core/transactional_outbox.py)
  -> relay -> durable transport (DurableEventStream | RecoverableStream)
  -> idempotent consumer inbox (exactly-once logical processing)
  -> projectors (notifications, outcomes, ledger, paper accounts)
  -> typed failures -> circuit breaker -> provider quarantine
```

## Key invariants

* PostgreSQL is the transactional source of truth; Redis holds short-lived
  queues/state; dashboards are never the system of record.
* Every delivery carries provider provenance + source timestamp; stale or
  unattributed quotes are rejected at final send (`data/provider_types.py`).
* Real execution / payouts remain fail-closed behind explicit guarded
  activation (`core/financial_activation.py`, `GLOBAL_EXECUTION_KILL_SWITCH`).
* One Alembic head; engine/worker readiness fails when the schema is behind.
* Staging uses isolated bots, test Paystack keys and staging resources and
  never falls back to the production bot token.
