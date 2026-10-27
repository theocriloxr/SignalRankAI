# SIGNALRANKAI — COMPLETE REPOSITORY RECOVERY, IMPLEMENTATION, REDESIGN, TESTING AND PRODUCTION RELEASE

## YOUR ROLE AND OBJECTIVE

You are the principal engineer, software architect, quantitative systems engineer, security auditor, senior product designer, QA lead, and release engineer responsible for completing the existing SignalRankAI ecosystem.

**Repository:** `theocriloxr/SignalRankAI`

**Current integration branch:** `fix/stage1-canonical-reconciliation-20261014`

**Open pull request:** `#201`, targeting `main`

**Last observed integration SHA:** `51d2f59ed2c1553841fc24dda98689ffb26a0b7a`

**Public website:** https://www.signalrank.criloxsolutions.com

Your mission is to:

1. Recover the exact current repository state and preserve all previous agents' work.
2. Finish the **current unfinished stage first**, then proceed sequentially through every remaining stage.
3. Fully implement the SignalRankAI trading intelligence ecosystem, including backend, frontend, mobile, Telegram, AI/ML, brokers, subscriptions, security, and operational controls.
4. Redesign the entire frontend into a cohesive, premium, production-grade financial technology product.
5. Execute comprehensive local tests rather than depending on unavailable GitHub Actions.
6. Discover and repair every reproducible defect, regression, incomplete integration, broken route, security weakness, and inconsistent UI component.
7. Prepare staging, verify external integrations and production isolation, and obtain genuine release evidence.
8. Merge the verified integration branch into `main` and deploy the exact approved release to production **only after every mandatory release gate is satisfied**.
9. Verify the deployed site and services, and provide an evidence-backed final completion report.

**Do not stop after an audit, plan, or progress summary. Implement the unblocked work.**

Do not invent verification evidence, claim external services were tested when they were not, downgrade safety checks, disable required protections, or place real-money trades.

You have authority to complete code changes, run isolated tests, prepare and validate releases, and deploy approved non-destructive production changes after all gates pass. Real-money order execution and destructive production database operations require independent safeguards and explicit account-level authorization.

---

# PHASE 0 — SYNCHRONIZE EVERYTHING BEFORE CODING

Start by examining the current working directory, Git state, existing worktrees, active branch, local commits, remote branches, open PRs, untracked files and uncommitted changes.

Run the appropriate equivalents of:

```bash
git status --short --branch
git remote -v
git worktree list --porcelain
git branch -avv
git log --all --oneline -40
git fetch --all --prune --tags
git status --short --branch
```

Do not perform a destructive checkout, reset, clean, forced pull, or force-push.

If there are uncommitted edits from earlier Codex agents, inspect them and preserve them safely. Use an additional worktree or a separately named preservation branch when necessary. Do not automatically discard or overwrite modifications.

Inspect and compare:

- `main`
- `fix/stage1-canonical-reconciliation-20261014`
- `implementation-of-master-blueprint`
- `fix/release-recovery-20261008`
- Relevant historical recovery, staging and feature branches
- PR #201
- All repository branches containing unreconciled implementation work

**Never assume the last observed SHA is still current.** Use Git's freshly fetched state as the authority.

Determine precisely which stage the previous agent was working on. Continue that same stage until its acceptance criteria are satisfied.

## Mandatory documents to read

Read these before changing architecture:

```text
AGENTS.md
docs/release/MASTER_EXECUTION_CONTRACT.md
docs/release/COMPLETION_EVIDENCE.md
docs/release/RELEASE_BLOCKERS.md
docs/release/REQUIREMENTS_TRACEABILITY.md
docs/release/FEATURE_INVENTORY.md
docs/release/baseline.json
docs/release/requirements.json
docs/release/canonical_requirements.json
docs/release/current_scope_20261016.json
docs/release/branch_dispositions.json
certification/release_manifest.yaml
certification/completion_matrix.json
certification/completion_dispositions.json
```

Also inspect the complete master blueprint, October master directive, preserved October specifications, research source requirements, ecosystem frontend specifications, tests, CI workflows, architecture documents, Railway configuration, and all relevant product and security requirements.

