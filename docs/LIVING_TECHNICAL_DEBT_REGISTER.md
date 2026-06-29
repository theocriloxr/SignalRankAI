# Living Technical Debt Register

Date opened: 2026-06-29
Last updated: 2026-06-29
Owner: Engineering

This register tracks verified technical, architectural, code quality,
performance, security, UX, ML, AI prompt, testing, documentation,
infrastructure, and operational debt. No debt item should disappear silently.

## Schema

Each item must include: unique ID, title, description, affected subsystems,
root cause, severity, likelihood, impact, dependencies, proposed solution,
estimated implementation effort, regression risk, current status, verification
evidence, date opened, date resolved, and owner.

## Open And Accepted Items

| ID | Title | Description | Affected Subsystems | Root Cause | Severity | Likelihood | Impact | Dependencies | Proposed Solution | Effort | Regression Risk | Status | Verification Evidence | Date Opened | Date Resolved | Owner |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| LTD-001 | Time handling modernization | Naive `datetime.utcnow()` calls still produce deprecation warnings. | `engine`, `data`, `ml`, `web`, tests | Legacy UTC helper usage | Medium | High | Medium: future Python compatibility and timestamp ambiguity | Shared UTC helper | Replace with timezone-aware UTC helper and update tests. | Medium | Medium | Open | Full suite shows UTC deprecation warnings. | 2026-06-29 |  | Engineering |
| LTD-002 | External provider integration confidence | Provider-capable news, on-chain, Gemini, Telegram, broker, and market-data paths are mostly tested with deterministic fakes. | `data`, `services`, `engine`, `signalrank_telegram`, `payments` | CI safety and missing sandbox credentials | Medium | High | High: live production drift can escape unit tests | Provider sandbox credentials | Add opt-in live integration tests gated by env flags. | High | Low | Open | Full suite green, but live E2E is not enabled. | 2026-06-29 |  | Engineering |
| LTD-003 | Telegram E2E verification gap | Commands, callbacks, and formatters are covered by contracts, but every Telegram workflow is not exercised end-to-end. | `signalrank_telegram` | Bot API tests require sandbox token/chat | High | Medium | High: user-facing regressions | Telegram sandbox | Add `TELEGRAM_E2E_ENABLED=1` smoke suite and workflow checklist. | High | Medium | Open | `tests/test_command_contracts.py` exists; no full Bot API suite. | 2026-06-29 |  | Engineering |
| LTD-004 | Decision intelligence lifecycle integration | Structured decision records exist but are not yet wired into every signal lifecycle branch. | `engine/core.py`, `services/decision_intelligence.py`, `db` | New layer added after existing compact decision logging | Medium | High | Medium: weaker explainability coverage | Full-suite green checkpoint | Integrate `build_decision_record()` into issued, rejected, skipped, delayed, and suppressed branches. | Medium | Medium | Open | `services/decision_intelligence.py` and tests exist. | 2026-06-29 |  | Engineering |
| LTD-005 | Runtime configuration drift | Thresholds and toggles are env-driven and can diverge between local, Railway, and production. | `config.py`, `engine`, `signalrank_telegram`, deployment | Multiple env files and fallback defaults | Medium | High | Medium: inconsistent behavior | Startup diagnostics | Export sanitized startup config snapshot and compare against expected deployment profiles. | Medium | Low | Open | Multiple `.env*` templates and threshold fallbacks present. | 2026-06-29 |  | Engineering |
| LTD-006 | Outcome tracker architecture split | State-machine helpers and polling/backfill tracker coexist. | `engine/realtime_outcome_tracker.py` | Compatibility merge preserved both approaches | Medium | Medium | Medium: duplicate mental model | Shadow comparison | Run shadow comparison and decide primary tracker architecture. | Medium | Medium | Open | Realtime tracker tests pass; architecture decision pending. | 2026-06-29 |  | Engineering |
| LTD-007 | Generated/runtime inventory boundary | `.venv`, `.git`, bytecode, and caches are excluded from source audit. | repository operations | Boundary between source audit and supply-chain review | Low | High | Low: documented scope issue | Lockfile/supply-chain tooling | Treat as accepted application boundary; run separate dependency review when required. | Low | Low | Accepted | Audit report documents exclusion. | 2026-06-29 |  | Engineering |
| LTD-008 | Enterprise observability maturity | Health endpoints and Prometheus metrics exist, but dashboards, alert ownership, and SLOs are not yet complete. | `core`, `engine`, `web`, `worker`, deployment | Operational layer grew after product logic | High | Medium | High: production incidents harder to detect | Metrics backend, alerting target | Add structured dashboards, alert thresholds, SLOs, and on-call runbooks. | High | Medium | Open | Verified `core/telemetry.py`, `/metrics/prometheus`, `/health`, `/healthz`, and telemetry tests. | 2026-06-29 |  | Engineering |
| LTD-009 | Premium UX full rewrite | Every user-facing message has not yet been comprehensively rewritten to a premium standard. | `signalrank_telegram`, `web`, `payments` | Large message surface area | Medium | High | Medium: conversion and trust impact | UX register inventory | Audit commands/messages one workflow at a time and add snapshot tests. | High | Medium | Open | UX register created with known gaps. | 2026-06-29 |  | Product/Engineering |

## Closed Items

| ID | Title | Resolution | Verification Evidence | Date Opened | Date Resolved | Owner |
| --- | --- | --- | --- | --- | --- | --- |
| LTD-C01 | Same-path divergent symbol gaps | Closed with subsystem-safe compatibility review. | AST scan: `same_path_symbol_gap_files=0`, `ref_only=0`, `target_only=0` for owned Python files. | 2026-06-29 | 2026-06-29 | Engineering |
| LTD-C02 | Telegram unknown command fallback | Added top-level `_handle_unknown_command` registered after concrete handlers. | Targeted command tests and full suite passed. | 2026-06-29 | 2026-06-29 | Engineering |
| LTD-C03 | Dead signal action callbacks | Signal keyboards no longer emit a trade callback when no signal id exists. | `tests/test_command_contracts.py` passed. | 2026-06-29 | 2026-06-29 | Engineering |
| LTD-C04 | On-chain exchange-flow veto | `OnChainAlpha` now uses configured provider context for inflow/outflow vetoes. | `tests/test_onchain_providers.py` passed. | 2026-06-29 | 2026-06-29 | Engineering |
| LTD-C05 | TP dict parsing | Realtime outcome TP parsing accepts `price`, `tp`, `target`, and numeric entries. | `tests/test_time_stop_outcome_persistence.py` passed. | 2026-06-29 | 2026-06-29 | Engineering |

## Maintenance Rule

Update this file after every audit, implementation, refactor, optimization, or
release-hardening pass. Closed items must retain resolution evidence.
