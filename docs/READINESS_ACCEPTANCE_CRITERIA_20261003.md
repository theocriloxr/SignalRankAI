# Release acceptance and scoring criteria

Requested targets: every applicable subsystem dimension and aggregate at least
90; development and merged-feature completeness 100; stability acceptance 100;
enterprise readiness at least 97; institutional trading maturity 100.

These are acceptance targets, not achieved scores. Historical June estimates
in `PRODUCTION_READINESS_SCORECARD.md` cannot certify the October release.
No current numeric score is published without the evidence below. Passing
tests establish the behavior they exercise; they do not establish profitability
or guarantee the absence of future failures.

## Evidence and calculation

Freeze the release SHA, normalized source hash, dependency locks, schema head,
configuration identity, required assets, account policies and acceptance scope.
Use the existing `requirements` traceability and release gates to account for
every merged feature and every master-directive requirement. A requirement is
complete only when its implementation and acceptance evidence are reviewed.
Missing, skipped, mocked-only or stale external evidence remains incomplete.

Before assessment, split each applicable dimension into acceptance criteria
with named owners and equal weights. Each criterion passes only with reviewed
evidence tied to the frozen release; unsupported criteria receive zero credit.
Dimension score = 100 times passed weight divided by applicable weight.
Subsystem score is the mean of its applicable dimensions. Define applicability
before running checks; an unresolved feature cannot be converted to N/A.
Always show failed criteria alongside the score. Do not use averages to hide a
failed security, execution, provider or recovery gate.

Development and feature completeness require all frozen requirements to pass.
Stability 100 means every scoped reliability acceptance criterion passed,
including the actual 24–72-hour soak; it is not an absolute future guarantee.
Enterprise readiness covers the operational, security, governance and support
criteria. Institutional maturity requires every trading lifecycle, account
policy, data provenance, reconciliation and intervention criterion to pass.
The requested percentages cannot authorize execution while any release gate
is blocked, even if an aggregate happens to meet its threshold.

## Dimension evidence required

| Dimension | Acceptance evidence |
| --- | --- |
| Architecture | Reviewed ownership and dependency boundaries, one canonical path per lifecycle, no alternate route bypassing policy, schema and migration compatibility |
| Code quality | Full typing without debt allowance, lint and static analysis completed without suppressed coverage failures; reviewed error and resource handling |
| Test coverage | Measured line and branch coverage at least 90% in the scoped subsystem, critical financial state transitions and failure paths exercised; real integrations distinguished from mocks |
| Performance | Release-specific repeatable load tests against approved latency, throughput, memory and provider-budget objectives; percentile distributions and saturation evidence |
| Security | Completed dependency, secrets, source and container scans; reviewed authentication, authorization, webhooks, credentials, tenant isolation and financial abuse cases; no unresolved release-blocking exposure |
| Scalability | Load and concurrency evidence at declared launch capacity with database/Redis/pool limits, queue bounds, backpressure and provider quotas enforced |
| Reliability | Retry/idempotency, partial failure, crash/restart, Redis loss, database restore, kill switch and stale-data drills; sustained soak without unresolved material failure |
| Observability | Tested metrics, freshness-aware readiness, alerts, tracing and audit events; alert delivery and operator response confirmed, credentials redacted |
| Documentation | Current release identity, runbooks, disaster recovery, account onboarding, limitations, API contracts and requirement traceability reviewed |
| UX | Actual tier-aware desktop/mobile flows in light/dark/system, keyboard and screen-reader acceptance, native devices, truthful states and clear transaction feedback |
| AI/ML maturity | Versioned models/prompts, leakage-free held-out evaluation, calibration and drift evidence, cost/latency limits, reproducible promotion and safe fallback |
| Trading intelligence | Certified provider provenance and freshness, account-specific risk admission, real demo fills, partial exits, breakeven, reconciliation and intervention evidence |
| News intelligence | Source provenance, deduplication, timestamps, impact/novelty evaluation, stale/conflicting news handling and held-out impact evaluation |

Objectives for performance and capacity must be approved against actual launch
traffic before measurement. A successful health probe is not a latency/load
certificate. A passing test count is not a coverage percentage.

## Subsystem acceptance focus

| Subsystem | Additional acceptance paths |
| --- | --- |
| Core engine | Signal admission through decision, delivery, outcome and execution; bounded scheduling, risk and kill-switch enforcement |
| Telegram product | Every registered command/callback/menu by tier, actual test-chat delivery and web parity, retries and revocation |
| Data providers | Each required asset class during its trading session, provider identity, quota/failover behavior, candle validation and stale rejection |
| News intelligence | Actual source ingestion, provenance and retention; event impact evaluation and reproducible shadow promotion |
| ML/Gemini | Model/prompt provenance, calibration, drift, outage fallback and promotion rollback |
| Payments/subscriptions | Signed real sandbox events, duplicate/out-of-order webhook replay, refunds, revocation, billing/tier parity and tenant isolation |
| Web/admin | Authenticated seven-tier flows, privileged authority, session/CSRF protections, responsive/accessibility/device acceptance |
| Operations/observability | Immutable fleet identity, capacity, restored backup, connection budgets, monitored soak and incident drills |
| Governance/docs | All frozen requirements traceable to evidence; two full audits with no new material gaps; operator release decision |

## Current gates and activation sequence

The current production capacity, schema and immutable rollout, hosted CI,
dependency vulnerabilities, incomplete Semgrep analysis, typing debt, provider
entitlements, broker certificates, native devices, sustained soak and two clean
audits remain open as documented in `UI_REFRESH_AND_LAUNCH_GATES_20261003.md`.
No requested target is certified as achieved by this document.

Complete paper and demo acceptance first. For funded prop testers, record each
firm/account type, automation permission, verified loss/drawdown baselines,
reset timezone, policy version and execution certificate. Different firms
require different verified policies. Enable only the certified account and
asset scope through existing admission controls, retaining an operator kill
switch. Monitor a limited rollout before expanding access. Never replace
provider freshness or account policy checks with blanket launch approval.
