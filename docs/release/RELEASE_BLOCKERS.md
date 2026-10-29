# Release blockers and exact continuation

## Continuation, 29 October 2026 — client address trust (owner request)

Commits `57e56058` (fix) and `bf067ce2` (governance). Nothing was deployed; production still runs `9865a3d1`.

- **Problem.** Rate limits, the IP stored with security events, and the Paystack webhook IP allowlist all took the first `X-Forwarded-For` value, which the client chooses. Railway's public networking specification says its edge sets `X-Real-IP` to the client's remote address, and does not mention setting `X-Forwarded-For`. The production domain resolves directly to Railway's edge, with no CDN in front.
- **Fix (CX-SEC-02, threat TM-42).** `core/client_ip.py` trusts, in order:
  1. an address signed by our web proxy (HMAC-SHA256 with `SIGNALRANK_CLIENT_IP_SECRET`, 5-minute window);
  2. `X-Real-IP` on Railway (override with `TRUSTED_CLIENT_IP_HEADER`);
  3. the socket peer.

  The first `X-Forwarded-For` value is never used. The rate limiter, security events and the Paystack allowlist all use this resolver. The Next.js proxy no longer forwards browser-supplied forwarding headers: it passes the edge-set address, signed when the secret is set.
- **Owner check after deployment.** New owner-only `GET /api/v1/platform/operator/request-identity` shows the address and source the server derived from your own request.
- **Not observed.** That the edge replaces a client-supplied `X-Real-IP` comes from Railway's documentation; production cannot be inspected without deploying. Reading the web service's variables (to learn whether the web app reaches the API privately or through the public edge) was refused by the production-read guard and not attempted another way.
- **Tests:** 14 Python and 4 frontend tests, including a signature test vector shared by both languages; 475 related Python tests pass. Full suite at `bf067ce2` (Windows 11, Python 3.13.7, owned PostgreSQL 17 migrated from empty to `0057`, `SIGNALRANK_POSTGRES_INTEGRATION_REQUIRED=1`): **4,313 passed, 1 failed, 2 skipped**; the failure is the environmental `release_provenance[isolated_metadata]` case.

## Continuation, 29 October 2026 — threat model revision, security fixes, accessibility audit (owner request)

Commits `6360f648`, `0243af1f`, `8c2c15e4` and `64e5653d` (security fixes); `6bc1f02b` (threat model); `d9d28e15` (accessibility); `28c0c39e` (governance). Nothing was deployed; production still runs `9865a3d1`.

- **Threat model (CX-SEC-01).** `docs/security/THREAT_MODEL.md` gains section 12, extending the 26 Sep model (schema `0045`) to `0057`. It covers new surfaces, trust boundaries TB-09 to TB-13 and threats TM-28 to TM-41, each with the control read in the code and its tests. Sections 1–11 are unchanged. Open items are stated as risks, not exploit steps, because the repository is public.
- **Fixed while modelling (CX-SEC-02):**
  - **Webhook address pinning:** a delivery now connects only to the address that passed validation, which closes DNS rebinding. Non-public ranges are refused, TLS is still verified against the real hostname, and connections are not reused across customers.
  - **Per-account sign-in limit:** 10 failed passwords in 15 minutes lock password sign-in, whatever the forwarded IP. Unknown emails are counted too, so the lock reveals nothing.
  - **Account email cap:** at most 5 sign-in-link and 5 reset emails per account per hour, with an identical reply when capped.
  - **Private-chat-only bot commands:** in groups, only eight public-information commands answer.
- **Supply chain and secrets (CX-SEC-06, CX-AUTH-04).** On 29 Oct, `pip-audit` on `requirements.lock` found 0 known vulnerabilities in 135 packages, and `npm audit --omit=dev` found 0. A secret-pattern scan of tracked files found only false positives.
- **Accessibility (CX-WEB-02).** New `scripts/a11y_audit.py` runs axe-core's WCAG 2.2 A/AA rules on 40 pages (public, legal, workspace), in two themes at two widths. A 320 px pass adds reflow, skip-link and visible-focus checks. Before the fixes, 128 of 140 runs failed (1,067 colour-contrast nodes, 62 name mismatches); after, 0 of 200 fail. The fixes:
  - muted-text tokens now meet at least 4.8:1 and 5.3:1;
  - the menu's accessible name starts with "Menu";
  - public pages have a skip link;
  - the legal pages' mis-encoded link name is corrected.

  Evidence: `docs/release/evidence/continuation-20261029/a11y_audit.json`. Screen readers, full keyboard journeys and real devices remain manual.
- **Tests:** 17 new Python tests (5 on real PostgreSQL) and 3 new frontend tests; 598 related Python tests pass. Full suite at `28c0c39e` (Windows 11, Python 3.13.7, owned PostgreSQL 17 migrated from empty to `0057`, `SIGNALRANK_POSTGRES_INTEGRATION_REQUIRED=1`): **4,299 passed, 1 failed, 2 skipped**; the failure is the environmental `release_provenance[isolated_metadata]` case.
- **Still open:** confirm how the hosting edge sets `X-Forwarded-For` before changing IP-keyed rate limits; an external security review (CX-SEC-07); manual accessibility checks.

## Continuation, 29 October 2026 — Telegram /watchlist and /journal (owner request)

Commits `5b2ef71a` (commands and shared services), `e09f65ce` (governance), `17c15b15` (web watchlist controls), `f591ceca` (governance). Nothing was deployed; production still runs `9865a3d1`.

