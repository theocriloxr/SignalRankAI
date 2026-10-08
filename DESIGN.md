# SignalRankAI institutional interface system

## Product identity
Multi-asset trading research, evidence, paper execution and risk-authorized broker operations. Audience: individual researchers, professional traders, owners/operators. Emotional target: precise, calm, trustworthy, informed. Must never resemble a casino, a broker's proprietary trading terminal clone, or a neon AI effect showcase.

## Authority / brand
Preserve the approved SignalRankAI symbol at `frontend/public/brand/icon.svg`, existing production green/silver palette and Telegram brand. Supporting source of truth: `frontend/src/app/globals.css`. User-supplied blue direction is inspiration only; do not override the approved brand solely to follow a reference template.

## Semantic color and roles
- Ground `--bg: #08120f`; primary surface `--panel: #101e19`; elevated `--panel2: #14251d`.
- Text `--text: #e6eeea`; supporting `--muted: #a5b8ad`; strokes `--line: #294036`.
- Primary control `--accent: #4ce0a4`; on-accent text `--button-text: #071c12`; subdued highlight `--accent2: #bcf4d7`.
- Theme preference `data-theme=dark|light` and system respect existing local control; secondary stylesheet must use the tokens, not hardcode an alternate identity.
- Profit/loss colors **only when accompanied by textual labels**. Never use green as proof of profitability or connection readiness.

## Typography / density
Use current system font stack, 4px spacing units, fluid displays at 30–48px for workspace headings, 12–14px metadata, and tabular numeric currency/percent data. No currency conversion from unknown codes. Never style a missing number as zero.

## Shell and layouts
Desktop: context navigation rail (230–276px) and bounded content canvas with headline, status, dense cards and optional table. Tablet: collapsible semantic menu + 5 major routes. Small mobile: fixed primary bottom links, full-width stacked content with safe-area insets and other routes in the disclosure menu. Breaks at intrinsic 1150, 900, 660 and 360 CSS px.

## Components
`PublicNav`, `AppShell`, `AccountEntry`, `WorkspaceLive`, `ThemeControl`, `SessionExit`. Semantic cards, key/value pairs, scrollable data tables, accessible loading/error/auth/empty presentations. Operability never depends on hover.

## Motion
Tier 0 for money, broker execution, risk and security status. Tier 1 subtle focus/hover feedback only. No perpetual WebGL, forced ticker or action-changing decorative transitions. Reduced-motion turns off transitions.

## Accessibility
Keyboard first; skip link; clear errors and associated form labels; `aria-current` on active nav; visible focus; semantic headings, tables, lists; native mobile disclosure menu; no color-only performance labels; high contrast/forced-color outlines; 320px/200% zoom checks required for certification.

## Approved responsibilities / do not touch
- Business data comes from the **typed canonical** `/api/v1/platform` endpoints through `openapi-fetch` and `platformFetch`; never invent broker balances, fills or signal scores.
- Show actual entitled signals, separately labeled paper records and claim-uncertified performance only.
- Only backend enforces auth, entitlement and execution approval. Client menu visibility is not security.
- No browser storage for access or refresh tokens, no broker credentials in chats, no disabled CSRF, no UI toggle that asserts live-money readiness.
- Do not mutate active staging/prod DB, merge the ongoing recovery PR or deploy from this design branch until security/release gates pass.
