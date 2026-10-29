# SignalRankAI accessibility

Target WCAG 2.2 AA; certification requires rendered manual/accessibility-tool review, not only source code.

- Native landmarks (main, nav, header, aside), skip to main, semantic headings, table headers, status messaging.
- Log in with labels/autocomplete, no password prefill or storage, MFA code accessible and ephemeral.
- Auth, network failure, 403 tier restriction and empty/no-trade states have descriptive text, not color alone.
- App navigation active link uses `aria-current`; mobile drawer `details/summary`; focus outlines visible.
- Financial amounts show the actual currency or Unavailable; missing numbers never zero; precision and uncertainty visible.
- Scrollable tables keyboard-focusable with accessible names.
- Never auto-place orders from navigation or release a kill switch from a public UI.
- Reduced motion and forced-colors tested on real browsers before marking VERIFIED.

No full screen-reader/device audit yet because the complete current branch has not built in a reachable runtime.

## Automated audit, 29 October 2026

Run with `python scripts/a11y_audit.py --base http://localhost:3100 --out audit.json`. The script refuses any non-local host and reads `A11Y_EMAIL` and `A11Y_PASSWORD` for a local test account. It runs axe-core's WCAG 2.0/2.1/2.2 A and AA rules in headless Chromium on 40 pages: 19 public pages, the 5 other legal pages and 16 workspace sections. Each page is checked in light and dark themes at 1280 px and 375 px. A 320 px pass then checks reflow (no sideways scrolling), that a skip link comes first wherever three or more controls precede the main heading, that it is visibly focused, and that activating it moves focus.

| | Before fixes | After fixes |
| --- | --- | --- |
| Runs | 140 (axe only) | 200 (axe + keyboard/reflow) |
| Runs with violations | 128 | 0 |
| Failing elements | 1,067 colour contrast, 62 accessible-name mismatch | none |

Fixed:

- The muted-text tokens are now `#5d6877` (light) and `#8a95a1` (dark), at least 4.8:1 and 5.3:1 on every surface. They were 3.75:1 and 4.22:1.
- The menu's accessible name now starts with its visible word ("Menu: …").
- Public pages now have a "Skip to content" link.
- The legal pages' credit link name no longer contains a mis-encoded "?".

`frontend/scripts/accessibility.test.mjs` recomputes the contrast from `tokens.css` and checks the skip link and menu name. Evidence: `docs/release/evidence/continuation-20261029/a11y_audit.json`.

Still not done: screen-reader passes (NVDA, VoiceOver, TalkBack), full keyboard-only task journeys, 200% text zoom, forced-colours and real-device checks. Automated rules find roughly a third of WCAG issues, so this audit is not an accessibility certification.

