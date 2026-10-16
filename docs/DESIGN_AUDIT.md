# SignalRankAI design and functionality audit

## Current implementation
- Backend API: `web/platform_api.py`, typed `frontend/src/lib/api.d.ts`; cookie/CSRF transport in `frontend/src/lib/transport.ts`.
- Frontend: Next 16.3.8 in `frontend/`; routes `/`, single-slug public informational pages, `/app`, dynamic `/app/[...slug]`, and now `/login`.
- Mobile: independent Expo app `mobile/`; remains outside this initial web styling slice.
- Existing site already has approved icon and persisted system/light/dark theme.
- Previously `/app` and its 14 section routes displayed **unbound explanatory cards** rather than account-backed API results. Section URL alone did not prove authenticated data. There were no dedicated email login/register/MFA screens in this separate Next frontend.
- Existing branch is a recovery candidate, not a signed release.

## Risks
1. Public informational screens and signed-in workspace blurred; no real account state in terminal cards.
2. Desktop nav was long and scrolling on mobile; public links vanished under 900px.
3. Missing loading, session-expired, entitled-denied, no-data and canonical-service-failed states.
4. Unqualified "0" or fake currency would mislead in trading decisions.
5. Broker connection can be confused with authorization to execute; paper equity cannot be presented as consolidated real broker funds.
6. Owner operations must be backend-protected; frontend may additionally hide restricted data but cannot grant access.
7. Full visual/browser/device testing, staging demo connection, multi-broker lifecycle and broker/prop certification remain outside confirmed evidence.

## Implemented in this branch
- Live, account-gated overview; entitled delivered signals/detail; paper; portfolio; historical performance; broker listing; server-priced billing history; quality reporting; operations release readout; journal/support/watchlist/alert read-only views.
- Backend MFA-aware email login/register, session-verifying redirect and confirmed logout.
- Grouped desktop/mobile navigation, skip link, focus/empty/permission/error states, scannable responsive tables, public mobile navigation.
- No backend write, broker execution action, quote/fill fabrication or dark/light override introduced.

## Remaining truthful boundaries
- Browser runtime and full Next production bundle unverified until hosted CI or a genuine checkout becomes available.
- API base origin, cookie policy, and deployment variables require real staging verification; not assumed functional based on types alone.
- More complex editable settings, broker linking/certification, paper controls, password reset and full Telegram-parity workflows require implementation and tested approvals; don't fake buttons for these.
