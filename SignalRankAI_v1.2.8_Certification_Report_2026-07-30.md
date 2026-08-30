# SignalRankAI v1.2.8 Certification Report

Date: 2026-07-30  
Scope: outcome user-performance processing, proof-backed recipient selection, error-boundary correctness and direct Railway Prometheus readiness.

## Certification status

**Locally code-certified as a v1.2.7 hotfix candidate. Railway runtime proof is still required before this release can be called production-ready.**

The release does not certify unrestricted live broker auto-execution, copy trading or automatic payouts.

## Runtime evidence that triggered the hotfix

The supplied v1.2.7 Railway log showed the expected v1.2.7 release fingerprint, active provider quotes, outcome reconciliation and adaptive candle persistence. It also repeatedly showed:

`[outcome_tracker] Error updating user performance ... name 'func' is not defined`

The code inspection confirmed that the affected query depended on an SQLAlchemy symbol that was not guaranteed at module scope. The runtime diagnostics also treated the Prometheus route as absent even though it existed only through the mounted compatibility web app.

## Implemented controls

- Module-level SQLAlchemy `func` and `select` imports in the outcome tracker.
- Separate lifecycle and user-performance recipient-query failure boundaries.
- Proof-backed, case-normalised Telegram recipient selection.
- Null-safe Telegram user identifier handling.
- Direct `/metrics/prometheus` ownership in `railway_main.py`.
- A ninth production-readiness gate for direct Railway observability routes.
- Versioned v1.2.8 staging and production profiles.
- v1.2.8 static/runtime verifier and focused regression tests.
- No database migration; the sole Alembic head remains `0027_launch_paper_trading`.

## Verification results

- Tracked Python files: `749`
- Python compilation failures: `0`
- Schema audit: PASS
- Alembic revisions: `27`
- Sole migration head: `0027_launch_paper_trading`
- Production readiness: `9/9` PASS
- Architecture smoke: PASS
- Legacy DB session call sites: `0`
- Secret scan: `0` findings
- v1.2.5 compatibility verifier: PASS
- v1.2.6 compatibility verifier: PASS
- v1.2.7 compatibility verifier: PASS
- v1.2.8 verifier: PASS
- Focused v1.2.8 suite: `22` passed
- Broader selected regression suite: `92` passed, `2` deselected

## Dependency-bound local tests

The local image does not contain `python-telegram-bot` or APScheduler. Repository-wide collection therefore cannot execute modules that import Telegram callbacks, the mounted web app or Railway's scheduler. The broad selected suite excluded only two individual dependency-bound assertions after confirming that their failures were import errors rather than assertion failures.

This limitation must not be represented as runtime certification. The Railway deployment must demonstrate the endpoint and callback paths with the declared dependencies installed.

## Release decision

v1.2.8 is suitable for a controlled Railway staging deployment. It is not yet approved for public onboarding until the required runtime evidence is captured.

## Required post-deployment proof

- exact v1.2.8 boot identity and release fingerprint;
- no SQLAlchemy `func` NameError;
- proof-backed active outcome scans and persisted lifecycle transitions;
- distinct lifecycle versus recipient-query telemetry;
- HTTP 200 for `/healthz` and `/metrics/prometheus`;
- Prometheus body contains SignalRank service and request metrics;
- readiness diagnostics pass all nine checks;
- Telegram callback and outcome interactions work in the deployed environment;
- no duplicate processing or regression in v1.2.7 adaptive/outcome fixes;
- payment and execution safety boundaries remain fail-closed.
