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
