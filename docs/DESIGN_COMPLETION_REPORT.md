# SignalRankAI redesign completion ledger — first implementation pass

| Workstream | Evidence state | Source evidence | Outstanding verification |
| --- | --- | --- | --- |
| Canonical recovery branch selected | VERIFIED | GitHub branch/compare inspection; `REDESIGN_BRANCH_BASELINE.md` | Reconcile independent divergent commits only if valid |
| Design and brand inventory | IMPLEMENTED | `DESIGN.md`; `BRAND_COLOR_AUDIT.md`; backend, API, frontend and mobile source inspected | Full comparative site/device visual review |
| Public mobile navigation | IMPLEMENTED | `PublicNav.tsx`; home and legal/product information pages wired | Browser/tablet/mobile QA |
| Responsive app shell | IMPLEMENTED | `AppShell.tsx`, `workspace-design.css` | Zoom, focus, safe-area/device screenshots |
| Actual canonical data views | IMPLEMENTED | `WorkspaceLive.tsx`: account-gated GETs, no API writes; overview, signals, paper, portfolio, performance, billing, broker status, operations and related read-only feeds | Staging account/entitlement/browser API contract smoke |
| Secure authentication UI | IMPLEMENTED | `AccountEntry.tsx` for registration, cookie login and MFA challenge; `SessionExit.tsx` for verified logout | End-to-end MFA/login/session/CSRF across configured API origin |
| No fake financial/market data | IMPLEMENTED | `presentation.ts` strict finite checks, recorded currency only, calibrated fractional probability and unknown broker environment | Unit tests + actual data fixtures |
| Lower-level API safety | IMPLEMENTED | No mutation in `WorkspaceLive`; no new execution backend code, database writes or kill-switch paths | CI security contracts, QA |
| Unit tests | IMPLEMENTED | `frontend/scripts/presentation.test.mjs` + `npm run test:presentation` | Must execute on Node 22 and review output |
| Complete frontend/mobile & Telegram parity | NOT COMPLETE | Initial read-only web implementation is not full authenticated product/mobile rebuild | Full UI/mutation workflows + approval, full native QA |
| Full release/soak | BLOCKED_EXTERNAL | PR #189 staged recovery source; broker and provider readiness not yet certified | Hosted CI, real demo fills, props, 24–72h soak, two audits |

**No production deploy, merge, broker connection, live execution or claim of passing full Next/mobile/browser tests.** This report deliberately does not label incomplete engineering BLOCKED_EXTERNAL unless a genuine outside requirement is established.


## Continued authentication/QA progress — 8 October

- **IMPLEMENTED**: `frontend/src/components/PasswordRecovery.tsx`, `/recover` and direct handling of backend-issued `/app?password_reset=TOKEN`. This matches the **existing** backend link builder in `services/platform/identity.py`. No reset token is placed in local storage.
- **IMPLEMENTED**: `frontend/src/app/error.tsx`, `loading.tsx` and `not-found.tsx` provide safe route fallback text without disclosing order, trade or identity information.
- **IMPLEMENTED**: Pure UI presentation tests are part of the existing required `frontend` transport test script; CI will run them without relaxing release certification or modifying recovery policy.
- **VERIFIED FOR AN EARLIER HEAD ONLY**: GitHub Actions run `37782585165` frontend job `113329216604` completed successfully, including lint, TypeScript, existing transport/dependency tests, security audit policy and Next production build. This run did **not** include the later password-recovery and presentation-test-script changes, and does not certify current PR head.
- **BLOCKED_EXTERNAL / DEPLOYMENT CONTRACT**: Check `NEXT_PUBLIC_SIGNALRANK_API_BASE_URL` and same-site session cookie/CSRF routing in the deployed Next frontend; source alone cannot establish cross-origin browser policy. No trading execution or account mutation was tested live.
- **RELEASE STATUS**: draft PR `#190` remains layered above the recovery work in draft PR `#189`; no merge or production/staging promotion.


## Account workflow and UI functionality addendum (2026-10-08)

- **IMPLEMENTED:** Existing backend-issued one-time email links for `/app?verify_email=...` and `/app?magic_login=...` are handled by `AccountEmailLink`. Confirmation is user-initiated so email prefetch/link scanners do not consume tokens; magic login still completes MFA where required.
- **IMPLEMENTED:** Non-enumerating email magic-link request page `/magic-login`, no-index/no-store policy, and accessible sign-in option.
- **IMPLEMENTED:** `AccountCreation` allows user-owned watchlist, journal and support creation through existing `/api/v1/platform` endpoints with CSRF transport, server-confirmed results and no order/payment mutations.
- **IMPLEMENTED:** `SignalFilters` adds instrument, class, timeframe and strategy filters to the authenticated delivered-signal feed. Filters never change market scans, ML selection or risk gates.
- **IMPLEMENTED:** Security/privacy headers for `/app`, `/app/:path*`, `/login`, `/recover`, `/magic-login` set private no-store, noindex and no-referrer.
- **TESTS ADDED:** Account creation endpoint allowlist and explicit email-link/MFA consent source tests are integrated into required `npm run test:transport`. No latest-head CI results yet at this documentation point.
- **VERIFIED for earlier UI head `5a8cc7a7e202`**: GitHub Actions `37783520705` frontend job `113332391571` completed with 13 transport/presentation tests passed, 3 dependency tests passed, 5 audit-policy tests passed, zero frontend npm vulnerabilities, lint, TypeScript and Next build successful. Other jobs failed.
- **BLOCKED/NOT FINISHED:** Full automated release still fails due four high-severity mobile npm audit findings; backend-governance detects stale `requirements/legacy_disposition.json` when frontend files are added. The existing workflow `.github/workflows/regenerate-governance.yml` is hardcoded to commit to the **older** `implementation-of-master-blueprint` branch and is not safe to invoke for this design branch. Governance must be regenerated using the canonical generator in the exact intended candidate branch, with diff review and CI checks, **not** suppressed or excluded.
- **NOT VERIFIED:** Real-browser authentication/cookie/MFA including domain alignment, native mobile apps, visual QA, staged demo account, broker/prop certification, 24–72h soak, two audits and production deployment.


