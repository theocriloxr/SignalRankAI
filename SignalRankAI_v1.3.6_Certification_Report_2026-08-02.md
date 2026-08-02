# SignalRankAI v1.3.6 Certification Report

Date: 2026-08-02  
Scope: Railway process decomposition, startup ownership, role-specific database admission and deployment tooling.

## Status

**Locally code-certified for a controlled three-service Railway staging deployment. Railway runtime performance certification is still required.**

The package is not certified for unrestricted live execution, copy trading, automatic payouts or public launch.

## Verified controls

- `frontdoor` is a canonical runtime role.
- Front-door ownership remains engine/worker disabled even when stale loop flags request them.
- Decomposed topology rejects `RUN_MODE=all` and unknown-role monolith fallback.
- `railway_main:app` rejects dedicated roles using the wrong executable path.
- Dedicated engine/worker roles skip duplicate startup maintenance by default.
- Front door, engine and worker receive distinct database identities and absolute pool caps.
- Global `railway.json` is neutral; healthcheck and migration ownership are front-door specific.
- Migration head remains `0033_ml_learning_runtime`; no database migration was added.

## Validation results

- Python files compiled: `805`
- Compilation failures: `0`
- Focused decomposition/retained-release suite: `136 passed`
- Broad dependency-independent run before a pre-existing provider-registry stall: `556 passed`
- Remaining retained-release/governance group: `172 passed`
- v1.3.6 verifier: `PASS`
- Shell entrypoint syntax: `PASS`
- Front-door fake-entrypoint execution: `PASS`
- Hidden-monolith fail-closed execution: `PASS` with exit code `64`
- Production readiness checker: `12/12 PASS`
- Architecture smoke: `PASS`
- Schema audit: `PASS`, `33` revisions, sole head `0033_ml_learning_runtime`
- Secret scan: `0 findings`
- Governance validation: `24 documents PASS`
- Generated v7 governance check: `PASS`

## Local environment limitations

The analysis image does not include `python-telegram-bot` or APScheduler. Seven full-suite test modules could not collect for that reason. Those dependencies are declared by the project and were present in the supplied Railway runtime logs.

A broad run also reached a pre-existing test that performs provider-registry initialization and did not finish within the execution window. The targeted provider and runtime contract tests used for this release passed; this timeout is not represented as a successful assertion.

## Required Railway proof

1. Front door logs exact v1.3.6 version/fingerprint and `mode=frontdoor ... engine=false worker=false`.
2. Front door never logs `Engine loop task created` or `Worker loop task created`.
3. Engine logs `run_mode=engine` and performs market-data/signal cycles without Telegram scheduler startup.
4. Worker logs the worker compatibility mode and starts outcome, shadow, candle, paper and ML workers without engine startup.
5. Database `application_name` distinguishes `signalrankai/frontdoor`, `signalrankai/engine` and `signalrankai/worker`.
6. PostgreSQL active/idle connections remain within reviewed headroom under normal and peak command load.
7. `/healthz`, `/readyz` and `/metrics/prometheus` return HTTP 200 from the front door.
8. Telegram command p50/p95/p99 latency improves against the v1.3.5 monolith baseline.
9. Signal cycle duration, outcome scan duration, candle persistence and ML dataset reads progress without foreground-lane starvation.
10. Only one front-door scheduler/resend owner is active after rolling deployment overlap clears.
11. All three services remain at one replica during certification.
12. Live-risk and payout flags remain disabled in staging.

## Decision

Deploy the complete v1.3.6 archive to the staging repository, then run `split_signalrank_railway.ps1`. Do not overlay only `railway_main.py` or only environment variables on v1.3.5. Keep production and public onboarding blocked until the runtime proof above is captured.