- **Shared services (CX-CHAN-01, CX-PROD-03).** `services/platform/watchlists.py` and `services/platform/journal.py` now hold the SQL the web endpoints used; the web endpoints and the bot both call them, so a list or entry made in one channel appears in the other for the same canonical account. Web responses are unchanged apart from two additions: a blank watchlist name is refused (422), and each watchlist item carries its `display_symbol`.
- **`/watchlist`** (free, as on the web): list every watchlist with symbols; `add`/`remove` by symbol or exact instrument id; `new`; `delete <name> confirm`. A symbol shared by several active instruments (for example spot and perpetual) is never guessed: the candidates are listed. A mistyped symbol creates nothing; only a successful add creates the default list.
- **`/journal`** (free): the latest five entries; `add <text> #tags`; `delete <id> confirm` with a short id (six or more characters, own entries only).
- Both commands answer only in a private chat, so journal content is never posted to a group.
- **Web watchlists** now show symbols, remove one instrument at a time, and delete a list after a second click. Before this, the web had neither control even though the API offered both. A presentation test that pinned "no DELETE calls" now allows exactly those two routes.
- **Parity matrix:** the watchlists and journal sections now map to commands. The generator now lets a singular command match its plural route, which adds 10 route matches; each was reviewed and is a true match.
- **Verified** end to end on the owned local stack: a list and an entry made through the real bot handlers appeared on the web pages, and an entry, a removal and a deletion made on the web were reflected by the bot. Real Telegram delivery was not exercised: no bot token was used locally.
- **Known limit (pre-existing):** Telegram's command menu holds at most 100 commands per scope. Every tier's menu includes both new commands (free 40 of 40, admin 98 of 98), but the owner menu shows 100 of 123 catalogue entries (previously 100 of 121), so the last 23 owner and admin entries are missing from it. `/help` still lists all of them.
- **Tests:** 9 new Python tests (7 on real PostgreSQL) and 3 new frontend tests; 358 related Python tests pass. Full suite at `e09f65ce`: 4,282 passed, 1 failed, 2 skipped. Full suite at the final code commit `f591ceca` (Windows 11, Python 3.13.7, owned PostgreSQL 17 migrated from empty to `0057`, `SIGNALRANK_POSTGRES_INTEGRATION_REQUIRED=1`): **4,282 passed, 1 failed, 2 skipped**; the failure is the environmental `release_provenance[isolated_metadata]` case.

## Continuation, 29 October 2026 — engine reliability: bounded database calls, owner alerts, owner screens

Commits `b0bf1c78` (timeouts), `3bfda44a` (owner alerts), `510dd352` (owner screens), `86cd8c6d` (docstring correction), `82c35b66` (governance). Nothing was deployed; production still runs `9865a3d1`. No financial permission changed.

- **Bounded database calls (CX-Q-05).** The five `run_sync` database calls in the engine loop that had no timeout (decision log, ML rejection record, ML prediction log, exposure check, notification fan-out) now carry `ENGINE_DB_CALL_TIMEOUT_SECONDS` (default 10 s, clamped to 1–120 s; the fan-out has a 45 s outer bound). The exposure check refuses the trade on a timeout. `run_sync` ignored its timeout when background threads were disabled; fixed. A source test fails if an unbounded call is added. *Correction:* the 28 Oct sections said thirteen calls were unbounded; the count was five, plus one fallback reached only when the async runner cannot be imported.
- **Owner alerts (CX-OBS-04).** Telegram alerts to `OWNER_IDS`, de-duplicated across processes, each ending with a runbook line: `engine_stalled` (sent by the stall watchdog before a dedicated engine exits); `engine_silent` (a worker loop, `OWNER_ALERTS_ENABLED` default on, every `OWNER_ALERTS_INTERVAL_SECONDS`=120, when the engine heartbeat is missing, stalled or older than `OWNER_ALERT_ENGINE_SILENT_SECONDS`=900); `queue_age` (oldest undelivered `event_outbox` row or Telegram update older than `OWNER_ALERT_QUEUE_AGE_SECONDS`=300); the existing `provider_outage` alert now carries its runbook. The queue-age reads are read-only and never create a stream or group. Delivery to real Telegram was not exercised.
- **Owner web screens (CX-RISK-04, CX-USER-02, CX-COST-01, CX-ADMIN-01).** Operations gains scoped kill switches (engage with a reason and the typed phrase `ENGAGE`, two-step release, audit trail), account-merge review (read-only preview; owner-only apply needing a tick and the exact merge id) and AI spend (budgets, spend by provider, workload, model and user). The backend still enforces owner authority, confirmation and a recent sign-in. Exercised end to end on the owned local stack with a synthetic owner: a switch engaged and released, a merge refused for a wrong id and completed for the right one (two watchlists, a journal entry and the Telegram identity moved), spend shown from three ledger calls; no horizontal overflow at 375 px.
- **Tests.** 5 timeout tests, 10 alert tests (1 on real PostgreSQL), 4 frontend contract tests; 338 related Python tests pass; frontend 71 transport and 38 presentation tests, `tsc` and `eslint` clean. Full Python suite at `82c35b66` (Windows 11, Python 3.13.7, owned PostgreSQL 17 migrated from empty to `0057`, `SIGNALRANK_POSTGRES_INTEGRATION_REQUIRED=1`): **4,273 passed, 1 failed, 2 skipped**; the failure is the environmental `release_provenance[isolated_metadata]` case seen in earlier runs.
- **Still blocked on the owner:** `PROMOTE_TO_PRODUCTION` (migrations `0054`–`0057`), provider keys and plans, a staging environment, GitHub Actions billing.

