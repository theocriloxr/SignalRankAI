# SignalRankAI Railway Runtime Fix and Deployment Diagnostics Report

Generated: 2026-07-26T17:08:26.466313+00:00

## Release status

`CODE_FIXED_AND_HERMETICALLY_VERIFIED__LIVE_RAILWAY_PROOF_PENDING`

This change set repairs the concrete failures shown in the 2026-07-26 Railway logs and adds a deployment-time evidence system. It does not label missing credentials or unperformed live tests as successful.

## Railway incident conclusions

The provider-blackout explanation was incomplete. Coinbase REST returned usable candles in the same deployment, so WebSocket failure did not need to stop market-data correctness. The observed outage was a combination of code, configuration, database admission, queue and migration problems:

- the engine called an async circuit-breaker check from a thread with no event loop;
- WebSocket ingestion started even though REST-first owner validation was required;
- free-user distribution was not fail-safe and queued deliveries for real users;
- webhook `503` responses lacked a structured rejection reason;
- critical outcome tracking was starved by DB admission and unlabelled sessions;
- scheduler calls could create repeated event-loop-specific DB engines;
- the `decision_log.created_at` migration was absent;
- waitlist job registration imported an unnecessarily heavy web module;
- proxy validation called a placeholder `example.com` URL;
- the delivery-stream backlog and dead-letter state were not visible in the audit.

## Production-code fixes

1. Engine async circuit-breaker checks now use the shared long-lived async bridge with a bounded timeout and fail-closed diagnostics.
2. The market circuit breaker uses Coinbase and OKX REST before Binance, preserving regional availability.
3. WebSocket ingestion defaults off and requires both master and crypto-specific flags.
4. Worker task registration does not start the WebSocket task when disabled.
5. Railway ignores the test-only async-runner disable flag, preventing repeated event loops and auxiliary DB engines.
6. Free distribution and delayed free-queue draining are explicit opt-in and default off.
7. A dry-run-first, non-destructive free-queue quarantine utility was added.
8. Webhook rejection responses and logs now include a specific reason and bounded queue/dispatcher diagnostics.
9. Runtime readiness verifies the Telegram secret, sole Alembic head and `decision_log.created_at`.
10. Outcome-tracker DB work has a canonical label, bounded timeout and admission-holder diagnostics.
11. DB session diagnostics now show active holders, priorities, thread/loop identity and hold duration.
12. Waitlist jobs moved to a lightweight canonical module with explicit import tracebacks.
13. Proxy validation requires an explicit feature flag and a non-placeholder URL.
14. Boot logs now include Railway commit, deployment and environment identity.
15. Railway pre-deploy runs Alembic followed by strict core diagnostics.
16. A protected endpoint exposes the latest secret-safe deployment diagnosis.
17. Redis Stream diagnostics report group lag, pending count/age, consumers, dead letters and legacy-list backlog.
18. State-side signal-dispatch queue depth is included.
19. The deployment audit inventories routes, Telegram commands/callbacks, environment safety, schemas, dependencies, credentials and optional integrations.
20. Advanced scanner inventory and opt-in execution were added for Ruff, Mypy, Pyright, Bandit, pip-audit, Semgrep, Vulture, ShellCheck, Hadolint, Coverage and mutation testing.
21. A separate `requirements-audit.txt` supports an isolated Railway certification service without bloating the live bot image.

## Automated verification

- Pytest: **733 passed, 1 skipped, 0 failed**.
- Complete system orchestrator: **True**.
- Orchestrator evidence scope: `HERMETIC_LOCAL_ONLY`.
- Alembic revisions: 21; sole head `0021_runtime_truth_hardening`.
- Environment profiles: validated.
- Architecture audit: passed.
- DB-session legacy call audit: passed with zero call sites.
- Secret scan: passed.
- Governance validation: passed.
- 100,000-user fan-out planner: passed in the orchestrator.
- Provider adapter/static certification: passed in the orchestrator.
- Repository files inventoried: 884; Python syntax errors: 0.

## Coverage evidence

The exhaustive repository-wide branch coverage run completed all tests but does **not** meet the aspirational line/branch targets:

- statements: 59994
- covered statements: 18923
- statement coverage: 31.54%
- branches: 18070
- covered branches: 3762
- branch coverage: 20.82%
- combined coverage: 29.06%

Coverage is evidence of remaining test-depth work, not a reason to mislabel the current suite. The full JSON report is included in the evidence archive.

## Local diagnostic boundaries

The local deployment audit intentionally failed or blocked live checks because no Railway secrets were present. It correctly reported missing PostgreSQL, two Redis URLs, Telegram credentials, owner identity, encryption key, API-token pepper, provider keys, Gemini, Paystack, TradingView and MetaApi instead of assuming them.

The local host's `pip check` also found an unrelated globally installed `moviepy`/`Pillow` conflict. Railway uses a clean build from `requirements.txt`; the deployment audit will independently report the clean image result.

Advanced scanners not installed in this environment are explicitly `BLOCKED`. They can be installed from `requirements-audit.txt` in the isolated certification service.

## Required live evidence after deployment

The deployment audit must still prove:

- PostgreSQL/PgBouncer connectivity and migration head;
- distinct RedisState and RedisDelivery services;
- Telegram `getMe`, exact webhook URL, secret validation, update acceptance and optional test send;
- Redis Stream lag, pending age and dead letters;
- public/sandbox provider calls for every enabled asset class;
- one exact signal through generation, storage, reservation, Telegram proof, active-message state and terminal outcome;
- restart and Redis recovery;
- TradingView signed alert flow;
- Paystack test-mode reconciliation;
- MetaApi demo quote/order/reconciliation with explicit permission;
- 24–72-hour Railway soak;
- performance reliability only after at least 100 proof-backed outcomes and adequate outcome coverage.

## Safe deployment controls

Keep these off until their independent release gates pass:

- public/free distribution;
- public payments and real payouts;
- live accounts;
- real execution;
- copy trading;
- auto trading;
- WebSocket ingestion during the first REST proof.
