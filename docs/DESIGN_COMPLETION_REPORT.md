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


## Public and native redesign continuation — 9 October 2026

This section distinguishes **committed source work**, **hosted code verification** and **financial release acceptance**. They are not interchangeable.

### Implemented: full public Next.js informational experience
- Rebuilt `frontend/src/app/page.tsx` with an original emerald/silver editorial layout, CSS-generated abstract systems visualization (explicitly conceptual, never live price data), market coverage, multi-stage qualification model, research/paper/broker boundaries and secure workspace CTA.
- Replaced the original two-paragraph stubs on **all seven** public reference pages: `pricing`, `methodology`, `risk`, `security`, `status`, `docs`, `providers`. Each now has a structured hero, three substantive sections, bulletproof explicit claims, a relevant next page, and clear non-certification note.
- Added `PublicEditorial.tsx` and responsive `public-design.css`. Approved brand colors and light/system/dark tokens preserved; original layout does not import Framer assets or template licenses. Coverage at 320px, forced-colors, reduced-motion still requires actual device/browser review.
- Fixed one hosted JSX lint error and the old unreachable workspace renderer comparisons; removed internal full reloads on web sign-in/sign-out.
- Added source-level public-route and truthfulness regression tests in the mandatory frontend transport suite.

### Implemented: native UI redesign and safety
- Added `mobile/src/presentation.ts`: honest money formatting from **recorded currency**, fractional percentages, missing-value preservation, explicit non-zero tone. Removed fabricated USD assumptions and `0` substitutes from dashboard, paper, portfolio, performance, plans and receipts.
- Rebuilt native overview, delivered signals with entitled detail/evidence, paper, portfolio and historical performance using retryable account reads and read-only trading disclosures.
- Replaced nine crowded horizontally scrolling tabs with **four primary destinations plus a scrollable More panel**, currently exposing **14 native screens**: overview, signals, markets, paper, portfolio, performance, journal, support, account, brokers, notifications, watchlists, custom alerts and research.
- Added `AccountScreens.tsx` for broker connection inventory (strictly no trading control), confirmed notification reads, and user-owned watchlists with canonical instrument search/addition.
- Added `ResearchAlerts.tsx` for entitlement-gated research frequency diagnostics and confirmation-based monitoring alerts. Monitoring rules are **not** broker orders.
- Updated dark/native brand colors, push notification accent and Android adaptive-icon background. Existing `userInterfaceStyle: automatic` is now matched by system-driven dark/light styles across the native shell, tab bar and added account/alert components. No manual per-account theme override is claimed.
- Added native source contract tests to the required mobile dependency test suite.

### Hosted evidence to date
- GitHub Actions run `37890291443` (commit `e78bb964...`) **frontend job PASS**: lint, TS, Next 16.3.8 production build, 28 transport/presentation tests, 3 dependency tests, 5 audit policy tests and zero frontend npm advisories. This does not include **every** later native commit.
- Mobile hosted run `37890335474` (commit `57adb611...`) passed native TypeScript and **53** source/dependency tests but **failed** the unwaived npm audit for Expo/`node-forge`. Exact latest-head mobile tests, Android/iOS artifacts and light-mode screen-reader tests require current run evidence.
- The full CI release is **red**; design source completion cannot override mobile security or independent backend/governance/research gates. Do not declare "fully completed" based on unit or source tests.
- Recovery PR #189 advanced independently after the design branch last incorporated it. Compare and reconcile new engine/research commits through a real merge with conflict and governance review; never forge a merge commit without integrating source.
- Railway production currently serves an older accepted deployment; its newest failed redeploy and source-provenance gates remain. No isolated Railway staging environment, staging cookie/browser proof, broker demo certification, controlled restore, 24–72h soak or two complete audits have been established.

### Remaining work that must not be marked verified
1. Run exact-head full CI after recovery-branch reconciliation and regenerate source evidence against the immutable candidate. Fix code/type regressions, but **never suppress** high-severity mobile audit or relax risk/kill-switch tests.
2. Test public and signed-in web routes at responsive widths and zoom with real screenshots, keyboard/a11y and session/CSRF integration. Test Expo native Android+iOS, system light/dark, alerts/watchlists, deep links, push and device logout.
3. Provision independently isolated staging services, Postgres and Redis. Certify broker accounts and market data during real sessions; prove actual demo fills/partial exits/breakeven and safe multi-broker account selection.
4. Complete recovery, rollback, restoration, observability, 24–72h soak and two audits. Retain staging and production separation until all approval and evidence gates pass.

**No production merge, Railway configuration change, live-money enablement or order submission occurred as part of this public/native design continuation.**


### Verification update
- After source changes, the first full CI job found a JSX apostrophe lint error, which was fixed. A subsequent frontend TypeScript issue came from unreachable duplicate branch checks and was removed, not suppressed.
- Hosted run `37890291443` frontend then passed the **28 tests / 3 dependency tests / 5 audit policy tests / lint / TypeScript / Next production build** suite; an additional run `37890335474` also reported **frontend PASS** with mobile compile and **53 tests PASS**, and **mobile audit FAIL**.
- The native research and alert components are included in the 53-test mobile run at commit `57adb611...`, with Expo `userInterfaceStyle=automatic`, current native source appearance mapping, and the 14-route bottom/More navigation present in that candidate.
- All results are **source/build evidence only**. They are not screenshot/device, login/browser/cookie, broker fill, environment isolation or release soak certificates; newer documentation commits require fresh exact-SHA CI.