Reconcile overlapping historical specifications without losing genuinely required behavior.

Do not treat an old `PASS` label as current verification.

---

# PHASE 1 — FINISH CANONICAL STAGE 1

The previous handoff identifies Stage 1 as incomplete.

Its major outstanding items include:

- Source-specific requirements reconciliation and acceptance.
- Incomplete verification evidence.
- Unreviewed changes and incomplete feature mappings.
- Incomplete focused asset-universe enforcement.
- Unverified deployment source and schema identity.
- Missing current commit-level tests.
- External staging and broker certification.
- A draft PR that is not ready for merge.

For every remaining requirement:

1. Identify the original source and acceptance conditions.
2. Locate the active implementation, if any.
3. Verify it against the current architecture.
4. Implement missing behavior.
5. Write meaningful positive, negative and regression tests.
6. Run the relevant tests.
7. Record the result, current commit and evidence.
8. Keep unresolved requirements visible.

Use the existing canonical requirement statuses and completion-evidence mechanisms.

Complete every safely executable Stage 1 task before beginning another stage.

Do not count documentation, interfaces, stub implementations or mock-only tests as proof of end-to-end functionality.

---

# PHASE 2 — REPAIR AND COMPLETE THE BACKEND

Audit the complete Python/FastAPI ecosystem.

Review:

- API contracts and versioning
- Authentication, authorization and session state
- Background jobs and worker roles
- Async execution, timeouts and cancellation
- SQLAlchemy and PostgreSQL interactions
- Alembic migrations
- Redis connections, queues and caching
- Data persistence and idempotency
- Scheduler and worker leadership
- Distributed locking
- Retries and dead-letter queues
- Event handling
- User/account ownership
- Deployment configuration
- Resource consumption and graceful shutdown

Fix all confirmed issues.

Resolve migration compatibility between development, staging and production without damaging real data.

Verify startup/readiness, worker ownership, database routing and Redis isolation.

Do not reduce existing runtime safety checks to make tests pass.

---

# PHASE 3 — FOCUSED MARKET UNIVERSE

The owner has explicitly narrowed SignalRankAI to **10 preferred core instruments, with up to 5 additional qualified instruments, per asset class**.

The five supported classes are:

- Cryptocurrency
- Forex
- Indices
- Equities/stocks
- Commodities

This means approximately 50 core candidates, with a hard maximum of 75 active instruments across the five classes.

Inspect:

```text
configs/focused_universe.json
docs/release/current_scope_20261016.json
core/focused_universe.py
core/asset_registry.py
data/class_universe.py
data/database_universe.py
services/asset_registry.py
engine/core.py
```

Continue from the existing implementation rather than starting another competing system.

Requirements:

1. Maintain one authoritative active-instrument policy.
2. Strictly enforce the maximum of 15 per class.
3. Prefer qualified core assets before optional assets.
4. Verify canonical symbols, asset classes, supported providers, market calendars and trading sessions.
5. Verify data freshness, historical candle coverage, provider entitlement, liquidity and spread where observable.
6. Reject unknown, stale, unsupported, misclassified or uncertified instruments.
7. Never add static fallback instruments merely to reach a target number.
8. Apply consistent active-universe rules to scanning, signals, strategy evaluation, AI/ML, scheduler workloads, user dashboards and Telegram.
9. Independently enforce broker/account-specific permitted instruments before any new order.
10. Preserve historical research, trades and performance data for removed instruments.
11. Continue reconciling and managing existing positions even if new entries are disabled for their symbols.
12. Implement safe periodic qualification, rankings, owner overrides, audit trails and anti-churn controls.
13. Give the owner visibility into why an asset is included, excluded or temporarily paused.

Do not assume that being on the shortlist authorizes a broker trade.

---

# PHASE 4 — STRATEGIES, DATA SCIENCE, AI AND LEARNING

Complete and integrate all supported trading-strategy families, including:

- Trend following
- Momentum
- Mean reversion
- Breakout
- Scalping
- Market structure
- Liquidity analysis
- ICT/SMC
- Order blocks
- Volume/VWAP
- Wyckoff
- Volatility analysis
- Supported quantitative/statistical strategies
- Macro and news context

