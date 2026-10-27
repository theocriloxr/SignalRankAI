# SIGNALRANKAI — COMPLETE ECOSYSTEM FRONTEND REBUILD, INTEGRATION, PRODUCTION MERGE AND RAILWAY DEPLOYMENT

## 1. YOUR ROLE AND PRIMARY OBJECTIVE

You are the lead full-stack engineer, senior UI/UX designer, software architect, security engineer, QA engineer and DevOps engineer responsible for completing **SignalRankAI**.

**Repository:** `theocriloxr/SignalRankAI`

**Production website:**
- https://www.signalrank.criloxsolutions.com
- https://signalrank.criloxsolutions.com

**Hosting:** Railway, with existing application services, PostgreSQL, Redis, workers and associated infrastructure.

**Owner/developer:** CRILOX Solutions.

Your mission is to:

1. Recover and reconcile all relevant frontend and backend work from the latest branches and pull requests.
2. Completely redesign, improve and restructure the SignalRankAI website and authenticated trading workspace.
3. Build a coherent, premium, responsive user experience suitable for the **entire SignalRankAI ecosystem**, not merely a marketing landing page.
4. Complete missing, partially implemented, disconnected or malfunctioning frontend functionality.
5. Integrate every frontend operation with the correct canonical backend API and permissions.
6. Resolve outstanding UI, API, authentication, routing, deployment, reliability, performance and accessibility problems.
7. Restore and pass the required CI, tests and release governance.
8. Merge the finished work into the appropriate canonical release branch, reconcile it with production, and deploy the verified result to **Railway**.
9. Confirm the real production domains actually serve the new frontend.
10. Produce evidence of what is working, what was tested, and anything legitimately blocked by external requirements.

**This is an implementation task, not a planning-only, design-mockup-only or documentation-only task.**

Continue working through the repository, making and validating changes. Do not stop after providing a list of recommendations, producing screenshots, creating a preview deployment, or opening an unmerged PR.

At the same time, do not bypass trading safeguards, falsify certification, or claim tasks requiring real elapsed time or external authorization are complete when they are not.

---

## 2. UNDERSTAND THE EXISTING REPOSITORY AND BRANCHES FIRST

The project contains divergent frontend, backend and release-development histories.

The following were observed previously, but **you must independently verify their current status**:

- Production Railway branch: `fix/provider-discovery-readiness-20260923`
- Previously observed production commit: `9865a3d1bcee632bfd9347e50d5de34d355225d9`
- Production application service: `SignalRankAI`
- Next.js frontend integration branch: `design/signalrank-ui-rebuild-20261008`
- Frontend integration PR: `#190`
- Cinematic frontend redesign PR: `#200`
- PR #200 was merged into the Next.js integration branch, **not into the live Railway production deployment**.
- Previous integration merge commit: `f7ca87be51cad7f048b20b21e92437024104dc4b`
- Release-recovery work: `fix/release-recovery-20261008`
- Other historical audited implementation and master-blueprint branches also exist.
- Production has historically had schema-version divergence from more recent unreleased candidates.
- Previous GitHub Actions runs failed on governance/manifest checks.
- A separate Next.js Vercel preview existed, but this did not constitute production deployment.

### Required actions

1. Fetch all remotes and inspect all relevant branches, commits, pull requests and deployment histories.
2. Determine the **actual commit currently deployed on Railway**, not merely what `main` contains.
3. Identify the canonical release branch and all divergent commits that remain relevant.
4. Compare production, `main`, the release-recovery branch, the Next.js integration branch, and other open or recently merged implementation branches.
5. Build a branch-reconciliation report with:
   - Production baseline
   - Missing commits
   - Overlapping implementations
   - Regressions and conflicts
   - Database migration differences
   - Frontend/API contract differences
   - Release governance dependencies
6. Create an appropriately named integration/release branch from the verified deployed baseline or another demonstrated safe common ancestor.
7. Carefully integrate the approved functionality from the divergent branches.
8. Resolve conflicts semantically. Do not blindly accept entire files from one branch over another.
9. Preserve all valid security, data-integrity, trading-risk, audit and infrastructure improvements.
10. Avoid force-pushing protected branches, deleting necessary history or overwriting production databases.

