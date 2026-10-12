# SignalRankAI frontend redesign — 2026-10-12
## Canonical branch strategy
- Production `main` remains the currently serving legacy `web/platform_app`. The main Next.js `frontend` directory is still the Next starter.
- Next.js account-connected implementation is on `design/signalrank-ui-rebuild-20261008`, PR #190, targeting the release-recovery line; not certified for production.
- This work layers onto that exact Next candidate at `265bea302359106d1f85f3b5469ce5cbce06b256` and lives on `design/signalrank-cinematic-terminal-20261012`, PR #200, targeting the existing design branch.
- The work is intentionally **frontend-only** plus an attribution / light CSS pass on legacy SPA; it must not overwrite or sidestep the 2026-10-08 release-recovery, authoritative role, MFA, market-data, broker admission, schema or Redis gates.
- Dedicated review project: `signalrankai-interface-review` on Vercel, root `frontend/`. It is **not** the SignalRankAI production frontdoor and deliberately omits `SIGNALRANK_PLATFORM_API_ORIGIN`, so workspace/API requests fail closed in the public design preview.

## Brand and creative standard
- Respect SignalRank's existing emerald/silver graphite icon and theme, not the cyan/lilac CRILOX logo palette. CRILOX appears only as a maker attribution.
- Design references used as pattern inspiration, not cloned assets: spatial terminal cards, editorial typography, sticky scroll storytelling, gradient lighting, accessible navigation, restrained micro-interaction and layered object assembly.
- Public hero and scrolling workstations contain **schematic non-live illustrations**. No fake trading prices, balances, broker mode, odds, gains, win rates, returns, open-now provider status, or execution confirmation.
- Work on actual connected services continues to require explicit account authority and server evidence.

## Frontend implementation
1. `frontend/src/app/page.tsx`: completely rewritten public frontend: conceptual hero terminal, five-market family rail, evidence-first proposition, interactive lifecycle, three truthful product-workflow stories, prominent risk/verification disclosure and workspace CTA.
2. `frontend/src/components/SignalLifecycleExperience.tsx`: a four-stage sticky scroll narrative (source quality, model/strategy qualification, account/risk admission, account-entitled delivery/outcomes). Accessible stage buttons, observer sync, reduced-motion and no-WebGL fallback.
3. `frontend/src/app/cinematic.css`: new responsive emerald/silver/graphite design system, public editorial styling, authenticated workspace card/tab navigation, real data presentation, mobile screens, login flows, empty/error/loading states, forced-colors and reduced motion.
4. `frontend/src/components/SiteCredit.tsx`: reusable **Powered by [CRILOX Solutions](https://www.criloxsolutions.com)** attribution, secure external anchor, in public homepage, public editorial pages, authenticated workspace and primary account entry.
5. `web/platform_app/index.html` and `web/platform_app/styles.css`: the same credit and conservative visual-polish layer for the existing serving legacy interface, without changes to financial or auth JS.
6. `frontend/scripts/cinematic-contract.test.mjs` and `frontend/package.json`: static regressions for real links, required stages, truthful disclosure, API-owned data, risk/auth navigation, CRILOX attribution, responsive and reduced-motion rules.
7. `.github/workflows/frontend-design-verification.yml`: separate UI-only check for npm/lint/tests/TS/build; it does NOT replace the mandatory release manifest or certify any broker, model, migration, payment, backend, staging or soak condition.

## Release evidence at handoff (must not turn into false completion)
- Isolated Vercel design-preview build for initial candidate `4bfe0bf...`: **READY**. The protected deployment currently requires authorized Vercel sign-in. It does not have a staging API origin configured; this is intentional.
- GitHub CI on PR #200: manifest and release-certification jobs failed; downstream frontend/backend/mobile suites were skipped. This is **not** a passing full certification.
- The isolated UI-only workflow was introduced and ran, but failed before a step summary/log could be retrieved (runner job log returned BlobNotFound; do not assume source-code failure or success).
- Next task: verify a NEW exact-commit preview after the final CSS/docs, independently capture full frontend build/test output and fix anything testable, and run browser snapshots and keyboard/pointer checks.
- Existing SignalRank staging Railway services are available but contain real operational roles; do not switch their source branch or auth routes until release/staging certification allows it.

## Completion checklist
- [x] New brand-consistent public design and scroll assembly source code
- [x] Reuse canonical session, MFA, CSRF, entitlement, signal and broker API integrations (no new fake endpoint)
- [x] Reusable CRILOX footer in Next public/authenticated shells and legacy web SPA
- [x] Mobile/sticky nav and responsive CSS; reduced-motion CSS
- [x] Static frontend guard-test source, safe independent UI-only workflow
- [ ] Frontend checks (npm ci, TypeScript, lint, transport, presentation, dependencies) **green on exact candidate**
- [ ] Browser visual and interaction QA across actual desktop/tablet/mobile hardware, including every account state
- [ ] Complete 27-route / full Telegram parity, all role-dependent write workflows and realistic failure cases
- [ ] Certified staging DB/Redis isolation, real account demo broker fill/partial/breakeven, market-data session evidence
- [ ] Master blueprint traceability and governance regeneration for this exact branch, full CI and release certification
- [ ] Real 24–72-hour staging soak and owner-approved production merge
- [ ] Check real-time accessibility, performance/Web Vitals and reconnect/refresh behavior

## Recommended next features, contingent on evidence
- Real interactive signal-evidence drilldown with source lineage, timestamps, confidence calibration metadata and event receipts supplied ONLY by the canonical API.
- Performance evidence charts, paper-trade drilldowns and asset-specific interfaces backed by real typed responses; no static pseudo-profit charts.
- Account-aware multi-broker destination selectors only after audited backend destination, risk/amount and permission contracts exist.
- Screenshot baselines at every route and 320/375/430/768/1024/1440/1920 widths; guard visually hidden active tab text, overlays and clipped forms.
- Performance budget: avoid a persistent high-cost 3D canvas in dashboard; use lightweight CSS/DOM motion for public illustrative scenes and opt-in 3D where useful.