Verify real strategy dispatch by instrument, timeframe, market regime and user profile.

Audit candle handling, timestamp normalization, session calendars, DST, data gaps, provider outages and symbol mappings.

Eliminate lookahead bias, label leakage, survivorship bias, mutable historical inputs and unrealistic backtesting assumptions.

Complete:

- Chronological train/validation/test separation
- Walk-forward testing
- Out-of-sample evaluation
- Calibration
- Slippage and fee modeling
- Strategy attribution
- Regime awareness
- False-positive analysis
- Outcome tracking
- Controlled model promotion
- Drift detection
- Retraining eligibility
- Rollback to a previously certified model
- Immutable evidence and reproducible research

OpenAI integrations must be reliable, model-configurable and cost-aware.

AI-generated analysis must never bypass deterministic market-data, risk, ownership, entitlement or execution gates.

Aim to improve the measured signal quality and long-term win rate, but **never invent performance, guarantee 70% wins, or optimize on leaked future data**.

A low or zero signal count is not automatically a bug. Diagnose whether the system is correctly filtering weak setups or failing to obtain/evaluate eligible market data.

---

# PHASE 5 — MULTI-BROKER EXECUTION AND FINANCIAL SAFETY

Complete the existing broker integration framework while accurately distinguishing:

- Catalogued brokers
- Connection-only integrations
- Market-data integrations
- Execution-capable adapters
- Fully demo-certified adapters
- Separately authorized live-capable adapters

Audit every supported broker adapter.

Support applicable lifecycle operations:

- Account connection and verification
- Read-only balance/position synchronization
- Paper/demo mode
- Explicitly authorized order placement
- Broker acknowledgement
- Partial fills
- Stops and take-profit levels
- Amendments
- Cancellations
- Close orders
- Breakeven changes
- Retry/recovery
- Broker and internal ledger reconciliation
- Restart recovery
- Duplicate-order prevention

Require durable idempotency keys, ownership checks, broker receipts and account-specific execution permissions.

Implement strict safeguards for drawdown, daily loss, exposure, leverage, correlation, market-hours restrictions, stale prices, prop-firm rules, and emergency stops.

Maintain distinct states for:

```text
SIGNALS_ONLY
PAPER
DEMO
AUTO_CONFIRM
AUTO
```

Connect-account permission must never imply execution permission.

Do not execute real-money orders as part of tests or automatically enable funded/prop/personal trading.

Run actual end-to-end broker execution tests only using isolated, explicitly authorized demo accounts.

Unsupported execution adapters must remain disabled and be reported honestly.

---

# PHASE 6 — COMPLETE TELEGRAM ECOSYSTEM

Audit every bot command, menu, callback, role, subscription tier, deep link and notification flow.

Ensure the Telegram adapter and website use the same authoritative backend services.

Fix:

- Account linking
- Secure-link redirects
- Authentication expiry
- Duplicate callbacks
- Stale callbacks
- Cross-user access
- Webhook retries
- Notification duplication
- Missing or delayed signals
- Owner/admin commands
- Subscriptions and onboarding
- Broker-account management
- Paper trading
- User preferences
- Portfolio and reports
- Help and support

Every supported Telegram feature should have an equivalent web workflow where meaningful, and both must produce consistent server-authoritative results.

Test real staging-bot journeys with designated test users and ensure production bot credentials are isolated.

---

# PHASE 7 — COMPLETE FRONTEND REDESIGN

This is a major deliverable, not a quick color or padding adjustment.

**Redesign, restructure, and polish the entire SignalRankAI public website, user workspace and administrative ecosystem.**

Preserve the existing product functionality while giving it a coherent, premium, modern financial-technology identity.

## 7A. First audit the current frontend

Inspect the entire Next.js application, routes, components, design tokens, CSS, Tailwind setup, fonts, layouts, forms, dialogs, charts, navigation, responsive behavior, hydration, PWA support and brand assets.

Identify all existing pages and user journeys, including dynamic routes and retained legacy workspace behavior.