The final release must contain the new frontend **and** all necessary compatible backend functionality.

**Do not assume that merging PR #190 or switching Railway's source branch is automatically safe.**

---

## 3. DESIGN VISION — REBUILD SIGNALRANKAI AS A PREMIUM TRADING INTELLIGENCE ECOSYSTEM

The website must feel like an advanced, credible, institutional-grade financial intelligence platform.

It should combine:

- The precision of a professional trading terminal.
- The usability of a carefully designed SaaS workspace.
- The visual quality of modern premium interactive websites.
- The depth of a sophisticated multi-asset research platform.
- The clarity required for high-risk financial decision-making.

The final product must **not** look like a generic admin dashboard, ordinary Bootstrap template, cryptocurrency landing-page clone or collection of disconnected cards.

Use the real SignalRankAI identity and logo.

### Brand and colour requirements

Inspect the actual SignalRankAI logo assets and existing branding before choosing the final palette.

Use a cohesive design system based on:

- Deep graphite, charcoal and near-black surfaces.
- The actual SignalRankAI emerald/green brand accents.
- Refined silver, off-white and neutral text.
- Carefully controlled gradients and subtle light effects.
- Distinct semantic colours for positive, negative, pending, rejected, simulated and verified financial states.

Support properly implemented **dark and light modes**.

Do not copy the cyan/lilac palette of the CRILOX Solutions corporate website into SignalRankAI. CRILOX is the developer attribution, not the SignalRankAI product brand.

All colours must meet appropriate accessibility contrast standards.

Text must always be legible without hovering.

---

## 4. LEARN FROM AND APPLY THE DESIGN REFERENCE MATERIALS

Study the available resources below before implementing the final design.

### Direct references

**Figma community reference**
https://www.figma.com/community/file/1653226930367948409

**Framer assets**
https://app.notion.com/p/Free-framer-asset-3aeaeb385d3a80f1ab31dd0c89d90f9d

**Creative websites collection**
https://app.notion.com/p/Creative-sites-PT-19-3e9aeb385d3a801e9bc8e766899825e9

**Google Drive references**
https://drive.google.com/file/d/18SDShlp7GOlPRvy8H900fVpDv_WIIoo0/view

https://drive.google.com/file/d/125_UV3VoU2qgJ068gduQCM5Pag6caBH0/view

**GetLayers**
https://www.getlayers.ai/

**BYFLOWWW**
https://byflowww.com/

**Weblance**
https://www.skool.com/weblance

**UI libraries collection**
https://whimsical.com/tharender/ui-libraries-FwjFih23QGyBWMhN2MnMSZ

**Framer scroll-animation guide**
https://framer.university/blog/10-scroll-animations-to-make-your-website-stand-out

**Additional animation references**
https://www.framer.com/marketplace/components/ripple-background/

https://hover-force.learnframer.site/

https://framer.university/resources/hover-force-component-for-framer

https://www.framer.com/marketplace/components/magnetizinglines/

https://framer.university/resources/hover-chroma-backgrounds-in-framer

Review any available previously attached reference videos and design materials in the workspace.

If a reference is inaccessible, record that limitation. Do not claim to have reviewed private course lessons or inaccessible files.

Learn from composition, animation timing, microinteractions, lighting, transition choreography, layout structure and visual storytelling. Create **original SignalRankAI implementations** rather than copying protected assets or another site's branding.

Use suitable established libraries where they improve quality, but avoid unnecessary dependencies.

Potential implementation tools include existing React/Next.js tooling, Motion, GSAP with ScrollTrigger, Three.js/React Three Fiber, and appropriate accessible UI primitives. Choose them based on the existing stack and performance requirements.

---

## 5. COMPLETELY REBUILD THE PUBLIC WEBSITE

Create a high-quality marketing and product-information experience containing:

### Cinematic homepage

Build an exceptional homepage with:

- Strong typography and a distinctive hero composition.
- Real SignalRankAI branding.
- A sophisticated interactive terminal illustration.
- Clear messaging explaining what SignalRankAI does.
- Well-designed calls to action.
- Meaningful product demonstrations.
- Elegant animated transitions.
- Appropriate risk disclosures.
- Actual navigation into the application.

