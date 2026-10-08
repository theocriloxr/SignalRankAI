# SignalRankAI responsive acceptance

Minimum audit widths: 320,360,375,390,412,430,768,1024,1280,1440,1920 CSS px; 200% zoom and short landscape viewports.

- Desktop: navigation rail and dense two-column signal evidence; table body scrolls within a named, keyboard-focusable region.
- Tablet: disclosure menu and sticky bottom primary navigation only when constrained; no 15-link forced horizontal strip.
- Mobile: touch-friendly 44px targets, 5 high-value destinations, safe-area padded bottom bar, full-width reading order; form inputs must remain readable without horizontal scrolling.
- No financial, signal or broker-critical detail behind hover, canvas or collapsed status.
- Dark/light/system should retain brand integrity, visible focus and readable contrast; `prefers-reduced-motion` disables unnecessary effects.
- Manual checkpoints: sticky overlaps, iOS keyboard viewport, 320px, long symbol/account names, big decimal prices, empty/denied/offline/no-signal, chart/table overflow and 200% zoom.

Implemented CSS in `frontend/src/app/workspace-design.css`; device/browser certification not yet performed.