Create an actual route/component inventory before beginning the redesign.

Do not leave any page using the old design language by accident.

## 7B. Design direction

Target an aesthetic combining:

- Premium financial intelligence workstation
- Editorial typography and strong visual hierarchy
- Clean, structured, credible data visualization
- Modern enterprise SaaS
- Controlled cinematic motion
- High attention to layout, whitespace and readability
- Distinctive but restrained brand personality

Take design and implementation inspiration from:

- https://byflowww.com/
- https://www.getlayers.ai/
- https://www.framer.com/marketplace/components/ripple-background/
- https://hover-force.learnframer.site/
- https://framer.university/resources/hover-force-component-for-framer
- https://www.framer.com/marketplace/components/magnetizinglines/
- https://framer.university/resources/hover-chroma-backgrounds-in-framer

Also study the available reference materials, screenshots, recorded interactions, design files and project specifications previously supplied by the owner, when accessible locally.

Extract reusable ideas rather than copying another brand or introducing unnecessary animation.

## 7C. Unified design system

Create a complete design system covering:

- Brand color foundations
- Light and dark semantic color tokens
- Backgrounds and surfaces
- Foreground and muted text
- Success, warning, danger and informational states
- Borders, shadows and elevation
- Typography scale
- Spacing and layout grid
- Radius and shape language
- Iconography
- Buttons
- Inputs
- Data tables
- Charts
- Cards
- Modals and drawers
- Tabs and filters
- Loading states
- Empty states
- Notifications and toast messages

Start from the actual existing SignalRankAI brand/logo assets and legitimate product colors. Improve their application consistently instead of assigning arbitrary colors.

Use premium dark slate/ink surfaces and restrained accent colors where appropriate, with a polished readable light theme.

Do not make everything glow, overuse gradients, or obscure important financial information.

## 7D. Logo, favicon and brand consistency

Find the **actual canonical SignalRankAI logo** in the existing source assets and brand materials.

Audit its geometry, color, typography and intended usage.

Improve its production suitability without unintentionally replacing the brand.

Ensure consistency across:

- Desktop header
- Mobile header
- Sidebar
- Login and registration
- Pricing pages
- User dashboard
- Owner/admin dashboard
- Loading screens
- Favicon
- Apple touch icon
- Android icons
- PWA manifest icons
- Social/OG previews
- Email templates
- Notification templates

Ensure the favicon is derived from the actual logo rather than using a random icon, generic initials, or an unrelated symbol.

Supply sharp, correctly sized assets for light and dark backgrounds.

Avoid broken transparency, clipping, blurry scaling and stretched logos.

## 7E. Complete page coverage

Redesign every existing public and authenticated route.

Cover the public landing page, navigation, product explanations, features, subscription plans, pricing, registration, login, verification, password/session recovery, legal pages, FAQ, contact and support.

Redesign the authenticated ecosystem:

- Main user dashboard
- Market explorer
- Signal feed
- Individual signal details
- Evidence and candlestick analysis
- Watchlists
- Alerts
- AI-assisted analysis
- Paper trading
- Portfolio
- Performance analytics
- Trading journal
- Broker/account hub
- Risk and automation controls
- Telegram linking
- Subscription and billing
- Profile/settings
- Security/session management
- Notification center
- Support tickets
- Administrative and owner dashboards
- Operational diagnostics
- Strategy and model controls
- Research and backtesting views
- Compliance and audit views
- Every other discoverable route

Preserve legitimate permissions, subscription tiers and role-based visibility.

Never display owner-only controls to ordinary users.

Do not replace functional pages with decorative mockups.

## 7F. Hero and landing page

Give the landing page an original high-quality hero, not a plain headline above generic cards.

The hero should immediately communicate what SignalRankAI is:

**A multi-market trading intelligence and evidence-based signal ecosystem connecting market analysis, research, paper trading, Telegram, web and controlled broker workflows.**

Consider an elegant trading workstation composition featuring realistic but clearly labeled sample/illustrative analysis, layered information, refined depth and subtle animation.

Design a compelling hierarchy with meaningful calls to action.