## Account workflow finishing pass — 8 October 2026

- **IMPLEMENTED IN SOURCE, PENDING EXACT-HEAD CI:** Account notification inbox `NotificationCenter`, with server-confirmed per-record read update. The unread selector filters only the 50 returned records, not the entire delivery database.
- **IMPLEMENTED IN SOURCE, PENDING EXACT-HEAD CI:** `NotificationPreferences` renders the backend-reported channel state and sends only explicitly selected web/Telegram/email/push fields; unknown current values are not inferred. It intentionally does not overwrite quiet hours or timezone.
- **IMPLEMENTED IN SOURCE, PENDING EXACT-HEAD CI:** `WatchlistsView` searches the canonical active instrument directory, displays selected canonical instrument identifiers and adds them only to the signed-in user's backend-owned watchlist. No broker account/action is implicated.
- **IMPLEMENTED IN SOURCE, PENDING EXACT-HEAD CI:** Delivered-signal history supports canonical `limit=30`/`offset` pagination and retains user filters. It does not fabricate a total when the API omits one.
- **IMPLEMENTED IN SOURCE, PENDING EXACT-HEAD CI:** `JournalView` shows backend-recorded reflections, linkage to entitled signal evidence and R fields. Deletion needs two deliberate clicks and `deleted:true` from the account backend. No journal entry is presented as broker-confirmed profit.
- **SOURCE CONTRACT TESTS:** `frontend/scripts/presentation.test.mjs` asserts notification read receipts, partial preference writes, canonical watchlist identity, signal pagination, and deliberate journal deletion. This is included in frontend's required `test:transport` script. Hosted exact-head tests are queued at the time of writing.
- **SECURITY AUDIT STILL BLOCKING:** As of 8 October the official GitHub advisory `GHSA-86w9-cpqp-85rv` lists node-forge <=1.4.0 as affected and no patched version. Expo inherits four audit highs; no exception or unsupported patch has been applied.
- **EXTERNAL STAGING STILL ABSENT:** Railway `trading-bot-account2` has only `production`. The currently serving successful SignalRankAI deployment is older than its latest failed redeploy. Isolated staging/Postgres/Redis, cookie/MFA browser proof, broker demo certification and 24–72h soak are prerequisites, not completed here.


## Continuation: notifications, account preferences, support and market alerts

- **IMPLEMENTED / NOT YET BROWSER-VERIFIED:** `TradingPreferences.tsx` uses GET-supplied `tier_policy` minimum score, maximum daily signals and entitled classes/profiles. It writes only bounded account preference fields through `PUT /api/v1/platform/trading-profile` and reads canonical response values back. It does **not** change account/venue execution permissions.
- **IMPLEMENTED / NOT YET BROWSER-VERIFIED:** `SupportCenter.tsx` reads the signed-in user's ticket and conversation detail, and writes replies only to an owned, open ticket. The backend remains the permission boundary. No response times, refunds or issue resolution are promised by the UI.
- **IMPLEMENTED / NOT YET BROWSER-VERIFIED:** Corrected a semantic conflation: `/app/alerts` now uses the `GET/POST/DELETE /api/v1/platform/alerts` rule contract, preserving the legacy web client condition format `{value:number}` for price thresholds. `/app/notifications` now handles the account inbox and message delivery preference controls. Alert disables require a separate deliberate confirmation and server `disabled:true`.
- **RELEASE GOVERNANCE FIX:** GitHub Actions `regenerate-ui-branch-governance.yml` initially failed on a normal non-fast-forward push when the candidate branch advanced during regeneration. The workflow now re-fetches the **same dedicated design branch**, resets only its runner checkout to latest fetched commit, executes the unchanged deterministic generator and `--check`, attempts a normal fast-forward push and retries up to four times after racing updates. It **never force pushes**, bypasses release gates, or updates main/production/staging branches. Exact-head workflow pass is pending.
- **TESTS ADDED:** `frontend/scripts/presentation.test.mjs` now asserts the backend score/daily limits, support ownership endpoints and success verification, separate alerts vs notifications endpoints, alert threshold wire format, and no broker order calls from these components.
- **MOBILE SECURITY RELEASE BLOCK REMAINS:** GitHub reviewed advisory [GHSA-86w9-cpqp-85rv](https://github.com/advisories/GHSA-86w9-cpqp-85rv) (updated 1 October 2026) still marks `node-forge <= 1.4.0` affected and lists no patched version on 8 October. Expo dependencies transitively generate four high npm audit findings. No vulnerable dependency bypass, audit exception, or unaudited crypto fork has been accepted.
- **NO RELEASE CERTIFICATION:** Exact latest-head frontend and integrated CI, isolated staging databases/queues, live cookie behavior, real demo broker fills, native-device parity, 24–72-hour staging soak and two clean independent audits remain absent. No production deploy or execution configuration change has been made by this design continuation.
