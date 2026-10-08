# Shared-chat recovery and release repair — 8 October 2026

## Continuation after hosted CI

Draft PR [189](https://github.com/theocriloxr/SignalRankAI/pull/189) published the
recovery as `ae6a6fb4aab968187a4a3aa5e9a8fde807fc33f2`. Its hosted run
`37746622470` passed frontend and research-browser checks. Backend failed
because a test demanded a tilde range instead of accepting the exact Expo 57
pin; the retry additionally loaded persisted trades from an earlier process.
The test now verifies the locked SDK and manifest agree, and tracker unit tests
isolate persistence as well as memory. The failing 106-test batch now passes
locally. This is not yet a new hosted backend certificate.

Static analysis found the new mobile `.npmrc` lacked a minimum release age.
Both Node projects now require a seven-day resolution age, enforce compatible
Node/npm engines, and use npm 11.17.0 in CI. Clean installs, the frontend lint
and production build, mobile type checking, three frontend dependency tests
and all 44 mobile dependency tests passed with this npm version. The npm config
scan passed with zero findings; the full scan passed on 498 files. Frontend's
full dependency audit still reports zero vulnerabilities.

The research continuation repairs actual correlation admission paths:

- Compare percentage returns for identical start/end timestamp intervals,
  rather than raw price levels or unrelated equal-length tails.
- Reject missing, malformed, constant, short, duplicate or unordered histories,
  invalid thresholds and existing-symbol exposure. Never drop invalid rows to
  manufacture sufficient evidence.
- Use the current market-data coroutine in the optional controller gate. The
  old import did not exist, and its exception handler silently admitted signals.
- Require complete shared trade snapshots in the engine and optional controller.
  Redis errors, unavailable shared state and corrupt records cannot become an
  empty portfolio. Existing non-admission callers retain their compatibility
  fallback; the new strict read is explicit.

The focused risk/state/tracker selection passes 179 tests; critical Pyright
reports zero errors and targeted Ruff passes. These checks use synthetic
evidence, not live account or broker certification. Untimestamped correlation
input now blocks admission when exposure exists. Absolute correlation remains
a conservative constraint; it does not establish portfolio netting, account
drawdown, stale-market-data acceptance or per-venue sizing readiness. The
engine's existing synthetic drawdown state is still not real account evidence.
The remaining ordered directives and financial release gates remain open.

## Source identity

The shared chat `cx_6ac748fc2cfc8191993747df1966a449` was retrieved in full.
Its last published source is `c7684b34178be6d69960c89b42a2805d6ccfb3ab`
on `fix/provider-discovery-readiness-20260923`. The older
`implementation-of-master-blueprint` ref is not the continuation source.
The final turn contained unpublished work under
`.pytest-tmp/release-ci-closure-20261007/`; this change recovers that work,
regenerates actual dependency locks, and verifies it on Linux.

## Implemented repairs

- Replaced the vulnerable frontend glob chain with a bounded tinyglobby-backed
  directory adapter while retaining the actual Next lint rules.
- Updated Expo and SDK-compatible native dependencies. Replaced the remaining
  Metro micromatch consumer with a bounded picomatch-backed watcher adapter.
- Added installed-consumer tests and kept the complete-graph audit policy.
- Added a read-only verifier for the owned backup service's pinned image,
  restore command, dump digest, schema, restored-table checks and freshness.
  Promotion passes only verified recent backup evidence to the migration role.
- Fixed the recovered promotion import defect: the workflow invokes
  `python -m scripts.approve_production_release`, and its backup import is
  exercised at module load. A subprocess test removes PYTHONPATH and tokens.
- Reject malformed backup command metadata with a redacted validation error.

An ordinary `npm install` against the old frontend lock retained fast-glob and
the old vulnerability. The consumer test caught it. The regenerated lock and
subsequent clean `npm ci` load the adapter and pass the same tests. This failure
must not be mistaken for successful validation of the original lock.

## Verification performed

- Frontend: clean npm ci, three dependency behavior tests, seven transport
  tests, ESLint, TypeScript and Next production build passed. Full npm audit:
  zero vulnerabilities, no exceptions.
- Mobile: clean npm ci, 44 dependency/session/watcher tests and TypeScript
  passed. Android and iOS JavaScript bundle exports passed. These are not
  physical-device or signed-native-build certificates.
- The release, backup, credential, manifest and provenance selection passed
  123 Python tests; a subsequent malformed-command regression also passed.
  Five independent audit-policy tests passed. Critical Pyright reported zero
  errors; targeted Ruff passed using the locked Python runtime.
- The real 8 October production backup logs were read without database access.
  The receipt parser accepted the dump started at 02:01:53 UTC, schema
  `0045_mt5_credential_retirement`, with successful disposable restore and
  cleanup. No production rows or credentials were exported. This verifies
  parsing of an actual receipt; it does not certify an executed promotion.

No full backend/PostgreSQL suite, candidate deployment, new soak, live order,
native-device test or two clean audits has been completed in this recovery.
Hosted CI must establish the new commit's own evidence.

## Confirmed deployment cause and remaining blockers

GitHub run `37542700019` passed backend 3.11/3.12, static checks, research
browser, manifest and credential preflight. Frontend/mobile audits failed,
release certification failed, and production source approval was skipped.
Railway deployment `a1e8cee9-de8b-4a24-a586-8db5a1330924` rejected c7684b34
because its expected release remained 8f858393. The four serving application
roles still reported online; no production configuration was changed here.

Mobile still has four high-severity audit rows: node-forge and the inheriting
Expo CLI/code-signing dependencies. The current registry's node-forge 1.4.0
remains affected by GHSA-86w9-cpqp-85rv; the advisory lists no patched release.
The vulnerable path is cryptographic signature/certificate verification, so
an unverified replacement or an audit exclusion is not a completed repair.
The unchanged security gate continues to block automatic promotion.

The source Google research document remains unreachable from this environment
through both the reader and text export. A readable copy is still needed for
the independent document review. The saved research directive is available.

Continue `docs/completion-order-20261006.md` in the user's requested order:
research validation; customer execution UX; complete web/mobile screens;
multi-broker routing; completion/resilience; operational acceptance; then the
self-improving per-asset/per-class strategy loop. Preserve the already fixed
Telegram identity/session behavior. Provider entitlements, real demo/broker
and prop-rule certification, native acceptance and a fresh immutable 24–72h
soak remain required. Do not reuse the old degraded soak as a pass.
