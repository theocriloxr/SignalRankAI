# Release blockers and exact continuation

Current Stage 1 acceptance: **FAILED — integration and clause-level acceptance
are not yet fully closed**. This deliberately does not claim completion from
reports or code presence. External release gates remain closed independently.

| ID | Status | Owner/component | Evidence / next action |
| --- | --- | --- | --- |
| ST1-TEST | FAILED | Engineering / local verification | The first full diagnostic timed out in database-heavy batch 1 at the harness's 300-second bound; Railway simulation did not become healthy in its 25-second allowance. Diagnose, use a justified bounded local test allowance, run the frozen integrated revision, and retain failures/skips/counts. |
| ST1-SOURCES | FAILED | Architecture and component owners | The inventory retains current and historical clauses, but many have no source-specific implementation/acceptance disposition. Resolve each applicable clause with code and meaningful tests; preserve superseded/optional context explicitly. See the generated matrix, not old PASS reports. |
| ST1-INTEGRATION | FAILED | Repository maintainers | Complete review/tests, commit the resolved integration and handoff artifacts, push only the new branch and create a draft PR into main. Do not force-update main or activate deployment. |
| EXT-CI | BLOCKED_EXTERNAL | GitHub billing/account owner | `evidence/github-latest-annotations.json`: jobs never started because the account is locked due to a billing issue. Restore GitHub Actions availability and rerun required checks on the proposed SHA. |
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

The next engineering action is to finish local integration evidence and review,
then use the source matrix as the exact remaining work queue. Resolve failures
without weakening risk, calibration, ownership or evidence thresholds. Document
why any historical implementation is superseded; never silently drop its source.

No production migration, configuration change, customer data write, billing
operation, broker order or real-money permission change is authorized by this
handoff. External blockers do not justify marking unrelated local work complete.