### Scroll-driven product assembly

Implement a premium sticky-scroll animation that visually demonstrates how SignalRankAI operates.

**Suggested sequence:**

1. **Market Intelligence** — Multi-asset market data enters the platform.
2. **Strategy Analysis** — Strategies and market structure generate candidate opportunities.
3. **AI Evaluation** — Models and validation systems evaluate available evidence.
4. **Risk Management** — Eligibility, account limits, execution permissions and risk controls are enforced.
5. **Signal Generation** — Qualified signals enter the delivery lifecycle.
6. **Delivery and Monitoring** — Telegram/web receipts, position monitoring and user notifications.
7. **Learning and Outcome Analysis** — Observed outcomes, performance evidence and model-improvement feedback.

As the visitor scrolls, interface modules should assemble, transform and connect.

Use meaningful transformations rather than floating empty rectangles or repeating decorative animations.

The experience must work in reverse when scrolling upward.

Do not imply that rejected signals, simulated executions or broker fills actually occurred if no supporting records exist.

Provide reduced-motion and non-WebGL alternatives.

### Additional public pages

Complete and redesign all relevant pages, including:

- Product overview
- Features and capabilities
- Markets and assets
- Strategies
- AI and methodology
- Risk management
- Pricing and subscriptions
- Security and privacy
- Documentation and FAQ
- Platform status
- Contact and support
- Account registration and sign-in

Use genuine platform capabilities and verified information.

No fabricated performance statistics, success rates, market prices or customer testimonials.

---

## 6. COMPLETE THE ENTIRE AUTHENTICATED WEB APPLICATION

Audit all existing workspace routes and the historical 27-route requirement.

Create a route inventory and verify every route, its purpose, permissions, API dependency and end-to-end behavior.

Do not assume a route is complete because it renders.

The experience must support the following areas as appropriate to the real product and account entitlements.

### Core trading workspace

- Overview/dashboard
- Market intelligence
- Asset discovery
- Live and historical eligible market information
- Signal feed
- Signal details and evidence
- Strategy analysis
- Watchlists
- Alerts
- Notifications
- Portfolio monitoring
- Performance analytics
- Trading journal
- Paper trading
- Broker accounts
- Trading and risk preferences
- Subscription and billing
- Account settings
- Security and MFA
- Support
- Administrative/owner operations

Each page must have a complete and consistent design, correct navigation, purposeful content and working backend integration.

### Dashboard

Provide a genuine personalized dashboard driven by authorized account data.

Possible elements:

- Signal activity
- Delivered signal summary
- Watchlist activity
- Account-level exposure and readiness
- Paper portfolio summary
- Verified account connections
- Strategy observations
- Notifications
- Recent activity
- Risk status

Use the canonical backend to determine what is available.

Show honest unavailable, loading, empty, expired, restricted and error states.

Never convert missing data into fake zeros or apparent success.

### Signals

Build a comprehensive signal analysis experience supporting applicable:

- Cryptocurrency
- Forex
- Indices
- Equities/stocks
- Commodities

Support real available timeframes and strategies.

Provide appropriate filtering, sorting, searching and pagination.

Signal details should expose authorized evidence such as:

- Asset and timeframe
- Strategy
- Direction
- Entry and invalidation conditions
- Stop-loss and targets when available
- Risk/reward information
- Model and calibrated probability data when supplied
- Qualification status
- Evidence timestamps
- Delivery receipts
- Lifecycle/outcome status
- Rejection explanations where entitled
- Follow-up observations

A signal is not automatically a trade, and a signal delivery receipt is not proof of a broker fill.

### Charts and analytics

Use appropriate interactive charts where actual backend data supports them.

Support zooming, filtering and comparison as appropriate.

Do not manufacture an equity curve, win rate, account return, market candle or profitability claim.

Charts must support accessible summaries and unavailable-data states.

### Paper trading

Implement a complete paper trading workspace using its canonical server-side state.

Support existing permitted functionality such as:

