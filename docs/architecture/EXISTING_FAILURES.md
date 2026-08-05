# EXISTING_FAILURES — verified status on 2026-08-05

Each item from the V2.0 brief's known-issue list was re-checked against the
current checkout. Statuses: `RESOLVED` (code + tests in HEAD), `VERIFIED_OK`
(never reproduced), `OPEN` (still missing), `EXTERNAL` (needs credentials).

| # | Known issue | Status | Evidence |
|---|---|---|---|
| 1 | `_env_bool` undefined in `db/pg_features.py` | RESOLVED | central helpers in `core/env.py`; suite green |
| 2 | Outcome persistence coupled to notification fan-out in one transaction | RESOLVED | outbox repair + per-item savepoint path; `tests/test_v1369_outcome_delivery_recovery.py` |
| 3 | Performance reconciliation failing for every user | RESOLVED | per-user transaction/classification; `tests/test_v1368_performance_scale_hotfix.py` |
| 4 | Terminal outcome coverage ~79.4% | RESOLVED (code path) | outcome ordering + outbox repair; final coverage requires staging runtime evidence |
| 5 | Webhook p99 above six seconds | RESOLVED (architecture) | durable webhook queue + immediate ack; SLO tracked in `core/slo_registry.py`; runtime p99 needs load evidence |
| 6 | Resend jobs repeatedly exhausting budget | RESOLVED | bounded claims, cursors, backoff, lease guards; `tests/test_scheduler_registry.py` |
| 7 | TradingView rate-limit loops | RESOLVED | feature flag enforced before network, circuit breakers, rate-limit bookkeeping |
| 8 | XAGUSD live-quote failures vs OHLC availability | RESOLVED (correct classification) | typed failures + quote trust policy never treat candles as live quotes |
| 9 | Paystack recovery disabled (incomplete key pair) | RESOLVED | canonical resolver accepts test-key recovery config; worker mode == front door |
| 10 | Exactly-once outcome delivery runtime certification | OPEN (runtime) | logical dedup exists; real runtime certification needs staging evidence |
| 11 | Semantic dedup + four-hour user–asset locks runtime certified | OPEN (runtime) | unit-covered; runtime certification pending |
| 12 | Load certification for 100,000 users | EXTERNAL | load profiles/sims required against representative infra |
| 13 | Web/mobile ecosystem, multi-provider execution, copy trading, marketplace, lab | OPEN (declared) | contracts/capability manifests in place; adapters + UI flagged disabled, listed in `BLOCKED_EXTERNAL_REQUIREMENTS.md` |

## Remaining suite failures on this branch (pre-existing, not caused by V2.0 work)

* `test_score_signal_soft_caps_instead_of_flattening_to_100` — scoring drifts
  from the test's pinned 95–100 soft-cap window (yields 92.07). Scoring code
  is untouched; thresholds are NOT weakened to manufacture a pass.
* `test_admin_pulse_uses_db_evidence_when_global_stats_are_zero` — test's fake
  DB session does not match the current `admin_pulse` query path.
* `test_database_readiness_returns_ready_from_consolidated_row` — test's fake
  session returns no rows for the current single-catalogue-query
  `.mappings().one()` implementation.
* `test_live_price_provider_routing_stock_not_fx` — network-dependent; passes
  on re-run when external providers respond.