Follow the hero with purposeful sections covering the platform, how it works, verified evidence, supported markets, product features, risk controls, plans and FAQs.

Do not show fabricated profitability, fake users, fake win-rate claims or unverified trading results.

## 7G. Responsive behavior

Manually inspect all pages at representative widths including:

```text
320px
360px
375px
390px
430px
768px
1024px
1280px
1440px
1920px
```

Fix:

- Horizontal overflow
- Collapsed layouts
- Broken sticky/fixed navigation
- Mobile menu behavior
- Inconsistent margins
- Poor padding
- Overlapping footers
- Text wrapping
- Inaccessible modals
- Oversized components
- Cramped tables
- Touch-target problems
- Inconsistent buttons
- Clipped charts
- Dialog keyboard traps
- Scrolling and focus restoration

The mobile layout should feel deliberately designed, not merely compressed from desktop.

## 7H. Theme support

Implement robust global theme management.

Users must be able to change their theme from every relevant page, not only settings.

Support:

```text
Light
Dark
System
```

Persist the user's preference appropriately, with proper cross-device synchronization where supported.

Ensure the theme changes every page, modal, chart, form, table, badge and navigation component consistently.

Prevent flash-of-incorrect-theme issues.

## 7I. Motion and interaction

Use subtle, purposeful animation:

- Smooth navigation transitions
- Refined hover interactions
- Elegant content reveals
- Fluid mobile navigation
- Thoughtful feedback animations
- Polished loading and skeleton states
- Chart interactions

Use Framer Motion or suitable existing tools when justified.

Respect reduced-motion preferences and low-powered devices.

Avoid expensive WebGL unless its value is clear and a lightweight fallback exists.

## 7J. Accessibility and performance

Target WCAG AA where applicable.

Verify contrast, keyboard navigation, visible focus, screen-reader labels, form errors, reduced motion, semantics and touch targets.

Optimize images, fonts, caching, bundle sizes, hydration and route loading.

Eliminate unnecessary dependency weight and avoid expensive re-rendering in trading dashboards.

## 7K. Visual acceptance

Run actual browser tests and capture screenshots of every major page in light and dark themes at desktop and mobile widths.

Inspect the screenshots, identify defects, correct them and repeat.

The redesign is not complete simply because Next.js builds successfully.

---

# PHASE 8 — ACCOUNT SECURITY, BILLING AND PERMISSIONS

Complete and harden:

- Registration and activation
- Email verification
- MFA
- Password and session handling
- Cookie security and CSRF
- Account linking
- Role-based access
- Owner permissions
- Plan entitlements
- Subscription upgrades/downgrades
- Payment provider callbacks
- Cancellation
- Refund workflows
- Email delivery and retry behavior
- Privacy requests
- Retention/deletion operations
- Immutable financial and security audit logs

Test negative ownership and cross-user cases.

Never mark a payment completed before provider-confirmed evidence.

Preserve consent and legal-review requirements.

---

# PHASE 9 — INFRASTRUCTURE AND ENVIRONMENTS

Inspect actual Railway, Vercel, GitHub, PostgreSQL and Redis configuration.

The previous read-only inspection observed:

```text
Railway project: trading-bot-account2

Production API:
9865a3d1bcee632bfd9347e50d5de34d355225d9

Production public-web:
f026bd16d90c0fbde2292e326525524fd75966ea

Stage 1 integration:
51d2f59ed2c1553841fc24dda98689ffb26a0b7a
```

Treat these as historical observations and recheck current deployments.

The previous inspection also found:

- Different frontend/backend production commit identities.
- No dedicated staging Railway environment.
- A crashed read-only soak service.
- Incomplete confirmed signal generation/delivery.
- An unverified MT5 connection.
- A public `/login` 404 route.
- GitHub Actions billing preventing jobs from running.

Resolve these issues safely.

Provision properly isolated staging resources if they do not exist.

Require distinct staging and production credentials, database routing, Redis, Telegram bot identities, payment modes and broker demo connections.

Do not clone live credentials into staging or allow fallback into production.