- Simulated account balances
- Paper positions
- Simulated entries and exits
- Paper trade lifecycle
- Exposure monitoring
- Paper P&L
- Journal and ledger
- Risk settings
- Confirmed reset/close actions
- Simulation history

Always distinguish paper results from live broker executions.

---

## 7. BROKERS, MULTI-ACCOUNT AWARENESS AND RISK CONTROLS

The frontend must properly represent the user's connected brokers and their independent states.

Inspect actual backend contracts before implementing or exposing an action.

Support:

- Multiple broker connections
- Verified broker environment (demo/live/unverified)
- Available instrument coverage
- Account status and certification
- Account-currency handling
- Broker-specific risk boundaries
- Exposure and sizing constraints
- Balance awareness from verified broker records
- Trade routing eligibility
- Account-specific execution permissions
- Broker configuration and diagnostics
- Manual account freezing/disabling
- Evidence for executed orders and fills

**Never assume a signal must execute automatically on every connected broker offering that instrument.**

Any account-level trade routing must respect explicit user authorization, capital/risk limits, broker restrictions, account-level isolation and deduplication.

A broker being linked does not imply it is authorized for live trading.

Maintain the existing global kill switch and fail-closed risk policies.

Do not enable live-money trading, lower calibrated thresholds, relax admission checks, activate funded/prop execution, or turn off safety controls to make UI demonstrations appear functional.

Production website deployment and live financial execution authorization are separate decisions.

---

## 8. TELEGRAM AND WEBSITE PARITY

The SignalRankAI web application and Telegram ecosystem must work as one coherent product.

Audit the real Telegram commands, onboarding flows, account identity mappings, entitlements and backend actions.

Build a **Telegram-to-Web Feature Parity Matrix** covering:

- Registration and account linking
- Account status
- Subscription status
- Signal discovery/delivery
- Notifications
- Market preferences
- Strategy preferences
- Risk preferences
- Broker connection management
- Paper trading
- Portfolio review
- Journaling
- Support
- Relevant owner/admin capabilities

Each supported action should use canonical shared backend services and compatible account identity.

Avoid duplicating business rules independently in the website and Telegram bot.

No invented command functionality.

Preserve delivery reliability, retries, recipient authorization, event logs, cooldowns and recovery behavior.

---

## 9. OWNER, ADMIN AND OPERATIONAL WORKSPACES

Design dedicated interfaces appropriate for authorized owner and administrator capabilities.

These should expose backend-supported operations such as:

- Engine health
- Signal generation activity
- Market provider status
- Signal drought diagnostics
- ML calibration and rejection statistics
- Entitled delivery outcomes
- Broker connectivity
- Risk-control status
- Worker availability
- Telegram delivery health
- Audit logs
- Administrative commands and review actions
- User and subscription management
- System configuration where permitted

Enforce authorization on the backend.

Never reveal administrative operations merely because someone directly visits a URL.

Do not put secrets, credentials, access tokens or privileged API data into client-rendered source.

Every administrative mutation must have proper validation, authorization, audit evidence and confirmation where warranted.

---

## 10. AUTHENTICATION, ONBOARDING AND SESSION RELIABILITY

Resolve existing and newly discovered issues involving:

- Registration
- Login
- MFA
- Password recovery
- Magic links
- Email verification
- Session persistence
- Cookie and CSRF handling
- Logout
- Session expiration
- Route protection
- Role-dependent access
- Server-side entitlements
- Return-to-page navigation
- Refresh and deep-link behavior
- Connected broker setup return flows
- Login redirects
- Mobile authentication layouts

The site must not unexpectedly return users to login or home during ordinary authorized navigation.

Authentication must not silently succeed when the backend has rejected the request.

Do not replace secure server-owned sessions with insecure local-storage tokens.

Verify the actual production-domain and staging-domain behavior, including same-origin API routing and cookie scope.

---

## 11. COMPLETE DESIGN SYSTEM AND RESPONSIVENESS

Create a documented, maintainable design system.

Include:

- Brand tokens
- Typography scale
- Layout grid
- Spacing scale
- Breakpoints
- Buttons
- Cards
- Data tables
- Charts
- Modals and dialogs
- Form elements
- Navigation
- Tabs
- Status indicators
- Tooltips
- Notifications
- Loading, empty, error and permission-denied states
- Motion tokens
- Dark/light theme rules