## Continuation, 28 October 2026 — shadow evidence for the expectancy gate (owner decision)

Commits `136290b8` (feature), `4ad62330` (schema head `0057_expectancy_shadow_index`), `698a0191` (promotion plan). The owner chose to build shadow evidence and keep `EXPECTANCY_HARD_BLOCK_ENABLED` on. Nothing was deployed.

- Candidates refused only for `expectancy_unavailable` are recorded once per setup as `decision_log` rows with `layer='expectancy'` (de-duplicated 24 h; `EXPECTANCY_SHADOW_RECORDING_ENABLED`, default on).
- A second shadow tracker (`layer='expectancy'`, own cursor and health key) follows them to stop or final target and stores realized R; ambiguous bars count as −1 R; it writes no ML shadow predictions or metrics.
- With `EXPECTANCY_SHADOW_BOOTSTRAP_ENABLED=1` (default off) the gate may use that evidence only with at least twice the live minimum sample (20) and only if the lower 95% bound of expectancy after a 0.05 R cost haircut is at least `EXPECTANCY_MIN` (0.15 R); the gate sees that bound, never the mean.
- Migration `0057_expectancy_shadow_index`: concurrent, validated partial index; `EXPLAIN` on a 50,000-row table shows index scans for both the tracker and the evidence query; upgrade/downgrade/upgrade passed.
- Tests: 8 new (2 on real PostgreSQL); 207 related tests pass. Full Python suite at `698a0191` (Windows 11, Python 3.13.7, owned PostgreSQL 17 migrated from empty to `0057`, `SIGNALRANK_POSTGRES_INTEGRATION_REQUIRED=1`): **4,258 passed, 2 failed, 2 skipped**; failures are V7 governance freshness (regenerated next) and the environmental `release_provenance[isolated_metadata]` case.
- Expected timeline after promotion: shadow trades accumulate while the engine runs; with the flag on, the first asset can qualify only after 20 tracked outcomes with a strongly positive lower bound. Until then the gate stays shut, by design.

## Continuation, 28 October 2026 — third pass: signal blockers, AI cost ledger, parity, data providers

Branch `feat/frontend-rebuild-and-stage1-hardening`, commits `8495d912` … `42f212a2` after `f3dd85c7`. Stage 1 and release remain NO-GO. Railway was read only except the owner-approved engine restart recorded above; nothing was deployed or migrated in production.

- **Crypto signals are blocked by an expectancy lockout (finding, not changed).** Production sets `EXPECTANCY_HARD_BLOCK_ENABLED`; `live_expectancy` is only populated from at least `EXPECTANCY_MIN_SAMPLE` (10) proof-backed delivered outcomes in 30 days. With no deliveries since early October, every candidate is refused with `risk/expectancy_unavailable` and the gate can never reopen by itself. Shadow tracking covers only ML-layer rejections, so no counterfactual evidence accumulates either. Resolving it is an owner decision (see the blockers list); no gate or threshold was changed.
- **Data providers (`8495d912`).** Connectors returned `[]` for every failure and logged the cause only at debug level, so production showed `insufficient_candles candles=0` for all FX/index/commodity requests. They now record the cause (`api_key_missing`, `rate_limit_cooldown_active`, `http_NNN`, `empty_response`, ...), which the fetcher appends to the failure reason, warned once per window. Defects fixed: Polygon received raw platform symbols instead of `I:`/`C:`/`X:` tickers; yfinance asked Yahoo for `BRENT` (now `BZ=F`), had no index mapping, and builds 4h bars from UTC-aligned 1h bars. 29 tests.
- **AI cost and usage ledger (CX-COST-01, CX-AI-06; `ab68f97b`).** Migration `0056_ai_usage_ledger` (append-only tables by trigger); every OpenAI/Gemini call reserves worst-case cost before the call and settles after; budgets from the environment are enforced under an advisory lock and an exhausted budget skips the AI step (deterministic review applies); without budgets it records only. `/operator/ai-spend` summarises spend. 16 tests on real PostgreSQL; `0053 → 0056 → 0053 → 0056` rehearsed on seeded data with `auto_renew` values unchanged. Every `EXPECTED_ALEMBIC_HEAD` pin moved to `0056_ai_usage_ledger` (`234c6231`).
- **Web/Telegram parity (CX-CHAN-01, CX-TG-01; `a3cd967d`).** Quality, privacy, feedback and operator authority are shared services used by the web API and the bot; `/quality`, `/privacy`, `/feedback` and `/account_merges` added or extended in Telegram; mutating owner controls stay web-only. `TELEGRAM_WEB_PARITY_MATRIX.md` is generated from the code (`scripts/build_parity_matrix.py`); remaining gaps it names include watchlists and the journal. 33 tests.
- **Order-block ABC strategy (`267a3339`, `42f212a2`).** Closed-bar-only evaluation, stop beyond every extreme since C, day-correct 4h dealing range and daily-to-4h mapping fixed (16 tests). A causal replay backtest harness was added (5 tests) but not run on real data: Binance, Coinbase, Bybit, KuCoin, OKX, Kraken, Gate.io and Dukascopy were unreachable from this machine (DNS/network filtering). The strategy stays disabled.
- **Work from the three sessions that stopped at their usage limit** (AI ledger, backtest, parity) was found uncommitted in this worktree, reviewed, completed where needed (one raw-exception Telegram reply fixed, missing parity matrix written, head pins and one source-pinned test updated) and committed separately.
- Full Python suite at `42f212a2` (Windows 11, Python 3.13.7, owned PostgreSQL 17 migrated from empty to `0056`, `SIGNALRANK_POSTGRES_INTEGRATION_REQUIRED=1`): **4,250 passed, 2 failed, 2 skipped**. Failures: V7 governance freshness (artifacts regenerated in the following commit) and the environmental `release_provenance[isolated_metadata]` case (`alembic` only in user site-packages, excluded by `python -I`).

