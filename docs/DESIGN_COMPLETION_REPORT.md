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