Eliminate contradictory stylesheets, duplicated design rules and accumulated emergency CSS overrides where safe.

Refactor large monolithic frontend components into sensible, maintainable pieces without changing their security responsibilities.

### Responsive testing

Test at a minimum:

320px, 360px, 390px, 430px, 768px, 1024px, 1280px, 1440px and 1920px.

Verify:

- No horizontal overflow
- Correct text wrapping
- Appropriate padding and margins
- Correct sticky/fixed positioning
- Responsive navigation
- Working menus and dialogs
- Usable data tables on phones
- No overlapping action buttons
- Readable charts
- Usable forms and keyboard
- Correct dark/light text colours
- No content hidden behind footers or navigation
- No hover-only functionality
- Reduced-motion behavior

Mobile navigation must close after route changes, Escape and outside interactions as appropriate.

Test iOS Safari, Android Chrome and desktop browsers where test infrastructure permits.

---

## 12. ADVANCED INTERACTION AND ANIMATION

Use high-quality motion deliberately.

Implement suitable:

- Scroll-linked product assembly
- Sticky storytelling
- Controlled 3D perspective
- Interactive product demonstrations
- Animated interface transitions
- Subtle hover and focus responses
- Sophisticated loading and state transitions
- Layered spatial UI
- Contextual data transitions
- Useful onboarding walkthroughs

Use animations to explain the product, not distract from actual market information.

A professional trading workspace must remain fast and usable during prolonged sessions.

Avoid multiple heavyweight WebGL canvases, uncontrolled animation loops and huge dependencies.

Prefer a single bounded 3D experience where appropriate.

Provide fallback content and performance safeguards for lower-powered devices.

Ensure animations do not interfere with trading controls, text visibility, screen readers or reduced-motion settings.

---

## 13. CRILOX SOLUTIONS FOOTER ATTRIBUTION

Implement a consistent footer attribution across the public site and appropriate application/authentication layouts.

Required visible text:

**Powered by CRILOX Solutions**

The words **CRILOX Solutions** must link to:

https://www.criloxsolutions.com

Use a proper accessible anchor.

The link should open safely, using `rel="noopener noreferrer"` if opening a new tab.

The footer should blend naturally into SignalRankAI branding and not look like an advertisement.

It must be visible without being intrusive on desktop and mobile.

Ensure the credit also works in the frontend actually deployed to Railway, not only a separate Next.js preview.

---

## 14. BACKEND CONTRACTS AND REAL FUNCTIONALITY

Audit and validate every frontend API dependency.

For each route or component:

1. Identify the backend endpoint.
2. Confirm the endpoint exists.
3. Confirm the current request/response contract.
4. Confirm authorization and entitlement behavior.
5. Validate successful responses.
6. Validate expected errors and missing data.
7. Verify loading and recovery states.
8. Verify any mutations and resulting persisted state.
9. Add automated tests.
10. Record the implementation and evidence.

Never claim a button is functional merely because an `onClick` handler exists.

Never implement a fake success response to conceal an unavailable service.

Do not produce frontend-only approximations of canonical financial, account or billing data.

Where required functionality is missing, complete the real implementation safely or mark the external dependency precisely.

---

## 15. REPAIR RELEASE AND CI FAILURES

Investigate all failed and skipped GitHub Actions jobs relevant to this release.

Previous failures included:

- Manifest/governance certification
- Release-certification gates
- Downstream jobs skipped
- Separate frontend verification failures
- Inaccessible or missing hosted job logs

Identify actual root causes.

Do not treat missing logs as a passed test.

Restore:

- Lockfile reproducibility
- Dependency security
- ESLint
- TypeScript
- Frontend unit/contract tests
- API contract tests
- Integration tests
- Browser E2E tests
- Security scanning
- Build reproducibility
- Release manifests
- Branch/source provenance
- Docker/container checks
- Readiness and health checks

Ensure the final published commit is the exact commit that was tested and approved.

Preserve existing governance controls instead of disabling them to manufacture a green release.

