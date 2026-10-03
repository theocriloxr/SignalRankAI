# Trading workspace refresh and launch gates — 3 October 2026

Branch: `fix/provider-discovery-readiness-20260923`.
**Launch status: blocked. Live and funded-prop execution remain disabled.**

## Implemented product changes

The functional FastAPI portal in `web/platform_app` uses the original logo,
emerald and silver branding, restrained surfaces, clearer headings, readable
data, explicit paper labels and larger controls. Shared styles cover every view
and account tier. Account section links and a compact profile form reduce the
effort of finding broker, policy, notification, security and billing controls.

System, Light and Dark preferences persist. System follows the device preference.
Theme labels and browser chrome stay synchronized. Keyboard focus, a skip link,
selected sign-in tabs and current-navigation semantics improve accessibility.
Unavailable analytics stay discoverable, with upgrade guidance; server
entitlements and execution checks continue to enforce access. Missing dashboard
measurements display an em dash rather than a fabricated zero. Empty signal and
paper states explain the next useful action without inventing performance.

The parallel Next frontend uses the same themes and original icon. Its public
pipeline illustration is labelled METHOD rather than suggesting a connected
LIVE status. This descriptive shell does not replace the authenticated FastAPI
application or certify end-to-end trading functionality.

The service worker caches only the public shell and exact public assets. API,
diagnostic, authentication and third-party requests bypass interception. It
does not cache requested navigation URLs containing activation tokens; offline
navigation uses the clean public shell. Failed or redirected asset responses
are not cached. Upgrade cleanup preserves unrelated application caches.

## Design references and analysis

- [Lollypop trading-app design](https://lollypop.design/blog/2026/june/trading-app-design/): clear information hierarchy, readable market data and explicit transaction feedback informed the changes.
- [Dribbble trading-platform collection](https://dribbble.com/search/trading-platform-ui): navigation, data alignment and restrained surface hierarchy informed the direction.
- [Behance trading-platform collection](https://www.behance.net/search/projects/trading%20app%20design): the collection returned 403; individual project descriptions were searchable. No inaccessible image is claimed as reviewed.
- [Blueberry Funded](https://blueberryfunded.com/home/) and [IUX](https://www.iux.com/en/landing): product and account information organization informed presentation, without copying account rules or marketing performance claims.
- The supplied 99designs project was unavailable. The first Google advertisement had no visible destination; it supplied no usable design evidence.

Three standalone mockups were generated with the built-in image tool before
implementation: dark desktop overview, light account view and mobile overview.
Their 240px sidebar, 32px desktop/16px mobile gutters, emerald actions, silver
text, restrained corners and readable empty states formed the visual reference.
Generated metric labels and suggested profile fields were reconciled with real
API capabilities. The original logo was preserved rather than regenerated.
Preview references and actual browser screenshots are in the ignored
`artifacts/ui-refresh-20261003` directories; they are not product assets.

## Verification scope

HTTP throttling now returns the intended 429 JSON response and Retry-After
header rather than propagating a middleware exception as HTTP 500. Three
actual TestClient regressions cover page/API throttling and available liveness.
Cache-generation validation rejects mixed HTML/worker assets, obsolete caches
and missing files; historical asset checks now permit coherent newer releases.
The targeted regression selection passed 75 checks after these changes.
Full-suite and exact-commit browser reruns are required before release approval;
the earlier exact 46472b4d browser run exposed this throttling defect.

- Actual local HTTP login with synthetic users and a disposable PostgreSQL
  database: 47 browser checks passed, including all seven tiers, server-side
  rejection of Free portfolio access, operator authority, desktop/mobile
  navigation, theme persistence, device preference changes and session revocation.
- Automated WCAG A/AA checks reported zero violations across audited states.
  These do not replace manual assistive-technology or native-device acceptance.
- Four executable service-worker regressions passed, covering private-request
  exclusion, allowed assets, offline fallbacks and cache isolation.
- Portal runtime, per-account prop policy and financial activation regression
  selection: 69 passed.
- Next frontend lint, TypeScript and production build passed locally. React
  component review retains server rendering and isolates browser storage in a
  small client component with cleaned-up event subscriptions.

These results are local candidate verification, not production or broker
certification. Synthetic paper balances in screenshots are local test fixtures.

## Gates still blocking launch

| Gate | Current evidence | Required completion |
| --- | --- | --- |
| Production capacity/schema | 4.50 GB volume usage on 5 GB; schema 0045; 0046 copies a 1.50 GB relation | Expand capacity to at least 10 GB, verify backup/restore and migrate under the capacity guard |
| Immutable production rollout | Core services recovered on 8f858393, older than this branch | Deploy and verify one exact candidate across application roles after migration |
| Hosted CI | Earlier exact candidate could not start jobs because of account billing lock | Resolve GitHub billing and pass hosted CI on the actual release commit |
| Frontend/mobile security | Actual npm gates: frontend 5 high; mobile 16 high + 7 moderate | Resolve advisory exposure with verified compatible fixes; keep security gates active |
| Static coverage/typing | Semgrep incomplete taint analysis; 1,424 legacy typing errors in earlier candidate | Complete analysis and resolve remaining typing debt; rerun on release source |
| Data providers | Latest actual certificate passed crypto only; FX/index/metal empty; equity stale | Obtain suitable provider entitlement/budget and certify real data during applicable market sessions |
| Funded prop accounts | Testers use different firms; no blanket account certificate | Configure and verify each account's exact rules, loss baselines, reset timezone and automation permission |
| Broker execution | No current actual fills/partial exits/breakeven certificate | Certify demo execution and reconciliation before funded activation |
| Recovery and operations | Complete release-specific Redis/kill/retry/crash/restore evidence incomplete | Complete controlled failure drills, restore, monitoring and retention acceptance |
| Device acceptance and soak | Native-device acceptance, 24–72-hour soak and two clean audits incomplete | Finish actual acceptance and sustained evidence; elapsed time cannot be fabricated |

Sandbox npm commands briefly returned zero findings, but unrestricted registry
and subprocess checks reproduced the failures. The zero reports are not
accepted as vulnerability resolution. Installed braces 3.0.3 and node-forge
1.4.0 still match the current affected ranges in
[GHSA-vfj7-8cjw-p6xm](https://github.com/advisories/GHSA-vfj7-8cjw-p6xm) and
[GHSA-86w9-cpqp-85rv](https://github.com/advisories/GHSA-86w9-cpqp-85rv).
Neither advisory lists a patched version at this observation. No forced
framework downgrade, audit exception, freshness exemption or financial
activation was applied to make a gate appear green.