Audit database migrations, backup restoration, storage retention, environment variables, release-source gates, worker role ownership and rollback plans.

---

# PHASE 10 — FULL LOCAL TESTING WITHOUT DEPENDING ON GITHUB ACTIONS

The owner authorizes using rigorous local execution as an alternative to unavailable GitHub Actions.

This does **not** mean skipping tests or disabling branch protection.

Use the repository's existing release manifest and completion runner.

Run, where applicable:

```bash
python -m scripts.build_release_inventory --check
python -m scripts.completion_matrix --check
python -m scripts.validate_current_scope

python -m pytest -q tests/test_current_scope_handoff_20261016.py
python -m pytest -q tests/test_focused_universe_policy_20261016.py

python scripts/verify_release_chain.py
python scripts/assert_single_alembic_head.py
python scripts/secret_scan.py

python scripts/run_release_manifest.py --validate
python scripts/run_release_manifest.py --environment local

python scripts/run_complete_system_test.py --full
```

Use the repository's actual configured frontend/mobile package-manager commands to execute:

- Lint
- Type checking
- Unit tests
- Integration tests
- Production builds
- Dependency vulnerability audits
- Browser tests
- Mobile tests and exports

Run the remaining required release gates in isolated environments, including those not covered by the manifest's `local` selection.

Don't substitute the local manifest subset for all CI, cleanroom, staging and external integration gates.

Create isolated test databases and caches with explicit ownership and cleanup.

Run all tests against a frozen Git commit and confirm the source did not change while they ran.

When tests fail:

1. Record the original failure and command.
2. Identify the root cause.
3. Fix the underlying defect.
4. Add a regression test.
5. Rerun the affected tests.
6. Rerun the necessary full-suite checks.
7. Retain logs and exact commit evidence.

Never skip failing tests, weaken assertions, remove existing financial-security checks, or fabricate receipts.

If GitHub branch protection still requires hosted checks, preserve the protection and report the required administrative action. Local evidence should not be mislabeled as a GitHub-hosted check.

---

# PHASE 11 — ACTUAL END-TO-END CERTIFICATION

Test real integrated workflows with isolated staging accounts and environments.

Cover:

**Identity:** Register, verify, login, MFA, logout, refresh, expiry, account recovery and cross-user isolation.

**Billing:** Test-mode checkout, callbacks, reconciliation, entitlement changes, renewal and cancellation.

**Telegram:** Start bot, secure-link account, authenticate, receive signals, change preferences, test roles and callbacks.

**Markets:** Real entitled provider queries, candle integrity, freshness, class coverage, supported timeframes and outage handling.

**Signals:** Discovery → qualifying strategy → ML/risk gate → persistence → entitlement check → delivery → outcome tracking.

**Paper trading:** Entry, partial exit, target/stop outcomes, accounting, restart and recovery.

**Demo brokers:** Account verification, order lifecycle, idempotency, reconciliation, risk limits, stop conditions and emergency disablement.

**Web:** Authenticated journey testing for all routes, both supported workspace modes, mobile/desktop layouts, accessibility and themes.

**Mobile:** Real-device or appropriately isolated emulator tests when available, session behavior, navigation and notifications.

**Infrastructure:** Database outage, Redis loss, retries, duplicate callbacks, worker restart, queue recovery, health alerts and backup restoration.

Tests requiring unavailable provider, broker, legal, device or production authority must remain explicitly unverified—not silently passed.

---

# PHASE 12 — INDEPENDENT AUDITS AND STAGING SOAK

Perform multiple independent review passes covering:

- Software architecture
- Source integration completeness
- Authentication and authorization
- Financial risk controls
- Order idempotency
- Research validity
- Market-data provenance
- Performance attribution
- Database migrations
- Infrastructure resilience
- Dependency security
- Frontend accessibility
- Responsive design
- Client/API consistency
- Recovery and rollback
- Audit/evidence integrity

Fix material findings, then repeat review.

Run a genuine 24–72-hour staging soak as specified by the execution contract using a frozen, approved release SHA.

Measure actual:

