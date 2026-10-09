# SignalRankAI redesign integration — 9 October 2026

Candidate: design/signalrank-ui-rebuild-20261008, draft PR #190. Recovery merge #191 incorporated with two parents in 7a9513b4942b8031f37a0b9962e1c238f28f6159. Main and production remain unchanged.

## Implemented web design and capability inventory

| Surface | Implementation | Verification boundary |
|---|---|---|
| Public site | Branded emerald/silver pages, shared responsive menu, keyboard/outside dismissal, dark/light/system themes | Native visual inspection not completed |
| Identity | Registration, login, MFA, email verification, magic link and password recovery | Staging end-to-end session and outbound-email proof pending |
| Browser session | Same-origin canonical API proxy and CSRF with safe single-flight GET refresh; never replay a write after 401 | Backend cookie/proxy/browser proof pending |
| Overview | Account-delivered signals, paper account and entitlement overview | Test with real staging session required |
| Signals | Receipt-backed history/filter/pagination, entitled ML lifecycle and outcome proof; no broker fill inference | Telegram/web parity and receipt checks pending |
| Markets | Multi-asset instrument directory with provider mappings and ML gate diagnostics; no synthetic quotes | Open-market provider proof pending |
| Research | Existing strategy leaderboard and merged adaptive research fixes | Full advanced research/SPA parity incomplete |
| Watchlists | Server-owned creation, canonical instrument selection and addition | Real staging persistence pending |
| Alerts and notifications | Rule management, read receipts, selected channel preference updates | Actual delivery/provider tests pending |
| Paper desk | Simulated positions, history, bounded settings, explicit reset/close/retry confirmation | Simulated state and crash recovery testing pending |
| Paper portfolio | Canonical timestamped virtual-equity chart and accessible ledger table | Device/visual QA pending |
| Performance | User-owned historical trade ledger, uncertified historical claims labeled | Real outcome proof and audits pending |
| Journal | Account-owned reflections and two-step deletion, no self-report as broker proof | Authz/browser QA pending |
| Brokers | Independent per-account policy, decimal-risk percentages, ledger, verification, safety freeze | Real provider/prop demonstration pending |
| Demo MetaTrader linking | Canonical known-server search, secure provider URL with browser-host visibility, demo-only connection request, no credential capture | MetaApi capacity, return/verify and demo certification pending |
| Billing | Authenticated subscription and receipt inventory | Checkout/cancel provider workflows still in legacy SPA |
| Support | Owned ticket list, replies and creation | Authenticated device testing pending |
| Settings and security | Signal preferences, profile, email verification, MFA setup with one-time codes retained until acknowledgment, session management | Manual MFA/device QA pending |
| Operations | Role-authorized owner navigation and read-only posture | Mutating operator tools remain in legacy SPA; preserve until verified cutover |
| FastAPI SPA | Existing richer workflows retained; latest recovery adaptive-health responsive/mobile styles merged | Production is serving older candidate |
| Expo mobile | Independent native code and redesigned navigation | Four high mobile audit issues and physical-device QA block release |

## Design, safety and provenance rules

Preserve approved dark/light emerald/silver palette; responsive widths 320 to 1920 CSS px, 200% zoom, reduced motion, forced colors, screen reader and real iOS/Android QA require rendered verification. Use native readable charts; avoid casino-like live tickers and purchased unlicensed effect assets. Unknown currency, balances or broker P&L must not become zero/NGN/USD by assumption.

Broker policy percentage values are decimal fractions: 0.005 means 0.5 percent, not 0.005 percent. Each broker account has its own connection ID and risk policy, with no automatic mirroring or execution. Paper history is simulated; delivery receipts never prove actual fills. Secure demo links never activate trading; freezes disable new execution only.

## Release requirements still unverified

1. Hosted CI on the exact final immutable commit, including frontend, Python 3.11/3.12, governance, static, research, native/mobile and npm audit. Earlier frontend CI has passed, but newer commits require exact-head results.
2. Expo and transitive node-forge remain blocked by four high-severity dependency advisories with no audited patched release at last inspection. Do not bypass or waive security.
3. Design-branch governance generator must recalculate requirements/legacy_disposition.json after source changes; never hand-edit its hashes or disable the check.
4. Railway SignalRank project trading-bot-account2 had production only and no isolated staging at last inspection. Main app remained online on an older successful release after a failed newer deployment attempt.
5. FastAPI SPA and Next.js both currently own /app. Execute docs/WEB_SURFACE_CUTOVER_RUNBOOK.md and service-worker handoff with rollback, no production branch promotion without independent staging.
6. Connect and verify a real provider-backed staging demo, show fills/partial exit/broker-confirmed breakeven, closed-market data behavior, kill-switch, crash recovery, Redis/DB isolation, retention, backup+restore.
7. Complete 24–72 hours of clean isolated staging soak and two reviews with no material gaps. Only then assess live/prop readiness; no current source patch authorizes real execution.

Links: https://github.com/theocriloxr/SignalRankAI/pull/190 and https://github.com/theocriloxr/SignalRankAI/pull/191

Statuses above denote source implementation only. No screenshots, runtime account sessions, actual broker fills, mobile binary install or production cutover are claimed.