## Continuation, 28 October 2026 — engine stall root cause, owner strategy, dependency verification

Branch `feat/frontend-rebuild-and-stage1-hardening`, commits `6c14af7d` and `5b7eb4c5` after `dce7bd8c`. Stage 1 and release remain NO-GO. Railway was read only (environment status, deployment lists and logs); nothing was deployed, restarted, migrated or reconfigured.

- **Production engine root cause (CX-Q-05, CX-FACT-06).** `striking-optimism` logged its last pipeline step at 2026-10-22 08:08:30 UTC (`PENGUUSDT`), immediately after `Postgres-R8Lr` was redeployed at 08:07:47 and the engine's connections broke at 08:08:35; it has logged nothing since, yet Railway reports it Online with one running replica and no failures. Thirteen database calls in the loop use `run_sync` without a timeout. *(Corrected 29 Oct: five calls, not thirteen; all bounded since `b0bf1c78`.)* Fix: an engine stall watchdog that logs the stuck call's stack, publishes a not-ready `stalled` heartbeat and, for a dedicated engine role, exits with code 70 so the `ON_FAILURE` policy restarts it (`5b7eb4c5`, 7 tests). Not deployed: the running engine stays stalled until it is restarted.
- **Engine restarted at the owner's request** (28 Oct, ~05:40 UTC; `striking-optimism` restarted in place on deployment `d6423329`, still `9865a3d1`; no deploy, migration or configuration change). Production `/readyz` became `ready` with every check passing for the first time since the stall; cycles 5→11 in about five minutes with heartbeat age under 60 s. Signals remain 0: crypto candidates (18–38 per batch, scores up to 81) are refused by the risk gate with `risk/expectancy_unavailable`, and FX/index/commodity assets have no candles from their providers. Gates unchanged; these need an owner decision (expectancy bootstrap) and provider fixes.
- **Other signal-drought causes seen in the same logs (not changed):** several FX, index and commodity providers returned 0 candles (Tiingo, Twelve Data, Polygon, yfinance), and BTCUSDT candidates were refused with `risk/expectancy_unavailable`.
- **PR #202 was not deployed.** Railway created no deployment for `4f4f6d33`; every application service still runs `9865a3d1` (12 Oct). Earlier pushes show automatic deployments SKIPPED and later deployed manually.
- **Owner strategy videos.** The 23 Jun 2026 (XAUUSD) and 6 Aug 2026 (USDCAD) recordings were reviewed from 67 extracted frames and a machine transcript (the first recording's audio is unusable). Implemented as `strategies/zone_rejection.py` (`Order Block ABC (Top-Down)`, `order-block-abc-v1`): 1d/4h order block, premium/discount filter on the 1d range, 4h break of structure, 15m (else 5m) ABC where C takes A and the latest closed bar is the first close through B, target the nearer of the 50% equilibrium and the 4h liquidity, minimum 2R. Group `zones`, 5m/15m capability, disabled unless `ZONE_REJECTION_STRATEGY_ENABLED` is set (`6c14af7d`, 11 tests). No backtest or shadow evidence yet; enabling needs owner approval.
- **Full Python suite with the upgraded dependencies** at `fa223df4` (Python 3.12 venv from `requirements.lock`, owned PostgreSQL 17 migrated from empty, `SIGNALRANK_POSTGRES_INTEGRATION_REQUIRED=1`): **4,145 passed, 1 failed, 2 skipped**. The failure, `test_provider_certification_boundaries.py::test_positive_infinity_cannot_hang_any_timestamp_normalizer`, is a 15 s subprocess deadline hit by cold imports in the new venv; it passes on re-run in about 4 s (twice).

## Continuation, 27–28 October 2026 — second pass: engine diagnostics, risk, identity merge, security

Branch `feat/frontend-rebuild-and-stage1-hardening`, commits `21e5c509` … `f95f9785`. Stage 1 and release remain NO-GO; nothing was merged, deployed or migrated against any shared system, and no financial permission changed. Environment for all evidence below: Windows 11, Python 3.13.7, an owned PostgreSQL 17 cluster on `127.0.0.1:55434` created for this session, Node 22.19 with npm 11.17.0. Not CI, staging or production.

- **Engine stall diagnostics (P0).** Five early cycle exits (circuit breaker active or failing closed, no assets, off-market throttle, empty queue) wrote no `engine:last_cycle`, so a live engine skipping every cycle looked stopped. They now publish `status: skipped` with the reason; readiness still treats `skipped` as not ready and names the reason (`2288ce6e`). The production root cause still needs Railway logs.
- **Runtime identity (CX-OBS-03).** `/version` reports the code's Alembic head and a UTC build stamp written by the Nixpacks build phase (`bd257421`, `131224e7`). `image_digest` stays `unknown` under Nixpacks.
- **Migration rehearsal.** `0053 → 0055 → 0053 → 0055` with plain Alembic and `0053 → 0055` through `scripts/controlled_migrate.py`, on 5,000 users and 200,000 decision rows: existing `auto_renew` values unchanged, index valid, downgrade clean. Found that the guarded migration also needs `PRODUCTION_DB_VOLUME_SIZE_MB` and a volume observation under one hour old; the promotion plan now lists it. Evidence: `evidence/continuation-20261027/migration_rehearsal_0053_0055.json`.
- **Risk.** Audited strategy/instrument/asset-class kill switches enforced at the MT5 and Bybit chokepoints, fail closed (`31770c17`). Real-PostgreSQL race: 12 simultaneous reservations against a limit of 3 approve exactly 3; found and fixed every quota refusal being reported as `execution_quota_unavailable` (`41e16c3b`). `engine/correlation_guard.py` and `core/risk_authority.py` are not wired into runtime.
- **Focused universe in ML training** (`fdcfefe0`) and **per-strategy/instrument/timeframe/layer rejection breakdowns** on `/quality` and the web Quality view (`6cc5f94c`, `b51d3db7`).
- **Telegram ↔ web account merge.** A web account linking a Telegram identity with existing bot history stopped at `merge_review` forever. Reviewed merges can now be previewed and completed (owner endpoints, `python -m tools.complete_account_merge`) in one transaction: rows referencing the archived account move only when no unique index collides and owned parent rows move with them; nothing is deleted; credentials and sessions never move; paid tier and the renewing subscription follow the person (`3febf802`). 5 real-PostgreSQL tests.
- **Security.** Next.js `16.3.8 → 16.4.2` (critical unauthenticated RCE advisories GHSA-2464-fhr4-w9xw, GHSA-673q-mjm6-r5xr) and zod; `npm audit`: 0 vulnerabilities (`630163db`). pip-audit of `requirements.lock`: 49 advisories in aiohttp, certifi, opentelemetry-api and Pillow; bumped to aiohttp 3.14.5, certifi 2026.10.19, OpenTelemetry 1.45.1/0.66b1, Pillow 13.0.0, respecting the 7-day release-age rule (`242eefc3`). Baseline `nosniff`, `no-store` and HTTPS-only HSTS on direct API responses; HSTS on the web app (`eaa11d9d`).
- **Audit.** Global and scoped kill-switch changes now write `security_events` rows, best effort so a switch never fails on audit (`f95f9785`).
- **Web.** Production build run locally against the local API. At 320 px the public Menu button was off-screen (fixed, regression test). A window with zero quality decisions now says the engine most likely did not run. Basic accessibility sweep clean on Settings, Signals and Login.
- **Tests.** Full Python suite at `eaa11d9d` on real PostgreSQL 17 (database migrated from empty to `0055`, `SIGNALRANK_POSTGRES_INTEGRATION_REQUIRED=1`): **4,138 passed, 4 failed, 0 skipped**. Failures: V7 governance freshness (artifacts not yet regenerated at that commit; regenerated before push), `release_provenance[isolated_metadata]` (environmental: `alembic` only in user site-packages, excluded by `python -I`), and two host-timezone privacy cases that call POSIX-only `time.tzset` (now skipped where unavailable, `4d8d596d`). Frontend at `630163db`: tsc, eslint, `next build` and 108 node tests pass.
- **Production promotion** was requested again; not executed. It still needs the owner phrase `PROMOTE_TO_PRODUCTION`, Railway access for backup and `EXPECTED_RELEASE_COMMIT` on every service, and the guarded migration (plan updated with the volume gate). The promoted code would now also change the Nixpacks build phase and Python/Node dependency versions listed above.

## Continuation, 27 October 2026 — runtime schema identity

Branch `feat/frontend-rebuild-and-stage1-hardening` (from `5f848d96`; code commit `bd257421`). Stage 1 and release remain NO-GO; nothing was merged, deployed or migrated, and no financial permission changed.

- CX-OBS-03 (partial fix): `/version` now reports the code's single Alembic head when `EXPECTED_SCHEMA_HEAD` is unset, resolved independently of the working directory, instead of `unknown`. An explicit `EXPECTED_SCHEMA_HEAD` still wins. `build_timestamp` and `image_digest` still depend on build-provided variables and stay `unknown` until the build sets them. Test: `tests/test_version_schema_head_20261027.py` (3 passed locally; the first case fails on the previous code). Not deployed, so production still reports `unknown` until an authorized promotion.
- Production promotion was requested in chat on 27 Oct without the `PROMOTE_TO_PRODUCTION` phrase or the prerequisites in [PRODUCTION_PROMOTION_PLAN_20261024.md](PRODUCTION_PROMOTION_PLAN_20261024.md) (backup evidence, `EXPECTED_RELEASE_COMMIT` on every service, guarded `0054`/`0055` migration). Not executed.

## Continuation, 24 October 2026 — frontend rebuild, live readiness finding, independent audit

Branch `feat/frontend-rebuild-and-stage1-hardening` (from `393f3d88`; commits `7946fa25`, `840abd90`, `801780d4`, `7a63d5ac`, `8a7d3e3b` and this documentation commit). Stage 1 and release remain NO-GO; nothing was merged, deployed or migrated, and no financial permission changed.

- Web frontend rebuilt on a new design system; billing (server-priced Paystack checkout, verified confirmation, auto-renew cancel, refund review) and signal feedback wired to existing APIs. Local evidence: tsc, eslint, `next build`, 98 node tests at the time of commit; 61/61 pre-rebuild API calls and 11/11 routes retained (`frontend/scripts/api-baseline.test.mjs`).
- Focused-universe admission now guards both signal persistence paths and the MT5/Bybit execution chokepoints (no-op unless enabled in staging). HTTP 451 classified as `REGION_RESTRICTED`; Binance region blocks logged and backed off.
- Live read-only `/readyz` (deployed `9865a3d1`) returns 503: only `engine_runtime` fails — the `engine:last_cycle` heartbeat is absent, so the production engine is not cycling (Engine Pulse: 0 signals in window). Probe now reports `engine_heartbeat_missing`. Root cause needs Railway logs (blocked: access). Production DB is at `0053`; repository head `0055`.
- New owner source `message.txt` (SHA-256 `b78374d0…`) consolidated privately into 287 requirement IDs; hashes and anchors only in `evidence/continuation-20261024/source_intake.json`.
- Full Python suite at clean commit `e9b2b368` on a local PostgreSQL 16.2 database migrated from empty to `0055`: **4,098 passed, 0 failed, 1 skipped** (pyarrow not installed); multi-user isolation suite 5/5. Three pre-existing test portability/isolation defects fixed. Local only; GitHub Actions remains billing-locked. Limits in the audit §8.

Full details, classifications and information gaps: [INDEPENDENT_ACCEPTANCE_AUDIT_20261024.md](INDEPENDENT_ACCEPTANCE_AUDIT_20261024.md).

## Stage 0 safe local Git and historical forensics, 22–23 October 2026

The exact observed source is e01e7c41f49a3e35335b00edc2de97367aa2dade. Evidence: [Stage 0 forensics index](evidence/continuation-20261022/index.json). Release remains **NO-GO**.

Stage 0 forensics passed all local checks. Branch audit across 247 refs confirms 118 unique commits across 28 divergent refs, with 0 missing and 0 moved heads compared to `branch_dispositions.json`. Migration head is single: `0055_user_renewal_default`. 18 worktrees discovered; 17 clean, 1 dirty (`.pytest-tmp/release-ci-closure-20261007`) preserved untouched. Draft PR #201 remains OPEN under active ruleset 24410166; CI is blocked external due to GitHub billing lock. Live public routes (`https://www.signalrank.criloxsolutions.com`) confirm `/login` and `/pricing` 404, while `/` serves 200 JSON and `/app` serves 200 HTML workstation. Railway CLI session is expired, blocking fresh authenticated control plane re-verification. All 5 release governance checks pass with 0 drift.


## Correction verification closed at local scope, 18 October 2026

The exact tested source is 393f3d88d6018d01c3f04234cc9c44b23a5de8fc. Evidence: [correction index](evidence/continuation-20261018/correction-393f3d88/index.json). The receipt-overwrite defect and strict HTML parse failures are locally resolved: 4,080 clean full-suite passes, a complete zero-finding/zero-error OpenGrep scan, and a passing legacy browser drill with owned-resource cleanup.

Release remains **NO-GO**. The mobile dependency audit still reports four high-severity rows in the Expo/node-forge chain. Stage 1 source reconciliation remains incomplete: 13 reviewed dispositions and 26,874 unresolved applicability/acceptance rows. Focused-universe provider qualification and cross-path enforcement are unfinished local work.

Hosted CI remains unavailable/failed at the prior remote head; independent review, isolated staging, broker-demo/provider/payment/Telegram evidence, native device coverage, restore/rollback and soak gates remain unsatisfied. No deployment or financial permission change is authorized.


## Updated local acceptance, 18 October 2026

The exact tested source is 2ee0a918d915549f7f5ce59d59f0a8a07d2202a9. Evidence: [frozen run index](evidence/continuation-20261018/frozen-2ee0a918/index.json). Stage 1 and release remain NO-GO.

The stale generated-governance failure is resolved: full local system and both browser modes pass. The strict scan revealed two HTML parse failures; escaped text is awaiting a frozen rescan. The evidence wrapper correction also awaits frozen regression acceptance. Mobile dependency audit remains red.

Source reconciliation and focused-universe cross-path/provider qualification remain executable local work, not external blockers. Nine additional source-truth seeds were reviewed with explicit gaps (13 total); remaining applicability and acceptance are unresolved. The fresh branch snapshot has 247 refs and 118 unique unmatched commits requiring comparison with prior dispositions, not automatic merging.

GitHub requires independent last-push approval plus manifest/release-certification; hosted Actions remain failed at the previously observed head. Railway still has only a production environment. Dedicated staging, actual demo/provider/payment/Telegram evidence, native devices, restore/rollback and soak acceptance remain open. No deployment or financial permission change is authorized by local PASS.

## Verification continuation, 18 October 2026

Clean unchanged 7c3f7e0f completed the full local system run: 4,075 passed,
one failed, zero skipped. The sole failure is the generated V7 governance
inventory, which was produced before the final retained evidence and register
updates. The failure is retained in evidence/continuation-20261018/index.json;
no runtime behavior is waived by identifying the generator-order error.

On that same commit, all five local manifest gates, 63 frontend tests, 53 mobile
tests, frontend lint, mobile typecheck, Android/iOS JS exports and the real Next
browser drill passed. The browser drill used synthetic accounts and an owned
migrated PostgreSQL database; server/database/key cleanup succeeded. These are
local checks, not native-device, provider, broker, financial or staging approval.
Stage 1 and the overall release remain NO-GO.

Generation order for the correction: retain/stage evidence logs first, update
baseline/docs, build_release_inventory, crosschat_intake, then build_v7_governance.
Check all three without writing before freezing. Do not add evidence after the
final governance generation without regenerating it. Run the full suite and
remaining browser/security checks from that exact unchanged correction commit.

Verification follow-up: 5f7ae60c passed the five local manifest gates, 63 frontend
and 53 mobile tests, but its full run was interrupted after an Android export
rewrote tracked legacy build artifacts. Those generated files were restored;
future exports target ignored artifacts. Missing Chromium is being installed.
A synthetic probe also exposed missing receipt metadata validation in the new
intake validator; environment, command, timestamp and scope are now mandatory,
with four negative regressions. No requirement was promoted to VERIFIED.
The next frozen commit must supply fresh full-suite acceptance.

## Cross-chat intake checkpoint, 17 October 2026

ST1-SOURCES is still FAILED. Both full DOCX bodies and text exports match all
14,226 ledger rows; all 1,586 heading entries and 242 seeds were ingested.
Individual acceptance review remains incomplete, including repository child
clauses retained through the existing register. See source_coverage.json for
exact reconciled counts, not a claim that all rows are product features.

The first new diagnostic run recorded 70 passed / one database setup error
because the owned localhost test cluster was stopped. After restarting only
that cluster, the same checks recorded 71 passed with zero skips. Both are
modified-worktree diagnostics, not frozen-release acceptance. The clean a23e088f
local manifest failed its SDK gate because it was invoked with the runtime
interpreter; use the existing separate SDK venv for that group. Preserve the
failure and run the full exact-commit suite after freezing this source.

Missing blueprint_modules.csv and unsupplied chats are inaccessible-source
items. The many unfinished code/acceptance reviews remain local work, not external
blockers. Production, provider, broker-demo, isolated staging/soak, financial,
independent review and required hosted-check gates remain unclosed.

## Current continuation findings, 16 October 2026

Stage 1 remains FAILED. The 51d2f59e focused baseline passed 32 executed tests.
Repairs subsequently passed 71 diagnostic tests in a modified worktree, including
real SQL against a newly migrated owned localhost database. These diagnostics
are not frozen-commit acceptance; see the current evidence section.

Configuration overrides previously accepted duplicate aliases, Boolean schema
versions and malformed symbols. Environment-label precedence could mask production.
The DB query admitted metadata-only records. These defects are repaired locally;
strict scan reads now require recent analysis-readiness, matching classification,
provider candle/quote capabilities and non-delisted mappings. Fresh registry
timestamps do not prove candle freshness, entitlement, spread or liquidity.

Remaining local focused work: actual provider-bound qualification and refresh,
bounded retention/hysteresis, owner overrides and reasons, other signal and
learning paths, web/Telegram presentation, and independent new-order enforcement.
Do not label these gaps external or start the redesign phase while Stage 1 is open.

Fresh read-only control-plane evidence confirms only a production Railway
environment, API at 9865a3d1 and public web at f026bd16, and a crashed historical
soak observer. PR #201 remains draft with required independent last-push approval;
manifest/release-certification jobs still cannot start because of GitHub billing.
No protected check was bypassed. See evidence/continuation-20261016/.

Current Stage 1 acceptance: **FAILED — not complete**. Local integration,
foundation fixes and the complete 3,984-test suite now pass on c411ebbb. Remaining
source-specific acceptance review is local work, not an external blocker.
Independent review and hosted checks remain external gates. This ledger does
not declare Stage 1 complete or begin the next stage.

| ID | Status | Owner/component | Evidence / next action |
| --- | --- | --- | --- |
| ST1-TEST | VERIFIED | Engineering / local verification | Clean unchanged c411ebbb: 3,984 passed, zero failed/errors/skipped; all 32 orchestration steps pass. Both local browser modes and Android/iOS exports pass. See COMPLETION_EVIDENCE.md and retained receipts for scope. This verifies the local suite, not product-wide acceptance. |
| ST1-FOCUSED-UNIVERSE | FAILED | Stage 1 / focused-universe scanner | 10 core + up to 5 optional candidate contract is preserved. `configs/focused_universe.json`, `core/focused_universe.py` and `engine/core.py` now offer classification-checked, capped, no-fallback scan selection behind `FOCUSED_UNIVERSE_ENABLED=0` by default. Enabled behavior explicitly rejects non-staging environments. Tests were added but could not execute in hosted CI (zero job steps). Qualification scoring, independent broker/order-entry boundaries, other signal paths, web, Telegram, all market/provider certifications, local exact-head test execution and production rollout remain **unverified/not complete**. Existing positions and live permissions unchanged. |
| ST1-SOURCES | FAILED | Architecture and component owners | The inventory retains current and historical clauses, but many have no source-specific implementation/acceptance disposition. Resolve each applicable clause with code and meaningful tests; preserve superseded/optional context explicitly. See the generated matrix, not old PASS reports. |
| ST1-INTEGRATION | IMPLEMENTED | Repository maintainers | Blueprint ancestry, legal merge and recovered provider/ML fixes are committed, with browser attribution and fixture repairs. Complete the draft PR handoff; main still requires independent last-push approval and manifest/release-certification checks. |
| EXT-CI | BLOCKED_EXTERNAL | GitHub billing/account owner | `evidence/github-latest-annotations.json`: jobs never started because the account is locked due to a billing issue. Restore GitHub Actions availability and rerun required checks on the proposed SHA. |
| EXT-MOBILE-SECURITY | BLOCKED_EXTERNAL | Expo/node-forge maintainers and release owner | Locked npm audit returns four high rows from GHSA-86w9-cpqp-85rv; the official advisory lists no patched version. Await a trusted patch or separately review a supported replacement, then reinstall, audit, export and test devices. Do not suppress it or downgrade Expo to the audit's incompatible suggestion. |
| EXT-RUNTIME | BLOCKED_EXTERNAL | Deployment operator | GitHub deployment metadata and public GET are available; no authenticated current runtime/schema/configuration audit or promotion occurred. Capture exact deployment SHA/image/schema/configuration and staging evidence. |
| GAP-PUBLIC-ROUTES | FAILED | Deployment/frontend integration | October 15 public GET: `/` serves service JSON, `/login` is 404, `/app` serves retained HTML. The new public/account site is not proven to be serving this domain. Complete isolated cutover acceptance and a separately reviewed deployment; do not infer public-site readiness from `/healthz`. |
| EXT-PROVIDERS | BLOCKED_EXTERNAL | Data operations | Certify each enabled provider, market class, entitlement and timeframe in the actual environment, with source timestamps and outage evidence. Local mock certification is insufficient. |
| EXT-BROKERS | BLOCKED_EXTERNAL | Authorized broker/account operator | Supply dedicated demo accounts and scoped authority; run full per-adapter lifecycle/reconciliation tests. Live authorization is outside this task and remains unchanged. |
| EXT-JOURNEYS | BLOCKED_EXTERNAL | Product/operations | Dedicated staging Telegram, SMTP, APNs/FCM, mobile signing and test-mode billing evidence required. Device and external round trips are not replaced by TypeScript or source tests. |
| EXT-RECOVERY | BLOCKED_EXTERNAL | Infrastructure operator | Retain actual isolated backup restoration, RPO/RTO, alerting, restart reconciliation and sustained exact-SHA soak evidence. |
| EXT-POLICY | BLOCKED_EXTERNAL | Product/legal owner | Recovered policy text and consent controls require accountable content/jurisdiction review. No legal certification is claimed. |
| GAP-BROKERS | NOT_IMPLEMENTED | Broker adapters | Complete required execution adapters beyond the catalogue's ready mt4/mt5/bybit entries; connection-only/integration labels do not satisfy execution requirements. |
| GAP-RESEARCH | FAILED | Quant/research | Finish retained research/master clauses, including independent causal/out-of-sample/forward acceptance; current immutable storage safeguards alone do not prove statistical validity. |
| GAP-FULFILLMENT | FAILED | Billing/support/privacy | Demonstrate manual refund/privacy request completion and retention controls; ticket creation is only intake. |

The next local action is ST1-SOURCES: reconcile source-specific dispositions,
beginning with the 991 formal specification/master entries and 19 V7 mappings,
then resolve historical conflicts against those authorities. Their IDs, text,
hashes and known mappings are preserved in requirements.json. They are not 9,916
independent product features: source sections, historical versions and PR context
overlap. Associate each applicable clause with active code, explicit gaps and
scoped evidence; retain superseded/optional rationale. Do not rerun the passed
runtime suite merely to update documentation; check subsequent changes according
to their scope. Never weaken risk, calibration, ownership or evidence thresholds.

No production migration, configuration change, customer data write, billing
operation, broker order or real-money permission change is authorized by this
handoff. External blockers do not justify marking unrelated local work complete.


## Latest continuation (16 October 2026)

- Retry of GitHub Actions run `38932482649` generated attempt 2; jobs
  failed before executing any steps. Later run `38943080448` at
  `e908bfba959b3d35fdeccfae6af14221059b1fff` also reports failed
  manifest/release-certification jobs with zero steps. No successful hosted
  coverage or release approval can be inferred.
- A read-only fetch of the deployed hostname resolved `/` to `/app`, which
  displayed a session-restoration workstation. `/login` returned HTTP 404.
  This is evidence of the routing gap, not authenticated/browser E2E certification.
- Source-review work, exact-head Python/JS suites, externally provisioned
  broker-demo and staging Telegram tests, full Next public-site cutover,
  backup restoration and rolling/soak verification remain open. Do not merge
  draft PR #201 or deploy trading changes based on local/static review alone.


## Connected Railway runtime reconnaissance — 16 October 2026

Read-only connector inspection of Railway project `trading-bot-account2`
(production environment) found:

- API `SignalRankAI` and analytics worker deployed at
  `9865a3d1bcee632bfd9347e50d5de34d355225d9`, from
  `fix/provider-discovery-readiness-20260923`.
- `SignalRankAI-Public-Web` deployed at
  `f026bd16d90c0fbde2292e326525524fd75966ea`, from
  `fix/release-recovery-20261008`. The web and backend are not on
  one release SHA and neither runs the Stage 1 PR head.
- The connected project has one Railway environment, `production`, and
  no dedicated Railway staging environment. No staging soak for PR #201
  can be inferred.
- `signalrank-readonly-soak-20261012` is marked CRASHED. Its final
  read-only sample at 2026-10-16 05:14 UTC recorded 72 hours of
  process observations but explicitly returned
  `release_soak_certified=false`,
  `aggregate_database_observation_window_24h_passed=false` and
  `financial_readiness_certified=false`.
- The final sample reported no confirmed delivery within one hour,
  no signal generation within 24 hours, and no verified broker connection.
  It observed an MT5 credentials-saved record with `verified=0`,
  `execution_enabled=0`, and broker reconciliation status UNKNOWN.
  The sample included last confirmed delivery on 2026-10-06.
  This is a scoped observer report, not a query of every customer
  account or a claim that the trading engine is permanently broken.
- Read-only inspection found the production Postgres online with two
  warnings; verify their type before modifying storage.
- Attempts to start an isolated Vercel sandbox against the PR head
  were refused with 403 FORBIDDEN by the connected Vercel project.
  Thus a fresh full-stack end-to-end test was not run in that environment.

**Release impact:** The latest PR cannot be released/merged based on these
observations. First restore independent CI, provision staging resources,
run exact-SHA environment and broker-demo certification, resolve the
reported delivery/scan drought and reconcile deployment identities.
Do not restart/modify production trading workers as an unreviewed
test workaround.