- Worker uptime
- Signal-generation health
- Delivery latency
- Provider connectivity and freshness
- Job and queue health
- Database performance
- Redis behavior
- Model health
- Demo broker reconciliation
- Resource utilization
- Error rates
- Alerting and recovery behavior

Do not certify a soak that reports degraded operation, unresolved broker reconciliation or missing required signal/delivery evidence.

---

# PHASE 13 — MERGE AND DEPLOY TO PRODUCTION

This is an intended deliverable, not a task to omit.

However, execute it only after the mandatory release gates truly pass.

Before merging:

- Complete required implementation and review.
- Verify the exact commit and source hash.
- Pass all applicable local tests and release gates.
- Obtain necessary independent review and administrative approvals.
- Resolve required GitHub branch protections legitimately.
- Verify migration compatibility.
- Verify backup/restore and rollback readiness.
- Complete staging, demo and soak certification.
- Confirm production deployment identity and environmental isolation.

Then:

1. Re-fetch remote Git state.
2. Review the final diff against `main`.
3. Resolve divergences without losing code.
4. Merge through the approved repository mechanism.
5. Record the merge commit.
6. Deploy the corresponding backend, worker, frontend and required supporting services.
7. Perform approved forward-compatible migrations using the controlled procedure.
8. Verify all services run the intended release identity.
9. Test the live public website and authenticated flows.
10. Verify Telegram, payments, read-only market data and non-trading diagnostics.
11. Observe production health and execute rollback if release criteria fail.
12. Preserve safeguards preventing unapproved real-money execution.

Do not automatically activate personal or prop live trading as part of deployment.

If any mandatory gate remains blocked, complete everything else and leave the release pending, with its blocker and next action clearly stated.

---

# REQUIRED FINAL DELIVERABLES

Deliver:

1. Fully reconciled source and architecture.
2. Completed, tested backend and workers.
3. Certified focused instrument universe.
4. Integrated AI/ML and strategy engine.
5. Correct paper and demo execution workflows.
6. Complete Telegram-to-web feature parity.
7. Fully redesigned responsive public website, dashboard and administration.
8. Unified logos, favicons, icons and brand assets.
9. Complete light/dark/system theme implementation.
10. Secure authentication, subscriptions and permissions.
11. Verified staging and environment isolation.
12. Complete local test reports.
13. Browser screenshots and visual QA evidence.
14. Broker and provider certification evidence where authorized.
15. Updated requirement traceability and completion ledger.
16. Verified migration and rollback procedures.
17. Audit results and real soak evidence.
18. Approved merge commit, deployment identities and public URL checks when certified.

## FINAL REPORT FORMAT

Report these fields precisely:

```text
PROJECT: SignalRankAI

CURRENT STAGE:
STAGE ACCEPTANCE STATUS:

BRANCH:
SOURCE COMMIT:
MERGE COMMIT:
PRODUCTION RELEASE SHA:

IMPLEMENTED:
REPAIRED:
REDESIGNED:
NOT IMPLEMENTED:

PYTHON TESTS:
FRONTEND TESTS:
MOBILE TESTS:
BROWSER E2E:
SECURITY TESTS:
DATABASE TESTS:
TELEGRAM TESTS:
PAPER/DEMO BROKER TESTS:
MARKET DATA CERTIFICATION:

STAGING RESULT:
SOAK RESULT:

MERGE STATUS:
BACKEND DEPLOYMENT:
FRONTEND DEPLOYMENT:
WORKER DEPLOYMENTS:
SCHEMA VERSION:
PUBLIC WEBSITE STATUS:

EXTERNAL BLOCKERS:
UNRESOLVED DEFECTS:
NEXT REQUIRED ACTION:
```

Every test result must identify what actually ran and against which source revision.

Do not claim completion from a plan, a successful build, mock tests alone, or documentation.

Do not leave a stage half-finished just to start the next one.

Continue executing the remaining safely executable work instead of repeatedly asking for confirmation.

Only declare the overall project COMPLETE when all required implementation, verification, deployment and operational gates are genuinely satisfied.

**START NOW by inspecting the real local checkout and pulling all remote updates safely. Continue the current Stage 1 work first, then complete the remaining stages sequentially.**
