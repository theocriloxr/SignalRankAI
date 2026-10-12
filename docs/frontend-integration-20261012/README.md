# Frontend integration and release evidence — 12 October 2026

This record separates implemented source, local acceptance and production acceptance. It does not certify live trading or close the earlier research, native, security or resilience directives.

## Branch reconciliation

- Verified production backend baseline: `9865a3d1bcee632bfd9347e50d5de34d355225d9`, schema `0053_research_market_inputs`.
- Integration branch: `fix/release-recovery-20261008`. Production branch remains `fix/provider-discovery-readiness-20260923`.
- PR #200 merged into the UI branch as `f7ca87be51cad7f048b20b21e92437024104dc4b`, with final design head `704b973b1080c787a87a4f259796ec58b47595c3`. It was not a production deployment.
- The integration includes the design stack, current backend fixes and semantic regeneration of governance. The latest four-file design follow-up is retained. Both upstream ancestry and generated inventories must be reconciled before publication.
- `origin/main` at `98a5de18f92674c9e70ec61a802391bf984de8d6` is already an ancestor of the verified production baseline. The two unique commits on the older blueprint branch are historical merges with no additional source delta. That branch is not the continuation source.
- Migration `0054_shadow_pending_index` adds a concurrent, validated partial index. The same additive index was applied operationally on production without advancing its Alembic revision; a future controlled migration adopts it idempotently.

## Safe frontend release boundary

`Dockerfile.frontend` and `railway.frontend.toml` define a separate, non-root, pinned Node service. It has no database, broker, worker or trading credentials. A configured HTTPS backend origin supplies canonical account APIs. Browser requests remain same-origin, with the existing HttpOnly cookies and CSRF checks.

`SIGNALRANK_WORKSPACE_MODE=legacy` retains the existing FastAPI workspace while publishing the new public website. It preserves `/app`, installed PWA assets, activation and billing returns, APIs, webhook ingress, health/version/metrics and broker/payment paths. Workspace links use full document navigation. Known deep links redirect to the existing SPA's visible `?view=` selector. The retained HTML shell is fetched without account cookies and returned with an explicit private/no-store policy. Its browser API calls keep their own session authority.

`SIGNALRANK_WORKSPACE_MODE=next` is a separate workspace candidate. Do not promote it merely because all pages render. Some mature account, professional and owner operations still need complete acceptance and parity. The installed PWA must be retired deliberately before replacing its navigation scope; retaining it requires no retirement.

API rewrites have a fixed operator-owned destination. Arbitrary request origins cannot receive session or CSRF authority. Client mutations are never automatically replayed after a 401. New Next HTML uses fresh CSP nonces. The retained independent HTML keeps its own CSP, with a conservative compatibility policy when upstream supplies none.

## Route and action inventory

The generated [contract inventory](contract-inventory.json) resolves 67 frontend API call sites to real backend handlers and inventories 117 canonical Telegram commands, 12 retained SPA views and the preserved historical route requirements. The [Telegram matrix](telegram-web-matrix.md) records actual canonical destinations. A route mapping is not execution acceptance.

| Next workspace route | Main backend data | Local acceptance and remaining work |
| --- | --- | --- |
| `/app` | dashboard, account | Real authenticated render; complete personalized workflow acceptance remains |
| `/app/signals` | entitled signals and signal evidence | Real account response and empty state; generation-to-delivery acceptance remains |
| `/app/markets` | quality and instrument search | Real authorized render; enabled market-class certification remains |
| `/app/research` | strategy leaderboard | Real authorized render; full research workbench remains |
| `/app/watchlists` | account watchlists and instruments | Browser creation persisted after reload; cross-account isolation and missing-CSRF denial verified locally |
| `/app/alerts` | account alert rules | Real authorized render; complete alert lifecycle acceptance remains |
| `/app/notifications` | notifications and channel preferences | Real authorized render; channel delivery acceptance remains |
| `/app/paper` | paper snapshot, detail, settings, reset/close/retry | Real authorized render; full simulation lifecycle and failure acceptance remain |
| `/app/portfolio` | portfolio | Real authorized render; broker reconciliation remains |
| `/app/performance` | eligible outcome performance | Real authorized render; comprehensive financial-statistic validation remains |
| `/app/journal` | account journal | Real authorized render; all journal writes and failure flows remain |
| `/app/brokers` | connections, demo setup and verification | Real authorized render; actual external demo verification/fills remain |
| `/app/billing` | subscriptions and receipts | Real authorized render; new-workspace checkout/renewal parity remains; mature tools retained |
| `/app/support` | support tickets | Real authorized render; full ticket workflow acceptance remains |
| `/app/settings` | identity, trading profile, MFA, Telegram link | Already-linked Telegram/verified email do not ask for reconnection; full MFA/recovery acceptance remains |
| `/app/operations` | owner overview | Authorized render; ordinary customer denied by UI and API; broader operator actions retained in existing workspace |

