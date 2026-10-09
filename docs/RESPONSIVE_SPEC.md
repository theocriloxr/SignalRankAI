# SignalRankAI responsive acceptance

Minimum audit widths: 320,360,375,390,412,430,768,1024,1280,1440,1920 CSS px; 200% zoom and short landscape viewports.

- Desktop: navigation rail and dense two-column signal evidence; table body scrolls within a named, keyboard-focusable region.
- Tablet: disclosure menu and sticky bottom primary navigation only when constrained; no 15-link forced horizontal strip.
- Mobile: touch-friendly 44px targets, 5 high-value destinations, safe-area padded bottom bar, full-width reading order; form inputs must remain readable without horizontal scrolling.
- No financial, signal or broker-critical detail behind hover, canvas or collapsed status.
- Dark/light/system should retain brand integrity, visible focus and readable contrast; `prefers-reduced-motion` disables unnecessary effects.
- Manual checkpoints: sticky overlaps, iOS keyboard viewport, 320px, long symbol/account names, big decimal prices, empty/denied/offline/no-signal, chart/table overflow and 200% zoom.

Implemented CSS in `frontend/src/app/workspace-design.css`; device/browser certification not yet performed.


## Public editorial and native additions — 9 October 2026

Public web now has dedicated original `public-design.css` for a cinematic but static, low-overhead typography-and-system-grid visual hierarchy. It adapts at 1050, 800 and 600 CSS px, preserves forced-color borders, and uses no external asset or animation dependency. Required visual review remains at 320, 360, 375, 390, 412, 430, 768, 1024, 1280, 1440 and 1920 widths and 200% zoom, including unusually long instrument/plan labels.

Native Expo app's four principal destinations appear in a bottom tab bar and all remaining destinations in a scrollable secondary menu rather than an overflowing horizontal set of tabs. Account screens use flexible rows and touch controls with ≥44px hit areas. System light/dark palettes transform surfaces and text based on `useColorScheme`; native device tests are still required at larger system fonts and VoiceOver/TalkBack.

The status page is an explanatory operational-readiness reference, **not** an invented live health feed. The marketing systems illustration is marked as conceptual and has no synthetic financial statistics. No responsive screenshot has been signed off as VERIFIED at this stage.
