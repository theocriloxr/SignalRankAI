# SignalRankAI candidate release acceptance — 8 October 2026

> This is an evidence ledger, **not** a release authorization. Source inspection,
> passed frontend CI and online older instances do not certify financial execution.

## Source and branch boundaries

- Recovery PR #189: `fix/release-recovery-20261008`, safety + dependency + admission repairs.
- Design PR #190: `design/signalrank-ui-rebuild-20261008`, now carries the recovery parent via an explicit two-parent, conflict-reviewed source-tree merge. It is ahead of its recovery base, not an alternate old main branch.
- `main` and production must not be implicitly advanced. No live-money permission is granted.
- The separate `Regenerate UI branch governance evidence` GitHub Action generated requirements artifacts from the **actual candidate checkout**, checked them and committed only `requirements/` on its exact design branch, with no bypass.

## Verified source and hosted evidence

- UI: real authenticated canonical dashboard, delivered signal/detail, quality rejections, paper records, portfolio, historical evidence, broker connection inventory, billing receipts, owner posture, and account-owned watchlist/support/journal creation.
- Canonical email password, MFA challenge, verification, magic link and password recovery match backend endpoint and link shapes.
- Responsive navigation, gated owner link, safe read-only trading screens, non-indexed/private account routes and explicit unavailable/no-signal states.
- Earlier frontend hosted CI on this PR repeatedly passed clean `npm ci`, lint, TypeScript, `next build`, transport and presentation checks; the exact final source commit needs fresh hosted verification.
- The new `services/broker_routing_policy.py` blocks ambiguous legacy auto-provider execution when more than one eligible canonical account exists without an explicit connection, and blocks unresolvable owner/database state; see `tests/test_canonical_broker_destination_admission.py`. This is a **safety admission repair**, not a complete account-ranking or mirrored multi-broker execution system.

## Live project inspection (read-only)

Railway project `trading-bot-account2` (`5baa1c14-a748-4dc8-8eb6-411c621e56c3`):
- Only environment enumerated: `production` (`05a014d1-73c1-485c-b767-e734c7ea2877`). An independent certified staging environment was **not** present in that Railway project inventory.
- Key runtime services `SignalRankAI`, `striking-optimism`, `bountiful-miracle` and `signalrankai-analytics-prod` were reported **online** even though their latest attempt to deploy older commit `c7684b34` failed on 6 October. The currently serving commit must be verified with runtime release markers; an online status is not proof that candidate PR #190 is deployed.
- Production DB, Redis and PgBouncer were reported online. Several services exposed warnings, and candidate verification services were offline. No variables, credentials, database rows or broker balances were read or modified.
- Vercel account did not list a SignalRank frontend project, so no available preview deployment was assumed or created.

## Hard blockers / acceptance prerequisites (do not waive)

1. Mobile `node-forge` and inheriting `expo`, `@expo/cli`, `@expo/code-signing-certificates` remain four high-severity dependency audit findings. Reviewed advisory [GHSA-86w9-cpqp-85rv](https://github.com/advisories/GHSA-86w9-cpqp-85rv) affects all versions through 1.4.0 with **no patched release** as of 8 October 2026. Do not accept an advisory exclusion, renamed dependency or unverified cryptography fork as a security fix.
2. Run full candidate CI including Python 3.11/3.12 backend, static/security, generated governance, frontend, native/mobile, release-manifest, research/browser tests and no-skips requirements on the **same immutable SHA**.
3. Provision **isolated** staging Postgres/Redis, explicit stage services and environment variables; prove that no production DB, tokens or queues can be touched.
4. Run real read-only broker discovery, demo account linking, provider server validation, demo/manual policy and connection-level test fills/partial exits/breakeven before considering any live execution.
5. Prove the full account risk/venue, leverage, drawdown, symbol identity, routing and prop-rule matrix; implement `SINGLE_BEST_ACCOUNT`, `PRIORITY_FALLBACK`, `MIRROR_SELECTED_ACCOUNTS`, `SPLIT_TOTAL_RISK` and `PER_ACCOUNT_RISK` independently of legacy auto-provider fallback. A single defensive ambiguity block is not complete multi-broker routing.
6. Native Android/iOS build and physical-device acceptance; mobile UI parity and accessibility across devices and color themes.
7. Confirm production backups/restores, provider coverage at actual market opens, immutable release identity, 24–72 hours **clean** staging soak and two complete audits without material gaps.
8. Independently read the referenced research Google document; it was not available in the recovery environment. Unreviewed information must not be fabricated.

## Operator instructions

- Keep PR #189 and #190 in DRAFT pending complete evidence and reconciliation.
- Do **not** merge a red CI, change a kill switch, enable live trading, promote unverified DB migrations or label synthetic paper outcomes as broker fills.
- Once a compatible audited mobile dependency remediation exists, rerun lock+audit+native builds and the immutable full release pipeline. Revisit provider/demo blockers with owned sandbox access and explicit owner approvals.