---

## 16. STAGING, DATABASE AND INFRASTRUCTURE SAFETY

The existing project uses Railway, PostgreSQL, Redis and multiple services.

Before promoting changes:

1. Inspect existing services and environments.
2. Confirm production and staging database isolation.
3. Confirm Redis isolation.
4. Check source branch/commit configuration for every application role.
5. Audit schema and migration compatibility.
6. Check for unapplied or divergent migrations.
7. Verify backups and an actual restoration procedure.
8. Verify readiness checks and service routing.
9. Test safe restart and rollback behavior.
10. Validate health and operational monitoring.

Never point a staging deployment at writable production trading databases as a shortcut.

Do not execute destructive migrations or overwrite actual account/financial records.

Do not move every worker to an unverified branch merely to publish a new website design.

---

## 17. PRODUCTION DEPLOYMENT — RAILWAY IS THE REQUIRED TARGET

**The final website must be deployed to Railway and accessible from:**

https://www.signalrank.criloxsolutions.com

and

https://signalrank.criloxsolutions.com

Do not consider the task complete because Vercel produces a successful preview.

### Deployment strategy

Inspect the current architecture and decide how best to host the redesigned Next.js frontend safely.

A separate Railway frontend service may be preferable if it cleanly separates the UI from the trading engine.

If using separate services, configure the appropriate routing, domains, TLS, cookies, reverse proxies and API access. Maintain working Telegram webhooks and other backend endpoints.

If the application can be integrated safely into the current Railway service, justify that architecture and test it thoroughly.

Preserve existing working backend services, workers, databases and trading controls.

### Deployment sequence

1. Produce an immutable release candidate.
2. Pass frontend checks.
3. Pass relevant backend and integration checks.
4. Deploy to isolated Railway staging.
5. Test actual authentication and API behavior.
6. Verify data, security, consent, permissions and risk policies.
7. Validate smoke tests on the deployed application.
8. Reconcile outstanding release governance and required staging/soak evidence.
9. Merge to the canonical production branch only when safe.
10. Deploy the exact approved candidate to the appropriate Railway production services.
11. Confirm the required domain routes actually load the redesigned frontend.
12. Check the backend health, service readiness, session handling, logs and actual end-to-end journeys.
13. Verify rollback availability and monitor after release.

**If the full release remains blocked by trading-engine certification, evaluate whether a genuinely isolated, read-only/public-frontend Railway deployment can be shipped safely without promoting the engine or modifying live financial operations.**

Do not treat that partial release as full ecosystem certification.

Do not perform a dangerous production migration just to satisfy a deployment checkbox.

---

## 18. FULL QA AND AUTOMATED TESTING

Implement and run tests covering:

### Public frontend

- All navigation links
- All calls to action
- Theme changes
- Animation states
- Scroll interactions
- Content visibility
- Mobile and desktop layouts
- Accessibility
- Responsive navigation
- Footer attribution

### Authentication

- Registration
- Login
- MFA
- Recovery
- Magic links
- Email verification
- Expired sessions
- Unauthorized routes
- Return navigation
- Refresh persistence

### Trading workspace

- Market discovery
- Signal filtering
- Signal evidence
- Watchlists
- Alerts
- Paper trading
- Broker account inspection
- Portfolio
- Performance charts
- Journal
- Notifications
- Preferences
- Billing
- Support
- Owner/admin permission boundaries

### Negative testing

- Backend unavailable
- Unauthorized account
- Expired credentials
- Invalid API responses
- Missing market data
- Broker disconnected
- No active subscription
- Insufficient permissions
- Financial information unavailable
- Network timeout
- Request retries
- Browser refresh
- Redis/service interruption where safely testable

Automate screenshots and browser journeys using Playwright or an existing compatible browser-testing framework.

Test actual rendered UI, not only source strings.

Fix issues identified by the tests and rerun them.

---

## 19. PERFORMANCE, SEO AND ACCESSIBILITY

Meet practical production standards.

Focus on:

- Core Web Vitals
- LCP, CLS and INP
- Responsive image optimization
- Reasonable JavaScript bundle sizes
- Code splitting
- Efficient 3D loading
- Stable layout during animation
- Semantic HTML
- Accessible forms
- Keyboard interaction
- Screen-reader support
- Focus visibility
- Colour contrast
- Reduced motion
- Correct page metadata
- Appropriate public SEO
- No indexing of private account pages
- Safe error handling

Do not expose user or broker information through SEO metadata, public caching or server-rendered responses.

---

## 20. EVIDENCE LEDGER AND COMPLETION STANDARD

Use the existing master-blueprint traceability matrix and completion evidence ledger where available.

For each requirement, record:

- Requirement ID
- Feature or route
- Implementation location
- Backend dependency
- Test coverage
- Test outcome
- Deployment environment
- Verification artifact
- Remaining blocker, if any

Use honest statuses:

- IMPLEMENTED
- VERIFIED
- BLOCKED_EXTERNAL
- DEFERRED
- NOT_APPLICABLE

Do not mark requirements VERIFIED merely because code was written.

Do not invent execution results, screenshots, soak-test durations, broker fills, audited balances or performance statistics.

Real 24–72-hour soak tests must involve actual elapsed time and collected operational evidence.

External owner approvals and account-provider credentials must remain explicit.

---

## 21. REQUIRED FINAL DELIVERABLES

Provide:

1. A fully redesigned and maintainable public website.
2. A redesigned, responsive authenticated application.
3. Complete API-connected functionality for supported user journeys.
4. A consistent branding/design system.
5. The working Powered by CRILOX Solutions footer.
6. A complete route and feature audit.
7. The Telegram-to-Web parity matrix.
8. Branch and PR reconciliation evidence.
9. Fixed CI and automated test evidence.
10. Railway staging and production deployment evidence.
11. Live-domain functional verification.
12. Screenshots of major pages on mobile and desktop.
13. Accessibility and performance results.
14. Migration and rollback evidence where applicable.
15. A clear list of remaining genuinely external blockers.

### Final response format

Report:

**A. Repository and branch**
- Exact branch and commits.
- Pull requests opened or merged.
- What was reconciled.

**B. Design and functionality**
- All major pages rebuilt.
- All workflows connected and verified.
- Issues found and fixed.

**C. Tests**
- Commands run.
- Results.
- Browser journeys verified.
- Any unresolved failures.

**D. Railway**
- Services updated.
- Exact deployed commit.
- Staging and production deployment IDs.
- Domain verification results.
- Readiness and rollback status.

**E. Completion**
- VERIFIED requirements.
- Remaining blockers.
- Exact user action necessary for genuinely external dependencies.

Do not call production deployment successful until the Railway deployment and real website verification both succeed.

---

## 22. EXECUTION RULES — IMPORTANT

- Work autonomously on everything within the repository and connected deployment environments.
- Do not ask repetitive questions when the answer is available in code, documentation or deployment settings.
- Fix defects rather than merely documenting them.
- Preserve the real SignalRankAI logo and legitimate brand identity.
- Never ship mock statistics as real financial information.
- Never silently bypass MFA, account entitlements, broker certification or risk checks.
- Never activate real-money trading without separate explicit authorization.
- Never silently delete data or destructive-migrate production.
- Do not weaken model thresholds or signal quality checks merely to generate more alerts.
- Do not stop at the marketing website; finish the entire user-facing ecosystem.
- Do not replace working backend functionality with fake frontend demos.
- Do not stop after a Vercel build: **Railway production is the intended release target**.
- Do not treat a frontend deployment as automatic approval of trading-engine changes.
- Do not claim completion without evidence.
- If a particular release blocker cannot be resolved internally, continue all safe independent work and document the precise blocker instead of abandoning the whole project.
- Preserve production safety and rollback capability throughout.

**BEGIN NOW.**

Start by inspecting the actual production Railway deployment, latest repository state, branches, PR #190, merged PR #200 and release-recovery code.

Then perform the complete audit, reconcile the implementation, rebuild the frontend, repair outstanding functionality, verify the system and safely deliver the finished website to Railway.

The required outcome is a **premium, functional, cohesive SignalRankAI ecosystem**, not another unfinished frontend preview.
