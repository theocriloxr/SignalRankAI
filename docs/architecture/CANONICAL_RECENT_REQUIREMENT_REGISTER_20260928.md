# SignalRankAI Canonical Recent-Request Register — 2026-09-28

This register makes the latest cross-chat requirements explicit in the repository so branch consolidation cannot silently drop them.

## Canonical branch contract

- `main` is the only production release branch.
- `staging` is the only staging development/release branch.
- Legacy branches are evidence/history only once their unique work is either merged or superseded.
- Production claims require repository tests plus runtime evidence; branch names alone are not proof.

## Recent-request requirements

| ID | Requirement | Status | Canonical evidence |
|---|---|---|---|
| SR-RECENT-001 | Web refresh must restore a valid session without flashing login/home; genuine service outages must not masquerade as logout. | VERIFIED | `web/platform_app/app.js` refresh-cookie bootstrap + outage state; `tests/test_site_account_billing_hardening_20260928.py` |
| SR-RECENT-002 | MetaApi secure-link account creation must be stored immediately and automatically reconciled when the user returns; normal connection and secure-link flows must converge on the same canonical broker account. | VERIFIED | `web/platform_app/app.js`, `web/platform_api.py`, `services/mt5_client.py`; secure-link reconciliation tests |
| SR-RECENT-003 | Multiple MT4/MT5 accounts per user; account-scoped risk/policy/execution; explicit account selection when ambiguous. | VERIFIED | `db/mt5_models.py`, broker account selection/router services, `tests/test_multi_account_prop_policy.py`, `tests/test_broker_account_bola_idor.py` |
| SR-RECENT-004 | Broker execution is never implied by connection. Only delivery-proven signals for that canonical user/account are eligible and every execution path stays behind risk, quote, consent, quota, reconciliation and global kill-switch gates. | VERIFIED | web signal execution, Telegram account selection, execution claims/evidence tests, account UI safety copy |
| SR-RECENT-005 | SignalRank market coverage must include crypto, FX, indices, equities/stocks and commodities rather than crypto-only behavior. | VERIFIED | `core/asset_classes.py`, profile demand/universe, provider registry/discovery, runtime readiness probe, multi-asset profile UI |
| SR-RECENT-006 | Learning must cover the full decision surface: issued, rejected, skipped/delayed/suppressed decisions and tracked shadow outcomes—not only completed trades. | VERIFIED | decision intelligence, rejection learning, shadow outcome tracker, `ml/train_model.py`, improvement register |
| SR-RECENT-007 | OpenAI must be a first-class production provider with governance, caching/rate budgets/circuit state and provider fallback, not an ad-hoc Gemini replacement. | VERIFIED | `services/openai_ai.py`, provider order, owner AI diagnostics/tests |
| SR-RECENT-008 | Paid plans must launch a server-priced Paystack checkout; callback/return must reconcile provider-verified payment metadata idempotently; browser-supplied tier/amount/user identity is never trusted. | VERIFIED | `payments/checkout.py`, `payments/paystack.py`, `web/platform_api.py:/billing/confirm`, `/billing/complete` SPA route |
| SR-RECENT-009 | Website visibility/actions must respect the same tier/owner authority as Telegram and the backend; locked features must not be presented as usable. | VERIFIED | `core/tier_policy.py`, `/entitlements`, entitlement-aware navigation, full command catalogue |
| SR-RECENT-010 | Telegram-created accounts and web-created accounts must converge cleanly; app/login-code activation, linking and device/security flows must not repeatedly prompt already linked users. | VERIFIED | command catalogue account commands, platform auth/link routes, account UI |
| SR-RECENT-011 | Website must expose the complete tier-filtered Telegram capability catalogue, not the Telegram BotFather 100-command menu limit. | VERIFIED | `/command-catalog` iterates canonical `COMMANDS` directly; web command centre |
| SR-RECENT-012 | Owner/admin Telegram operations must have web parity where operationally appropriate: diagnostics, AI provider status/test, release/runtime identity, kill switch, maintenance/rebuild/replay/adaptive controls, market scan and operator-only diagnostic signal generation. | VERIFIED | `/operator/*` routes, Operations view, confirmed/audited mutation controls |
| SR-RECENT-013 | Site must be redesigned as a professional multi-asset trading/intelligence workstation with responsive desktop/tablet/mobile navigation, persistent dark/light theme and dense data views rather than a generic marketing dashboard. | VERIFIED | `web/platform_app/index.html`, `styles.css`, `app.js`, PWA shell v30 |
| SR-RECENT-014 | Email identity for user-facing SignalRank transactional mail is `SignalRankAI <hello@criloxsolutions.com>` with replies to the same mailbox. | CODE VERIFIED / EXTERNAL SECRET REQUIRED | `services/platform/email_delivery.py`; Railway sender/TLS/username settings. Delivery remains intentionally disabled until the mailbox SMTP password is supplied. |
| SR-RECENT-015 | Performance truth reconciliation must not be blocked by a slow notification-outbox repair; analytics DB backpressure is an expected deferral, not a crash. | VERIFIED | worker reconciliation ordering and shadow tracker deferral handling; canonical consolidation tests |
| SR-RECENT-016 | Production/staging release source must be branch/commit pinned, schema gated and reversible; wrong-source deployments must fail closed. | VERIFIED IN CODE / RAILWAY SOURCE-SELECTOR MANUAL STEP PENDING | release-source gate and expected commit variables. Railway MCP source-branch mutation is currently blocked by Railway Agent quota. |

## Product-design benchmark principles applied

The workstation design deliberately borrows interaction principles—not branding or copied layouts—from established market tools:
- high-density customizable market dashboards and saved views;
- persistent market/account navigation;
- fast access to watchlists, alerts and analysis without leaving the core workspace;
- explicit separation between analysis, execution and account/risk state;
- responsive/touch-friendly layouts and dark/light themes.

## External configuration still outside repository control

The repository must not contain mailbox passwords, provider keys, broker secrets, Telegram tokens or payment secrets. Missing external values are reported from Railway separately; no secret is guessed or committed.
