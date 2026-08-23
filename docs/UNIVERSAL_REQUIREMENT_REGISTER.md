# Universal Requirement Register

Last updated: 2026-07-26
Status vocabulary: `IMPLEMENTED`, `VERIFIED_LOCAL`, `LIVE_PROOF_REQUIRED`, `BLOCKED_EXTERNAL`, `DISABLED_BY_POLICY`, `REVIEW_REQUIRED`.

This register reconciles the repository, the supplied v5 completion prompt, historical project documentation, previous Railway incidents, migrations, tests and deployment profiles. A passing unit test does not by itself change a live-proof requirement to complete.

| ID | Requirement | Implementation/evidence location | Current status | Remaining acceptance evidence |
|---|---|---|---|---|
| SR-RUN-001 | One canonical FastAPI Railway monolith, one process and one Uvicorn worker | `railway_main.py`, `web/app.py`, `start.sh`, Railway env profiles | VERIFIED_LOCAL | Railway staging boot and soak |
| SR-DB-001 | PostgreSQL durable truth and PgBouncer-safe bounded sessions | `db/session.py`, `db/priority.py`, migrations, DB audits | VERIFIED_LOCAL | Real PgBouncer transaction-pool test |
| SR-REDIS-001 | Separate state and delivery Redis roles with bounded pools | `core/redis_state.py`, `core/redis_streams.py`, env profiles | VERIFIED_LOCAL | Live two-Redis outage/recovery test |
| SR-REDIS-002 | Redis loss must rebuild from PostgreSQL, never erase durable signals | recovery services and regression tests | VERIFIED_LOCAL | Staging flush/restart evidence |
| SR-SIG-001 | Generated/stored/delivered/paper/shadow/backtest/demo/live evidence stays separate | models, repositories, performance and outcome services | VERIFIED_LOCAL | Same-signal live lifecycle evidence |
| SR-DEL-001 | Telegram success plus `sent_ok`, chat/message IDs and active message constitute delivery proof | delivery pipeline and `SignalDelivery` | VERIFIED_LOCAL | Dedicated Telegram test-bot proof |
| SR-DEL-002 | Same-user same-asset repeat lock defaults to four hours after proven delivery | `services/asset_repeat_policy.py`, `db/pg_features.py`, bot/dedup paths | VERIFIED_LOCAL | Staging restart and Redis-loss proof |
| SR-DEL-003 | Delivery fan-out is batched, bounded, idempotent and RetryAfter-aware | broadcaster/delivery paths and tests | VERIFIED_LOCAL | Network load and uncertain-send tests |
| SR-PROF-001 | `scalp`, `day`, `swing`, `position`, `all` persist and alter engine/delivery policy | trade profiles, preferences, Telegram profile flows | VERIFIED_LOCAL | Full profile × tier staging matrix |
| SR-TIER-001 | Canonical tiers `free`, `premium`, `vip`, `admin`, `owner` | tier constants, access policy and commands | VERIFIED_LOCAL | Payment/entitlement staging matrix |
| SR-ASSET-001 | Crypto, FX, commodities, equities, indices and correctly classified derivatives | asset mapper, registry, providers, strategies | VERIFIED_LOCAL | All enabled classes live data E2E |
| SR-PROV-001 | Every enabled provider has capability metadata, validation, rate controls and certification status | `data/provider_catalog.py`, connectors, `scripts/certify_providers.py` | VERIFIED_LOCAL | Public/sandbox/keyed live certification |
| SR-PROV-002 | Delayed/historical providers cannot silently become live execution truth | provider catalog/routing and validation | VERIFIED_LOCAL | Cross-provider live freshness evidence |
| SR-STRAT-001 | Registered strategies declare supported assets/timeframes and return valid geometry | strategy registry and tests | VERIFIED_LOCAL | All-strategy compatible-data orchestration |
| SR-RISK-001 | Advisory and execution risk gates are fail-closed when critical state is unavailable | engine, risk, exposure, broker gates | VERIFIED_LOCAL | Staging fault-injection evidence |
| SR-OUT-001 | TP/SL/missed/expiry lifecycle, MFE/MAE, R and notifications are idempotent | lifecycle/outcome services and tests | VERIFIED_LOCAL | Natural/replay same-signal staging proof |
| SR-ML-001 | Structured positive and rejected-candidate telemetry is collected without live heavy training | telemetry, rejection spool, model registry | VERIFIED_LOCAL | Production telemetry sample/export evidence |
| SR-ML-002 | Offline export/training is leakage-aware and promotion is governed | ML scripts/docs | REVIEW_REQUIRED | Complete offline pipeline evidence and model card |
| SR-TG-001 | Every registered command and visible callback is reachable, role-gated and prompt-ACKed | Telegram modules and command-contract tests | VERIFIED_LOCAL | Dedicated bot full command/button run |
| SR-TV-001 | TradingView alerts are authenticated, fresh, idempotent and pass normal risk/delivery gates | FastAPI route and tests | VERIFIED_LOCAL | Signed staging webhook test |
| SR-PAY-001 | Paystack verification, HMAC, idempotency, entitlement, receipt/refund/reconciliation | payment services and tests | VERIFIED_LOCAL | Paystack test-mode E2E |
| SR-BROKER-001 | MetaApi/MT5 demo path uses live quote/spec/account, no fake balance or fallback lot | broker abstraction, router, bridge and tests | VERIFIED_LOCAL | MetaApi demo E2E/reconciliation |
| SR-BROKER-002 | Real execution/copy trading requires independent approval and remains disabled | execution flags and gates | DISABLED_BY_POLICY | Separate security/risk pilot |
| SR-OBS-001 | Health/readiness, structured metrics, provider/DB/Redis/delivery diagnostics | web health and observability scripts | VERIFIED_LOCAL | Railway metrics/alerts/soak |
| SR-SEC-001 | Secrets, webhook auth, RBAC, replay, IDOR and log-redaction controls | security tests/configuration | VERIFIED_LOCAL | Staging penetration/dependency evidence |
| SR-TEST-001 | Complete local orchestrator runs static, env, schema, governance, Railway simulation, fan-out, provider and integration checks | `scripts/run_complete_system_test.py`, `artifacts/complete-system-test-final/` | VERIFIED_LOCAL | Live Railway and external integrations remain separate |
| SR-CI-001 | Weekly evidence review produces immutable, anonymized JSON/Markdown research artifacts | `services/continuous_improvement/`, `tools/continuous_improvement_review.py` | VERIFIED_LOCAL | Scheduled staging run and retention proof |
| SR-CI-002 | OpenAI review is optional, aggregate-only, structured, bounded, and disabled by default | continuous-improvement reviewer and `services/codex_governance.py` | VERIFIED_LOCAL | Configured staging API request |
| SR-CI-003 | Recommendations and Codex tasks cannot autonomously modify or deploy production | recommendation, experiment, promotion and handoff contracts | VERIFIED_LOCAL | Human approval workflow exercise |
| SR-REL-001 | Clean-room deploy, Railway staging, owner proof and 24–72 hour soak precede public release | deployment/runbooks | LIVE_PROOF_REQUIRED | Owner permissions and credentials |

## Unresolved business decisions

- Exact current weekly/monthly subscription prices.
- Whether any tier-specific same-asset cooldown should explicitly override the canonical four-hour default.
- Final public daily signal/score policy where historical documents conflict with current constants.
- Data-retention periods requiring legal/business approval.
- Real-execution release scope and jurisdictions.
