# SignalRankAI: FastAPI workstation, Next.js preview and PWA cutover

## Why these three surfaces must be reconciled

This repository currently contains **three** presentation implementations:

1. `web/platform_app/` — existing Python/FastAPI-served `/app` workstation, with mature account, owner, paper and broker workflows, standalone HTML/CSS/JS and a PWA service worker at `/app/service-worker.js`. This is the presently configured Railway source used by the old successful production service, but it has not received this candidate's source commits in production.
2. `frontend/` — redesigned Next.js marketing and account workspace. It also owns an `/app` route; it **cannot** be assumed to replace (1) at the same origin without an explicit routing migration.
3. `mobile/` — the independent Expo React Native application.

A common brand and typed canonical data are necessary but do not prove feature parity. Route collisions, authentication cookies, old cached service worker navigation and real account entitlements must all be checked in staging.

## Current design/source reconciliation

- The FastAPI SPA has already been styled with the approved emerald/silver brand and responsive view classes. The 2026-10-09 additions in `web/platform_app/styles.css` only improve safe-area, 320–390px behavior, focus and overflow. Existing SPA IDs, account checks, broker and paper actions, and its JavaScript remain unchanged.
- The SPA stylesheet now uses cache-busted `/app-assets/styles.css?v=44`, with matching `signalrank-shell-v44` service-worker cache. Icon, manifest and visual browser theme color use the approved brand. The old JS `app.js?v=43` is deliberately unchanged.
- The Next.js application uses a server-owned same-origin rewrite for `/api/v1/platform/*` and must point only to a trusted matching **staging** backend. Do not assume a Next app on one host can read `sr_csrf` from another host.
- Expo must be separately certified for app store signing, native login, secure storage, push links, user system appearance, voice accessibility and account features.

## Cutover acceptance sequence (not executed)

1. Provision an independent staging web/Next host, FastAPI API, Postgres and Redis. Use staging-only credentials, data and queues. Verify `APP_COOKIE_DOMAIN` and `APP_BASE_URL` for the staging web hostname, and `SIGNALRANK_PLATFORM_API_ORIGIN` pointing to the staged API. Ensure no production database or broker order destination is reachable from staging.
2. Inventory every existing SPA `data-view`, menu, login, account operation and broker/paper/owner control against actual backend endpoints and new Next routes. Record each as IMPLEMENTED, VERIFIED, MISSING, or SPECIFICALLY RETAINED ON LEGACY. Do **not** replace mature SPA tools with static read-only placeholders.
3. Test the Next public/site and private routes at 320–1920px, with light/dark/system, keyboard, forced-colors, 200% zoom, screen readers and native device browsers. Capture source commit and screenshots.
4. Prove browser cookies, CSRF writes, password reset and magic links, MFA, account restrictions, plan billing, account-scoped notifications, watchlists, paper/execution separation and owner visibility in staging. Never record raw cookies or tokens in logs/screenshots.
5. **PWA collision mitigation:** the existing `/app/service-worker.js` is scoped to `/app` and can cache `/app` offline. A same-origin cutover to Next must deploy an explicit service-worker retirement/update response at the previous service-worker URL before or with the route switch. The retirement script should stop interception, remove only `signalrank-shell-*` caches, activate immediately, and unregister after all current clients have been notified. Do not simply delete the URL: previously installed service workers may continue running. Confirm navigation after reload, offline transitions and fresh/returning-user behavior. Do not delete unrelated caches.
6. Prove the production routing switch is reversible, preserve user sessions safely and do not change any broker permission or trading control as part of a visual migration. Roll back on stale-app cache, auth, owner-gate or data consistency failures.
7. Deploy the exact approved source SHA only after full CI, independent staging financial/provider certification, 24–72h soak and two clean audits. Document source/provenance, results, rollback plan and human approval.

## Honest current status (2026-10-09)

The new Next public pages, private workspace and native redesign are code-complete **for the implemented first-pass features**, not universally feature-parity-certified. The current FastAPI SPA already has many workflows that do not exist in the Next client. The recovery branch continues to receive independent research/risk fixes. The mobile Expo security audit still has upstream high-severity findings. No isolated SignalRank Railway staging was observed, no browser cutover or service-worker retirement was performed, and production deployment remains unchanged.

This is a cutover plan and release acceptance document, **not evidence that the user-facing production domain has migrated**.