Public pages include product, features, markets, strategies, AI, methodology, risk, pricing, security, privacy, providers, documentation, FAQ, status and contact. The status view publishes only bounded, uncached availability observations; it never publishes raw diagnostics or claims broker readiness. Prices, performance figures and testimonials are not invented.

## Local evidence

The immutable `fae19b93` checkpoint passed both local browser modes and 56 frontend tests with zero frontend dependency audit findings. Its full backend run then exposed a mixed PWA asset generation and a Windows-default text decoding failure in a mobile source-contract test. The follow-up aligns every retained shell reference to generation 45 and reads the UTF-8 source explicitly; those original failed receipts remain preserved. Hosted checks on that checkpoint were rejected before starting because GitHub reports an account billing lock.

An isolated Railway UI acceptance project now has its own PostgreSQL and Redis. `railway.ui-backend.toml` builds the canonical backend with its existing image checks and guarded migration command. The service must use the web-only role, new staging secrets, execution disabled, and no broker or delivery credentials. Provisioning infrastructure is not deployment or soak acceptance.

Artifacts are under `artifacts/ui-refresh-20261003/manual-release-20261011/frontend-integration-20261012/` in the shared workspace. They are also emitted by the hosted browser workflow.

- `browser-04`: new workspace passed real local FastAPI/Postgres login, HttpOnly cookies, refresh, CSRF writes, persisted watchlists, account isolation, owner denial, Telegram connection state and dark/light responsiveness at nine widths from 320 to 1920. This evidence predates the additional public pages and is from a dirty integration tree; it is not final-SHA evidence.
- `browser-legacy-01` exposed lost deep-link selection. `02` and `03` exposed missing private cache headers on the external HTML proxy. Their failures remain preserved.
- `browser-legacy-04`: the corrected public/retained-workspace integration passed actual login, deep links, CSRF writes, PWA scope/assets, unsigned-webhook rejection, callbacks and public status/theming at six widths. It is also dirty-tree evidence until repeated on the published candidate.
- Focused backend checks passed 20 tests, including actual 100,000-row PostgreSQL index behavior, migration idempotency and downgrade data preservation, browser-runner isolation and broker destination admission.
- Final exact-SHA browser, frontend, governance, static and relevant backend results must be attached independently after publication. No dirty-tree result substitutes for them.

## Operational evidence and unresolved acceptance

The production shadow queue query dropped from 172.131 ms to 5.876 ms server execution, and from 14,098 to 8 read pages, after the concurrent index. This does not prove that network or all database timeouts are eliminated. The post-index observer still recorded a canceled decisions query at 19:55 UTC; that failure must remain in the monitoring window.

At 22:06 UTC the read-only observer had approximately 12.17 observed hours and remained DEGRADED. Production was healthy, but staging was unavailable. No clean 24–72-hour soak or two clean audits are certified. Last confirmed signal delivery remained 6 October; the saved MT5 connection remained unverified. No broker order or live/prop activation was performed.

The production domains currently belong to the backend service and use provider-managed CNAME records. DNS authority is Whogohost. A new Railway preview alone does not update those domains. Preserve the working domain bindings until a concrete verified cutover and rollback are available.

Mobile still has four high audit rows associated with upstream `node-forge` dependency usage. The advisory reviewed on 12 October lists no patched version. They remain failures; no advisory suppression, package renaming or fake security pass is allowed. Existing OS findings, actual demo lifecycle acceptance, native-device acceptance, the full activation requirements and the earlier specification backlog remain open.

## Latest prompt reconciliation

The exact new prompt is preserved at `docs/specs/20261012/ecosystem-frontend.md`. Its 22 sections are additional requirements, not replacements for the prior 560 preserved sections or separate master registry.

| Sections | Status | Evidence boundary |
| --- | --- | --- |
| 1–2 | IMPLEMENTED | Baseline, branch comparisons and integration inventory recorded; final merge/release receipt remains |
| 3–5 | IMPLEMENTED | Brand, themes, cinematic homepage and public pages; final accessibility/performance/deployment acceptance remains |
| 6–10 | DEFERRED | Substantial new workspace implementation and local journeys exist; all actions, account tiers and parity remain to be accepted |
| 11–13 | IMPLEMENTED | Shared styles, responsive layouts, reduced motion and CRILOX attribution; native and assistive-device acceptance remains |
| 14 | IMPLEMENTED | Every declared frontend API call resolves to a real handler; complete behavior/negative acceptance remains |
| 15 | IMPLEMENTED | CI branch triggers and two real browser modes added; hosted exact-SHA outcome remains |
| 16–17 | DEFERRED | Isolated staging and real-domain promotion/rollback still required; production engine is preserved |
| 18–19 | DEFERRED | Browser and negative checks exist; full accessibility, performance and all account workflows remain |
| 20–22 | IMPLEMENTED | Prompt, evidence boundaries and unresolved work preserved; no full-completion or live-readiness claim |
