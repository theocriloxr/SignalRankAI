# SignalRankAI UI rebuild baseline — 2026-10-08

- Target: `theocriloxr/SignalRankAI`. Default branch: `main`, inspected at `98a5de18f92674c9e70ec61a802391bf984de8d6`.
- **Do not** use main directly as the redesign baseline: it is 587 commits behind the active recovery branch.
- **Canonical cumulative implementation/recovery source selected**: `fix/release-recovery-20261008` at `ae6a6fb4aab968187a4a3aa5e9a8fde807fc33f2`; has 1 recovery commit ahead of `fix/provider-discovery-readiness-20260923` (`c7684b34178be6d69960c89b42a2805d6ccfb3ab`) containing frontend supply-chain, mobile, backup and certification repairs.
- Dedicated implementation branch: `design/signalrank-ui-rebuild-20261008`, created at the **exact** recovery SHA above.
- Active recovery review: GitHub draft PR #189. **Do not merge this UI branch directly into main before the recovery source is reconciled and security gates pass.**
- Inspected: `main`, `staging` (9 behind main), `implementation-of-master-blueprint` (550 ahead of main, but 39 recovery commits behind and 2 independently ahead), `feat/master-blueprint-production-completion-20261001`, `feat/final-workstation-redesign-20260928`, `fix/provider-discovery-readiness-20260923`, `fix/release-recovery-20261008`.
- `implementation-of-master-blueprint` must receive **selective** evidence-based reconciliation of its 2 divergent commits; no wholesale merge. The recovery branch includes dependency/backup fixes absent from that older branch.
- Existing immutable controls untouched: broker trade enablement, per-account authorization, CSRF/session, MFA, fail-closed risk, live-money feature gate, receipt ledger, migration gates, staging versus production isolation and Telegram parity.
- Older `archive/*` and `backup/*` branches are historical, not release candidates.

**Verification status**: source compare and branch topology checked through GitHub. Live service, native app and fresh soak evidence are separate external release requirements, not implied by Git history.
