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
| Backend behavior after branch changes | **Partially verified.** Focused-universe admission is a no-op unless the staging-only flag is set; full Python suite re-run is pending the dependency install (network). |

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
| FACT-16 AUC 0.670 vs 0.732 | Not yet assessed | Locate the experiment record. |
| FACT-17 OpenAI + Gemini | Partially verified / blocked | Live OpenAI configured and available. Gemini default `gemini-3.8-flash` — availability unverified without credentials. |
| FACT-18 cooldowns / fingerprint | **Unresolved ambiguity** | 4 h same-asset cooldown implemented per user. Timeframe values 600/5400/21600 s now act as *max signal age* (1h = 1800 s, not 1200 s); generation-lock TTLs differ (15m 1 h, 1h 2 h, 4h 4 h, 1d 6 h). Entry fingerprint uses a 0.1 % relative bucket, not 3 decimals. Owner decision needed; no behavior changed. |
| FACT-19 Redis 4 workers / 500 | Not yet assessed | |
| FACT-20 historical test counts | Not applicable | Historical only; current suites must be re-run. |
| FACT-21 load / DR | Not implemented (for this release) | No staging environment exists. |
| FACT-22 missing ecosystem | Not yet assessed | Release-to-requirement map pending. |
| FACT-23 version-specific fixes | Partially verified | Regression tests exist for many; full re-run pending. |
| FACT-24 XAUTUSDT sessions | **Unresolved ambiguity** | Registry: `tokenised_commodity`, calendar `crypto_24_7` (the token trades continuously). Owner to confirm the policy. |
| FACT-25 Engine Pulse cadence | Verified | Live `interval_seconds: 86400`. |
| FACT-26 crypto signals-only, delivered-only execution | Partially verified | Live execution not requested; execution routes require delivery receipts; new focused-universe admission at MT5/Bybit chokepoints. |
| FACT-27 live features disabled | Verified (production) | Live `financial_activation`: requested false, live execution false, payouts false. Beta audience allowlist exists and is forced off in public production (audience `global`). |
| FACT-28 design rebuild | Partially verified | Rebuilt and checked locally (desktop, light theme, 375 px); not deployed. |

## 5. The five safeguards

| Safeguard | Status |
| --- | --- |
| 1 Historical completeness audit | Partially verified — sources and gaps above; semantic review of all 287 consolidated IDs continues. |
| 2 Regression-proof migration | Partially verified — frontend and strategies proven; backend full-suite re-run pending. |
| 3 Multi-user isolation | Implemented, run pending — `tests/test_multi_user_isolation_postgres_20261024.py` (concurrent identities, IDOR on four resource types, per-recipient deliveries/feedback/notifications, sessions, profiles, payments, cooldowns). A local PostgreSQL 16.2 cluster is running; Python dependencies are still downloading. |
| 4 Completion ≠ authorization | Verified — nothing in this branch enables live trading, payouts or live payments; production reports them disabled. |
| 5 Independent final acceptance | In progress — this document. |

## 6. Coverage of this pass

Of 287 consolidated requirement IDs, this pass individually assessed the 28 historical-fact leads, the 5 safeguards and the focused-universe, billing, readiness and provider items changed on this branch. The remaining requirements are **not yet assessed** in this pass and keep their existing `requirements.json` dispositions; none was promoted to verified.

## 7. Next actions

| Owner | Action |
| --- | --- |
| Owner (access) | Grant read-only Railway log access, or check the engine service (`striking-optimism` or the role-configured engine) is deployed and running; read its logs before restarting. |
| Owner (decision) | Decide FACT-18 cooldown/fingerprint semantics and FACT-24 XAUTUSDT session policy. |
| Owner (billing) | Restore GitHub Actions (account billing lock) so CI can run. |
| Owner (credentials) | Paystack test keys, Gemini key, broker demo accounts for staging certification. |
| Agent | Finish dependency install; run the full Python suite, the isolation suite and the new tests on this branch; record results. |
| Agent | Continue per-ID assessment of the remaining consolidated requirements. |
