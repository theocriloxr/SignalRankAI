# Historical recovery and independent acceptance audit — 24 October 2026

Branch `feat/frontend-rebuild-and-stage1-hardening` (based on the Stage 1 head `393f3d88`). This pass was performed independently of the implementation checklists: it re-read the requirement sources, inspected code, probed the live public deployment read-only, and classified what the evidence supports. **Stage 1 and release remain NO-GO.** No production change, migration, deployment, broker call, payment or permission change was made.

Classification used here: **verified · partially verified · blocked · not implemented · awaiting approval · unresolved ambiguity** (plus *not yet assessed* where this pass did not reach a requirement — reported honestly rather than folded into another bucket).

## 1. Historical completeness audit (safeguard 1)

### Sources searched

| Source | Status | Notes |
| --- | --- | --- |
| Repository working tree and full history | Searched | 4,659 commits reachable; 241 remote branches; 0 tags; branch `implementation-of-master-blueprint` present; frozen blueprint commit `878747fc` is an ancestor of this branch. |
| Pull requests | Searched (counts refreshed live) | 200 PRs (1 open: draft #201). 199 previously retained in `evidence/github-pulls.jsonl`; #201 retained in continuation evidence. |
| Issues and discussions | Searched | Discussions disabled. One historical issue retained in `evidence/github-issues.jsonl`; live API re-count was interrupted by network resets. |
| Repository documentation, all historical versions | Previously indexed | `evidence/historical-documentation-index.json` (1,049 versions across 535 paths). |
| Owner-supplied DOCX packages (23 Aug, 30 Sep 2026) | Previously ingested | 14,226 clauses, 1,586 headings, 242 seeds (`crosschat_source_index.json`). |
| **Owner-supplied `message.txt` (new)** | **Ingested and consolidated** | SHA-256 `b78374d0…`, 10,298 lines, 8 documents + the five-safeguard note → 287 consolidated requirement IDs, 28 historical-fact leads, 0 duplicate IDs (`evidence/continuation-20261024/source_intake.json`). Not previously indexed. |
| Live public deployment | Probed read-only | `/version`, `/healthz`, `/readyz`, `/login`, `/app` (results in §3). |
| Railway control plane | Prior read-only snapshot only (16 Oct) | No Railway access in this session. |

### Information gaps (not searched — inaccessible)

| Gap | What it may contain | How to close it |
| --- | --- | --- |
| Original ChatGPT/assistant conversations (all eras) | Requirements, decisions and rejected proposals never exported | Owner exports conversations; ingest by hash as above. |
| Telegram chats other than the supplied export | Further decisions or incident reports | Owner exports relevant chats. |
| Production logs (engine, worker, frontdoor) | Why the engine has no heartbeat (§3) | Railway access (read-only logs). |
| Production database contents | Real rejection distributions, delivery history, entitlements | Read-only replica or sanitized export. |
| Railway service runtime state since 16 Oct | Whether the engine service is deployed/running | Railway access. |
| `indexes/blueprint_modules.csv` | 129-row module map named by an earlier contract | Owner supplies the file. |
| Provider, broker, Paystack, Telegram, OpenAI/Gemini consoles | Real entitlements, model availability, webhook delivery | Credentials for sandbox/demo/test modes. |

A zero-omission claim is therefore **not** made.

## 2. Regression-proof migration (safeguard 2)

| Check | Result |
| --- | --- |
| Web API usage before vs after the frontend rebuild | **Verified.** All 61 backend calls made by the pre-rebuild app (`393f3d88`) are still made; 6 added (billing products/checkout/confirm/cancel-auto-renew/refund-request, signal feedback). Locked by `frontend/scripts/api-baseline.test.mjs` + `api-call-baseline.json`. |
| Page and route handlers | **Verified.** The same 11 route files exist before and after. |
| Strategies and engine | **Verified for this branch:** `git diff 393f3d88 -- strategies engine` is empty — no strategy removed or altered. |
| Backend behavior after branch changes | **Verified locally.** Full suite at `e9b2b368`: 4,098 passed, 0 failed, 1 skipped (§8). |

## 3. Live production observations (read-only, 2026-10-24)

| Probe | Result |
| --- | --- |
| DNS | `www` and apex resolve to Railway (via 8.8.8.8). |
| `/version` | `1.5.1`, `git_sha 9865a3d1`, branch `fix/provider-discovery-readiness-20260923`; `build_timestamp`, `image_digest`, `schema_head` = `unknown`. |
| `/healthz` | 200, `signals_active: 0`. |
| `/readyz` | **503 `degraded`.** All checks pass (database at `0053_research_market_inputs` = expected, Redis state/delivery, provider coverage, outcome projection 8/8, performance ledger 25/25, ML calibration validated on 4,368 rows, OpenAI, Telegram, webhook secret, shadow tracker) **except `engine_runtime`: `health_probe_failed:ValueError`.** Engine Pulse (interval 86,400 s): 0 signals and 0 deliveries recorded in its window. |
| `/login` | 404 — the rebuilt Next frontend is not deployed. |

**Root-cause finding.** The probe's `ValueError` came from parsing an *absent* `engine:last_cycle` heartbeat. The engine writes that key (TTL ≥ 60 s, 2 h default) at every cycle stage, so no engine cycle has run recently: the production signal engine is not cycling. This explains the signal/delivery drought recorded since early October. The probe now reports `engine_heartbeat_missing` with an operator action (commit `8a7d3e3b`). Diagnosing *why* the engine process is not cycling requires Railway logs — **blocked (access)**. Production is also two migrations behind the repository head (`0054`, `0055`).

## 4. Historical fact register — independent status

| ID | Status | Evidence / next action |
| --- | --- | --- |
| FACT-01 domain/brand | Partially verified | Domain resolves; live; "Powered by CRILOX Solutions" in rebuilt frontend (not deployed). |
| FACT-02 branches/commits | Verified | Branch exists; frozen commit is ancestor. |
| FACT-03 migrations | Partially verified | Prod DB `0053` = prod expected; repo head `0055`. Promotion requires authorization. |
| FACT-04 Railway topology | Blocked (access) | 16 Oct snapshot only; engine service state unknown. |
| FACT-05 service observations | Blocked (access) | Needs runtime metrics. |
| FACT-06 0 signals stored | **Reproduced (production)** | Engine heartbeat absent; Engine Pulse 0 signals. Needs logs. |
| FACT-07 `_env_bool` / v1.3.6.9 | Partially verified | Every runtime caller defines or imports `_env_bool`; v1.3.6.9 regression tests exist, re-run pending. |
| FACT-08 terminal coverage | Partially verified | Live outcome projection 8/8, ledger 25/25; per-channel terminal-message coverage not recomputed. |
| FACT-09 dedup/exactly-once | Partially verified | Durable thesis fingerprint + advisory locks in code; tests exist; run pending. |
| FACT-10 webhook p99 | Blocked (access) | Needs production/staging load measurement. |
| FACT-11 provider gaps / Binance region | Partially verified | Live provider coverage "complete" for configured trusted providers. HTTP 451 now classified `REGION_RESTRICTED`, logged and backed off (commit `801780d4`). |
| FACT-12 Telegram ingress | Partially verified | Live `telegram: ready`, webhook secret configured; no message round trip tested. |
| FACT-13 stale APP_VERSION | Partially verified | Release SHA matches; build timestamp/digest/schema head report `unknown`. |
| FACT-14 Paystack | Blocked (credentials) | Server-priced checkout, provider verification and truthful availability UI implemented; sandbox round trip untested. |
| FACT-15 ML 84% / 88.05 | Partially verified | Superseded by a calibrated artifact validated on 4,368 rows (Brier 0.166, ECE 0.058). |
| FACT-16 AUC 0.670 vs 0.732 | Partially verified | No record of this experiment exists in the repository or its 1,049 indexed historical documents (information gap: chat-only). Its lesson — no challenger promotion without out-of-sample superiority — is enforced and tested (`tests/test_ml_champion_challenger_governance.py` passes). |
| FACT-17 OpenAI + Gemini | Partially verified / blocked | Live OpenAI configured and available. Gemini default `gemini-3.8-flash` — availability unverified without credentials. |
| FACT-18 cooldowns / fingerprint | **Owner decision: keep current** (24 Oct) | Current freshness limits (600/1800/5400/21600 s), generation leases and 4 h per-user same-asset cooldown kept. Effective duplicate suppression: 0.3 % log thesis band + 0.3 % semantic tolerance at persistence. Finding kept by decision: the engine Redis pre-filter bucket is exact-match for prices ≥ 1. Locked by `tests/test_owner_decisions_20261024.py`; recorded in `requirements_conflicts.md`. |
| FACT-19 Redis 4 workers / 500 | Verified (meaning) | "4 workers" = `WEBHOOK_UPDATE_WORKERS` (Telegram webhook dispatch pool; default 4, max 16). In-process queue default is now 1,000 (historically 500) with a Redis-backed queue depth of 2,000. Production values are environment settings not visible here. |
| FACT-20 historical test counts | Not applicable | Historical only; current suites must be re-run. |
| FACT-21 load / DR | Not implemented (for this release) | No staging environment exists. |
| FACT-22 missing ecosystem | Not yet assessed | Release-to-requirement map pending. |
| FACT-23 version-specific fixes | Partially verified | Regression tests exist for many; full re-run pending. |
| FACT-24 XAUTUSDT sessions | **Owner decision: keep current** (24 Oct) | `tokenised_commodity` on the `crypto_24_7` calendar; locked by `tests/test_owner_decisions_20261024.py`. |
| FACT-25 Engine Pulse cadence | Verified | Live `interval_seconds: 86400`. |
| FACT-26 crypto signals-only, delivered-only execution | Partially verified | Live execution not requested; execution routes require delivery receipts; new focused-universe admission at MT5/Bybit chokepoints. |
| FACT-27 live features disabled | Verified (production) | Live `financial_activation`: requested false, live execution false, payouts false. Beta audience allowlist exists and is forced off in public production (audience `global`). |
| FACT-28 design rebuild | Partially verified | Rebuilt and checked locally (desktop, light theme, 375 px); not deployed. |

## 5. The five safeguards

| Safeguard | Status |
| --- | --- |
| 1 Historical completeness audit | Partially verified — sources and gaps above; semantic review of all 287 consolidated IDs continues. |
| 2 Regression-proof migration | Verified locally — frontend API/route baseline, untouched strategies, and full suite 4,098 passed / 0 failed vs 4,076 baseline. |
| 3 Multi-user isolation | **Verified locally** — `tests/test_multi_user_isolation_postgres_20261024.py`, 5/5 passed against real PostgreSQL through the real platform routes (concurrent identities; IDOR on watchlists, journal, tickets, alerts; per-recipient deliveries, feedback, notifications; device sessions; profile persistence; payment references; per-user cooldowns). Staging/production multi-user evidence still required. |
| 4 Completion ≠ authorization | Verified — nothing in this branch enables live trading, payouts or live payments; production reports them disabled. |
| 5 Independent final acceptance | In progress — this document. |

## 6. Coverage of this pass

Of 287 consolidated requirement IDs, this pass individually assessed the 28 historical-fact leads, the 5 safeguards and the focused-universe, billing, readiness and provider items changed on this branch. The remaining requirements are **not yet assessed** in this pass and keep their existing `requirements.json` dispositions; none was promoted to verified.

## 7. Next actions

| Owner | Action |
| --- | --- |
| Owner (access) | Grant read-only Railway log access, or check the engine service (`striking-optimism` or the role-configured engine) is deployed and running; read its logs before restarting. |
| Owner (decision) | Done 24 Oct: keep current behavior for FACT-18 and FACT-24. Optional: approve aligning the engine Redis pre-filter with the thesis band. |
| Owner (billing) | Restore GitHub Actions (account billing lock) so CI can run. |
| Owner (credentials) | Paystack test keys, Gemini key, broker demo accounts for staging certification. |
| Agent | Done: full suite and isolation suite recorded in §8. Install `pyarrow` and re-run the one skipped Parquet test. |
| Agent | Done: per-ID assessment in §9. |

## 8. Verification evidence recorded after the audit (24 Oct 2026)

| Check | Commit | Environment | Result |
| --- | --- | --- | --- |
| Full Python suite `pytest -q tests` with `SIGNALRANK_POSTGRES_INTEGRATION_REQUIRED=1` | `e9b2b368` (clean tree) | macOS arm64, Python 3.12.14 venv, local PostgreSQL 16.2 (`127.0.0.1:55434`, migrated from empty to `0055`) | **4,098 passed, 0 failed, 1 skipped** (Parquet test: `pyarrow` not yet installed). Frozen 2ee0a918 baseline: 4,076 passed — no regression. |
| Multi-user isolation suite (5 tests, real routes, real sessions, real DB) | `e9b2b368` | same | **5/5 passed** |
| Fresh-database migration | `e9b2b368` | same | `alembic upgrade head` from empty → `0055_user_renewal_default` succeeded |
| Frontend: tsc, eslint, `next build`, 101 node tests | `e9b2b368` | Node 22.19, npm 11.17 | all pass |
| Governance generators `--check` (inventory, cross-chat, V7) | `e9b2b368` | — | all pass |
| Full Python suite (same setup, `pyarrow` installed) | `a53ac6be` | same | **4,108 passed, 1 failed, 0 skipped.** The failure was the V7 freshness check, caused by editing the promotion plan during the run; after committing and regenerating, governance tests pass at `d259adc2` (37/37). |
| Privacy + isolation suites on real PostgreSQL | `dea4e7da` | same | 11/11; the New York timezone case fails on the pre-fix code |
| Frontend: tsc, eslint, `next build`, 107 node tests | `dea4e7da` | Node 22.19 | all pass |

**Three pre-existing test defects fixed** (none in branch code): provider-key environment leakage in `test_connectors_providers.py` (order-dependent routing failure); CRLF-captured evidence hashes compared against LF checkouts; GNU-only coreutils assumed by the restore-drill harness.

**Limits of this evidence.** Local only (GitHub Actions remains billing-locked). The local PostgreSQL build lacks the `pgcrypto` extension; a local-only shim implements `digest()` with built-in SHA functions for migration `0034`. `xgboost` 3.2.0 (macOS wheel) stands in for the Linux-only `xgboost-cpu` pin, loading the `libomp` bundled with scikit-learn. A few pins resolved differently on macOS (e.g. `websockets` came transitively). Not native devices, providers, brokers, payments, staging or production.

## 9. Per-requirement assessment (24 Oct 2026)

Every consolidated requirement ID (287, plus the FACT-00 recording rule) now has a status, evidence paths and a next action in [`evidence/continuation-20261024/cx_assessment.json`](evidence/continuation-20261024/cx_assessment.json). The generator refuses to write the file if an ID is missing or duplicated, or if any cited evidence path does not exist in the tree. Labels are paraphrased; the private specification text is not committed.

| Acceptance class | Count |
| --- | ---: |
| Verified (locally only) | 8 |
| Partially verified | 248 |
| Blocked (access, external dependency, owner decision or unresolved history) | 20 |
| Awaiting approval | 7 |
| Not implemented / defective | 5 |

"Verified" here means verified on local PostgreSQL with real routes; none of the 288 is verified in production. Two thirds of the "partially verified" entries have code and passing local tests but no deployment evidence; the rest have known gaps named in their notes.

**Gaps closed during the assessment**

- CX-PRIV-01 / CX-USER-01 — there was no self-service data export or deletion workflow. Added `GET /api/v1/platform/account/export` (owner-scoped sections reused from each screen's read; plan-gated sections reported as unavailable; credentials excluded) and `POST /api/v1/platform/account/deletion-request` (recent sign-in plus typed phrase; opens one `privacy_deletion` support review; deletes nothing; lists records retained for reconciliation). Web panel: Settings → Your data. Tests: `tests/test_privacy_requests_20261024.py` (real PostgreSQL).
- New defect found and fixed: the recent-sign-in age for sensitive actions (API keys, webhooks, deletion) was computed with naive `datetime.utcnow().timestamp()`, which is shifted by the host UTC offset. On UTC hosts (Railway) this was harmless; on a UTC−5 host every sensitive action was refused, and on UTC+ hosts the 15-minute window was extended by the offset. Now uses `time.time()`. The New York regression case fails on the old code and passes on the fix.
- Developer access (API keys, webhooks), plan entitlements and referrals now have web screens (commit `af617d5f`).

**Remaining not implemented / defective**

| ID | Gap | Next action |
| --- | --- | --- |
| CX-AI-08 | No component ablation or OpenAI/Gemini disagreement study | Needs outcome data from a running engine |
| CX-COST-01 | No cost attribution or budgets (OpenAI token counters only) | Design usage ledger; owner to set budgets |
| CX-OBS-03 | Production `/version` reports unknown `schema_head` and `build_timestamp` | Set build metadata in the Railway build; verify after the next authorized deploy |
| CX-STRAT-07, CX-COPY-01 | Marketplace and copy-trading activation | Proposals only; need owner approval |
