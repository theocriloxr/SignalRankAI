# SIGNALRANKAI — COMPLETE WEB APP + MOBILE APP DESIGN

## PRODUCT DIRECTION

Redesign the entire SignalRankAI customer experience and owner/admin experience.

This is not a cosmetic reskin.

The objective is to create a polished financial-intelligence platform that communicates:

**Trust. Control. Intelligence. Safety. Precision.**

SignalRank must NOT look like:

- a casino;
- a meme-coin dashboard;
- a generic crypto exchange clone;
- a developer admin panel;
- a collection of disconnected cards;
- an AI chatbot with trading buttons.

The desired experience should feel closer to a modern institutional trading product combined with premium consumer fintech simplicity.

The user should immediately understand:

```text
What is happening?
What opportunities are available?
What am I risking?
Is automation running?
Which account is being traded?
What requires my attention?
How is my account performing?
Why was something blocked?
How do I stop trading?
```

Everything must work in:

```text
Desktop
Laptop
Tablet
Mobile web
iOS-style mobile app
Android-style mobile app
Light mode
Dark mode
```

---

# 1. CORE VISUAL IDENTITY

## Brand personality

SignalRank should feel:

```text
Premium
Calm
Technical
Confident
Minimal
Reliable
Modern
Professional
```

Avoid excessive gradients, neon glows, flashing numbers, oversized crypto graphics, confetti or gamification.

Use animation primarily to communicate:

```text
state
status
navigation
loading
transitions
```

rather than decoration.

---

# 2. COLOR SYSTEM

## Dark theme

Primary application background:

```text
#070B14
```

Primary surface:

```text
#0D1424
```

Raised surface:

```text
#121B2E
```

Interactive/highlight surface:

```text
#18243A
```

Borders:

```text
#1F2B3D
```

Primary text:

```text
#F4F7FB
```

Secondary text:

```text
#A3AEC2
```

Muted text:

```text
#708096
```

Primary brand:

```text
#5B82FF
```

Brand hover:

```text
#7194FF
```

Supporting cyan:

```text
#24C8F2
```

Success:

```text
#20C985
```

Warning:

```text
#F3B643
```

Danger:

```text
#EF5C6B
```

Informational:

```text
#5EA4FF
```

---

## Light theme

Main background:

```text
#F5F7FB
```

Surface:

```text
#FFFFFF
```

Raised/secondary surface:

```text
#F9FAFC
```

Borders:

```text
#E3E8F0
```

Primary text:

```text
#0A1220
```

Secondary:

```text
#536174
```

Muted:

```text
#7C899A
```

Use the same semantic brand/success/warning/danger system adjusted as necessary for accessible contrast.

---

# 3. SEMANTIC COLOR RULE

Never communicate state through colour alone.

Always combine:

```text
icon
label
colour
```

Example:

```text
✓ Active
● Paper
! Attention required
× Blocked
```

Profit/loss colours must always have accompanying:

```text
+
-
Gain
Loss
```

or equivalent accessible labels.

---

# 4. TYPOGRAPHY

Use a clean modern sans-serif such as Geist or the project's most appropriate existing production font.

Visual hierarchy:

```text
Display       40–56
Page title    28–34
Section       20–24
Card title    15–18
Body          14–16
Metadata      12–13
Micro label   11–12
```

Financial figures should use tabular numerals.

Large financial values should not cause layout jumps when digits change.

---

# 5. SPACING SYSTEM

Use a consistent 4px base grid.

Common values:

```text
4
8
12
16
20
24
32
40
48
64
```

Card padding:

```text
Desktop: 20–24px
Tablet: 18–20px
Mobile: 16px
```

Main desktop gutters:

```text
24–32px
```

Mobile page gutters:

```text
16px
```

Never allow elements to touch viewport edges except intentional full-width mobile navigation/background regions.

---

# 6. CORNER RADIUS

Inputs:

```text
10px
```

Buttons:

```text
10–12px
```

Cards:

```text
14–18px
```

Sheets/modals:

```text
18–24px
```

Avoid extreme pill styling except:

```text
small filters
status chips
segmented controls
```

---

# 7. SHADOWS

Dark mode should primarily use:

```text
borders
tonal elevation
```

rather than heavy black shadows.

Light mode can use subtle elevation.

Floating menus, sheets and dialogs may use stronger elevation.

---

# 8. APPLICATION STRUCTURE

SignalRank consists of four major UI surfaces:

```text
Public website
Customer trading platform
Mobile trading application
Owner/Admin operations platform
```

They should share design tokens but use different information density.

---

# 9. PUBLIC WEBSITE

Main routes:

```text
/
Features
How It Works
Signals
Automation
Brokers
Security
Pricing
About
Status
Login
Register
Legal
```

---

# 10. LANDING PAGE

## Hero

Desktop:

```text
┌───────────────────────────────────────────────────────┐
│ SIGNALRANK                                             │
│                                                       │
│ Trading intelligence                                  │
│ built to think before it trades.                      │
│                                                       │
│ Analyse markets. Receive validated opportunities.     │
│ Trade manually, confirm execution, or automate        │
│ within your own risk rules.                           │
│                                                       │
│ [Start with SignalRank] [See how it works]            │
│                                                       │
│                LIVE PRODUCT PREVIEW                   │
└───────────────────────────────────────────────────────┘
```

The preview should show the real application design rather than fake marketing charts.

---

# 11. LANDING PAGE SECTIONS

After hero:

```text
SignalRank workflow
Multi-asset intelligence
Signals vs automated trading
Personal risk profiles
Broker integrations
Portfolio controls
Research/validation
Safety architecture
Performance transparency
Pricing
FAQ
Final CTA
```

Do not promise profitability.

Avoid unsupported performance claims.

---

# 12. AUTH DESIGN

Routes:

```text
/login
/register
/verify
/forgot-password where applicable
```

Desktop:

split screen.

Left:

```text
brand
short benefit
small product preview
```

Right:

```text
focused auth form
```

Mobile:

single focused card-free layout.

Keep authentication clean.

No marketing carousel.

---

# 13. CUSTOMER APP — DESKTOP NAVIGATION

Desktop left rail:

```text
SignalRank logo

Overview

TRADE
Signals
Positions
Orders

ANALYTICS
Performance
Portfolio

AUTOMATION
Automation
Brokers
Risk

ACCOUNT
Notifications
Activity
Billing
Settings

---
Help
Profile
```

Advanced-tier/customer research users may additionally see:

```text
Strategies
Research
```

Never expose admin tools in normal customer navigation.

---

# 14. DESKTOP APP SHELL

Structure:

```text
┌───────────────┬─────────────────────────────────────────────┐
│               │ Top bar                                     │
│ Sidebar       ├─────────────────────────────────────────────┤
│               │                                             │
│               │ Main application content                    │
│               │                                             │
│               │                                             │
└───────────────┴─────────────────────────────────────────────┘
```

Top bar includes:

```text
Page context
Global search/command palette
System status
Notifications
Account switcher
Profile
```

Do not create an oversized header.

---

# 15. OVERVIEW DASHBOARD

The dashboard should answer all important questions in approximately five seconds.

Top section:

```text
Good evening, Theo

Trading status
AUTO ON

Main MT5
Connected

Risk profile
Balanced

System
Healthy
```

Then primary metrics:

```text
Account equity
Today's P/L
Risk used today
Open positions
```

---

# 16. DASHBOARD LAYOUT

Desktop:

```text
┌────────────────────────────────────────────────────────┐
│ Trading Status           Broker          System        │
├───────────┬───────────┬───────────┬────────────────────┤
│ Equity    │ Today P/L │ Risk Used │ Positions          │
├───────────────────────────────────┬────────────────────┤
│ Portfolio / Equity Curve          │ Risk Budget        │
│                                   │                    │
├───────────────────────────────────┼────────────────────┤
│ Active Positions                  │ Attention Required │
├───────────────────────────────────┴────────────────────┤
│ Latest Opportunities                                  │
└────────────────────────────────────────────────────────┘
```

---

# 17. TRADING STATUS CARD

This should be one of the most important UI components.

Example:

```text
Automatic Trading

● ACTIVE

Main MT5
Balanced risk profile

New automatic entries are allowed.

[Pause Auto Trading]
[Trading Settings]
```

If blocked:

```text
Automatic Trading

! PAUSED

Daily risk limit reached.

Existing positions are still being managed.

[View Details]
```

---

# 18. RISK BUDGET

Create a visual risk meter.

Example:

```text
Today's Risk Budget

████████░░░░░░

Used       1.4%
Remaining  1.6%

Daily limit 3.0%
```

Do not make the visual resemble gambling chips or a game energy bar.

---

# 19. ATTENTION REQUIRED PANEL

Priority ordered:

```text
Critical
Action required
Informational
```

Example:

```text
Broker needs attention
MT5 session authentication expired.

[Reconnect]
```

Another:

```text
Strategy paused
Momentum Breakout v4 has been temporarily quarantined.

No action required.
```

---

# 20. SIGNALS PAGE

Header:

```text
Signals

Validated market opportunities matched to your profile.
```

Controls:

```text
All
Active
Waiting
Executed
Expired
Blocked

Search
Filters
```

Desktop can use table/card hybrid.

Mobile uses cards only.

---

# 21. SIGNAL CARD

Primary hierarchy:

```text
BTC / USDT                     LONG

High Quality

4H · Momentum + Market Structure

Entry
$67,240 – $67,480

Stop
$65,910

Targets
$68,810
$70,120
$72,430

R:R
1 : 2.8

Expires
18 min

Your status
✓ Eligible
AUTO_CONFIRM

[Review Trade]
```

---

# 22. SIGNAL CONFIDENCE

Avoid presenting AI confidence as false certainty.

Use labels such as:

```text
Exceptional
High
Moderate
Low
```

Advanced details can display numeric scores.

Do not present:

```text
94% GUARANTEED
```

or similar language.

---

# 23. SIGNAL DETAIL PAGE

Desktop layout:

```text
LEFT 2/3
────────────────────
Price chart
Entry / SL / targets
Signal thesis
Market structure
Strategy evidence
News/regime context
Lifecycle timeline

RIGHT 1/3
────────────────────
Signal status
Your account eligibility
Execution status
Risk preview
Trade actions
Expiry
```

---

# 24. SIGNAL EXPLANATION

Customer summary:

```text
Why this opportunity qualified

✓ Higher-timeframe trend supports LONG
✓ Market structure shifted bullish
✓ Momentum confirms continuation
✓ Current liquidity is acceptable
✓ Portfolio exposure remains within your limits

Main risks

! Nearby resistance
! Volatility is above its 30-day median
```

Then:

```text
View Advanced Analysis
```

---

# 25. ADVANCED SIGNAL ANALYSIS

Expandable areas:

```text
Strategy evidence
Market regime
Multi-timeframe analysis
Liquidity
Technical indicators
News/events
Risk factors
Model confidence
Execution quality
Research history
```

Customer visibility should respect tier and proprietary IP restrictions.

---

# 26. WHY WAS THIS BLOCKED?

Every signal with execution disabled should show:

```text
Execution blocked

The market opportunity is still valid, but SignalRank will not automatically trade it.

Reason:
Your crypto exposure would exceed 35%.

Current crypto exposure: 31%
Projected exposure: 43%

[View Portfolio]
```

This should be a first-class product feature.

---

# 27. POSITIONS PAGE

Tabs:

```text
Open
Pending
Closed
```

Position card/table displays:

```text
instrument
side
strategy
account
entry
current price
size
unrealized P/L
risk remaining
stop
next target
management mode
```

---

# 28. POSITION DETAIL

Structure:

```text
Instrument + state

Current P/L
Position size
Entry
Current price
Stop
Targets

Chart

Position timeline

Risk
Execution details
Strategy

Actions
```

Actions where permitted:

```text
Partial close
Close position
Move stop
Pause automatic management
```

Dangerous actions require confirmation.

---

# 29. POSITION TIMELINE

Example:

```text
14:03 Signal generated
14:04 Eligible for your account
14:04 Order submitted
14:04 Broker confirmed fill
14:31 TP1 reached
14:31 Stop moved to break-even
15:46 Position closed
```

---

# 30. ORDERS PAGE

Provide proper states:

```text
Intent created
Submitting
Submitted
Acknowledged
Partially filled
Filled
Rejected
Cancelled
Reconciliation required
```

Never simplify uncertain broker state to success/failure incorrectly.

---

# 31. AUTO-CONFIRM DESIGN

AUTO_CONFIRM must feel deliberate but fast.

Desktop side sheet.

Mobile bottom sheet/full-screen confirmation.

Structure:

```text
Review Trade

BTC/USDT
LONG

Account
Bybit — Crypto

Entry
67,320

Current
67,340

Position
0.015 BTC

Planned risk
$82
0.48%

Estimated costs
$X

Portfolio effect
Crypto exposure:
24% → 31%

Signal expires in 3:42

[Reject]
[Execute Trade]
```

---

# 32. EXECUTION SUCCESS

Do NOT immediately show:

```text
Trade executed
```

when merely submitted.

States:

```text
Submitting order...
↓
Broker acknowledged
↓
Filled
```

Successful fill screen:

```text
Trade opened

BTC/USDT
0.015 BTC

Filled
67,352

Requested
67,340

Slippage
+0.018%

[View Position]
```

---

# 33. AUTOMATION PAGE

This is the main command centre for automatic trading.

Top:

```text
Automatic Trading

ACTIVE
Main MT5

[Pause]
```

Then:

```text
Trading mode
Risk profile
Enabled markets
Execution protection
News rules
Portfolio limits
Strategy permissions
```

---

# 34. TRADING MODE SELECTOR

Large cards:

```text
Signals Only
Receive opportunities and trade manually.

Paper
Simulated execution only.

Confirm Each Trade
SignalRank prepares orders; you approve each one.

Automatic
Eligible opportunities may execute automatically.
```

Use internal values:

```text
SIGNALS_ONLY
PAPER
AUTO_CONFIRM
AUTO
```

---

# 35. RISK PAGE

Start simple.

Sections:

```text
Risk Profile
Trade Risk
Daily Limits
Portfolio Limits
Drawdown Protection
Advanced
```

Primary preset selection:

```text
Conservative
Balanced
Growth
Custom
```

---

# 36. RISK SETTING EXAMPLE

Instead of:

```text
Risk = 1
```

show:

```text
Risk per trade

0.50%

On your current $10,000 equity:

Approximate planned loss at Stop Loss:
$50

Abnormal market gaps can exceed planned loss.
```

---

# 37. RISK IMPACT PREVIEW

Before saving material changes:

```text
Risk change

0.5% → 1.0%

Maximum planned risk per trade:
$50 → $100

Daily risk limit:
$150 → $300

[Cancel]
[Confirm Changes]
```

---

# 38. BROKERS PAGE

Header:

```text
Broker Accounts

Connect and manage the accounts SignalRank can analyse or trade.
```

Account cards.

Example:

```text
MT5
Main FX

● Connected

LIVE
USD

Equity
$12,420

Free Margin
$9,800

Trading mode
AUTO

Last sync
8 seconds ago

[Manage]
```

---

# 39. BROKER ACCOUNT DETAIL

Sections:

```text
Overview
Connection
Capabilities
Trading Mode
Markets
Risk
Activity
Security
```

Show capability matrix.

Example:

```text
Market orders        ✓
Limit orders         ✓
Stop Loss            ✓
Take Profit          ✓
Partial exit         ✓
Automatic execution  ✓
```

---

# 40. CONNECT BROKER FLOW

Wizard:

```text
Choose broker
↓
Account connection
↓
Verify
↓
Capabilities detected
↓
Choose purpose
↓
Choose trading mode
↓
Risk review
↓
Complete
```

Connecting a broker must never automatically enable live AUTO.

---

# 41. PERFORMANCE PAGE

Top switch:

```text
Signals
Paper
Live
```

Never combine evidence classes.

Key metrics:

```text
Net P/L
Trade count
Win rate
Expectancy
Profit factor
Maximum drawdown
Average risk
```

Graphs:

```text
Equity
Drawdown
Monthly performance
Asset contribution
Strategy contribution
```

---

# 42. PERFORMANCE EXPLANATIONS

Hover/tap info:

```text
Expectancy

The average amount gained or lost per trade after accounting for wins and losses.
```

Make advanced statistics understandable.

---

# 43. PORTFOLIO PAGE

Display:

```text
Total exposure
Long/short exposure
Asset-class exposure
Currency exposure
Correlation clusters
Risk concentration
```

Example:

```text
Exposure alert

Your portfolio is highly concentrated in crypto LONG positions.

BTC
ETH
SOL

SignalRank is restricting additional correlated exposure.
```

---

# 44. ACTIVITY CENTER

Chronological account activity:

```text
Trade opened
Signal received
Execution blocked
Broker connected
Risk setting changed
Auto paused
Strategy quarantined
Subscription changed
Login
```

Search/filter.

---

# 45. NOTIFICATION CENTER

Grouped by:

```text
Trading
Broker
Risk
Account
System
```

Allow read/unread.

Do not make critical alerts disappear when dismissed.

---

# 46. NOTIFICATION SETTINGS

Per event:

```text
Web
Telegram
Email
Push
```

Example:

```text
New Signal           Telegram ✓ Web ✓ Push ✓
Trade Opened         Telegram ✓ Web ✓
Execution Blocked    Telegram ✓ Web ✓ Email ✓
Broker Disconnected  All critical channels
```

---

# 47. SETTINGS

Sections:

```text
Profile
Appearance
Trading Preferences
Security
Sessions
Telegram
Notifications
Privacy
```

---

# 48. BILLING / PLAN

Show:

```text
Current tier
Billing state
Renewal
Usage/entitlements
Upgrade
Invoices
Payment method where applicable
```

Do not expose hardcoded tier assumptions.

---

# 49. TIER FEATURE UX

If gated:

```text
Automatic Trading

Available with Pro Auto.

Your current plan includes manual and paper trading.

[Compare Plans]
```

Avoid hiding the feature entirely when discovery is useful.

Do not use manipulative upgrade tactics.

---

# 50. EMPTY STATES

Examples:

```text
No active positions

SignalRank currently has no open positions on this account.

[View Signals]
```

```text
No eligible signals

The engine is running normally.
Current market opportunities do not meet your profile requirements.
```

```text
No broker connected

You can still receive and manually trade signals.

[Connect Broker]
```

---

# 51. ERROR STATES

Never:

```text
Something went wrong.
```

unless no more specific explanation is possible.

Example:

```text
Broker connection unavailable

SignalRank cannot verify your MT5 account right now.

New automatic entries are paused.

Existing positions continue according to their current management state.

[Retry]
[Broker Settings]
```

---

# 52. DEGRADED SERVICE BANNER

Example:

```text
Partial service degradation

FX signals temporarily unavailable.

Crypto and equities are operating normally.

Automatic FX entries are paused.
```

Do not display generic platform outage if only one subsystem is affected.

---

# 53. SYSTEM STATUS

Customer-friendly status:

```text
Market data       Healthy
Signal engine     Healthy
Broker sync       Healthy
Automation        Active
Risk controls     Healthy
```

Owner/admin sees deeper technical metrics.

---

# 54. EMERGENCY STOP

Persistent but unobtrusive access.

Desktop:

risk/automation page + account command menu.

Mobile:

More → Trading Safety.

Flow:

```text
Emergency Stop

What do you want to stop?

○ New automatic trades
○ Automatic trading + management
○ Emergency close eligible managed positions

[Cancel]
[Continue]
```

The destructive close action requires additional confirmation.

---

# 55. GLOBAL SEARCH / COMMAND PALETTE

Desktop:

```text
Ctrl/Cmd + K
```

Search:

```text
BTC
signals
positions
broker
settings
activity
```

Safe commands only.

Never enable dangerous one-click execution through command palette.

---

# 56. MOBILE APPLICATION ARCHITECTURE

If no native mobile project currently exists, create a mobile app architecture using an appropriate production framework such as Expo/React Native while sharing:

```text
API contracts
types
design tokens
validation schemas
reason codes
```

with the web app where practical.

Do not merely wrap the website in a WebView and call it the mobile app.

---

# 57. MOBILE BOTTOM NAVIGATION

Primary bottom navigation:

```text
Overview
Signals
Positions
Performance
More
```

Maximum five primary destinations.

---

# 58. MOBILE OVERVIEW

Structure:

```text
Good evening

AUTO ●
Main MT5

Equity
$12,450

Today
+$86

Risk used
1.1 / 3.0%

[Active Positions]

Attention Required

Latest Signals
```

Important information should appear before charts.

---

# 59. MOBILE SIGNAL CARD

Compact:

```text
BTC/USDT        LONG

High Quality

4H
Momentum + Structure

Entry
67,240–67,480

R:R
1:2.8

Expires 18m

AUTO_CONFIRM

[Review]
```

---

# 60. MOBILE SIGNAL DETAIL

Full-screen detail.

Sticky bottom action bar:

```text
[Trade / Review Trade]
```

but ensure it never overlaps page content.

Hide when action is unavailable.

---

# 61. MOBILE POSITION CARD

Example:

```text
EUR/USD
LONG

+1.4R
+$72

Entry   1.0843
Now     1.0871

TP1 ✓
TP2 next

[View Position]
```

---

# 62. MOBILE MORE PAGE

Sections:

```text
Automation
Brokers
Risk
Portfolio
Orders
Notifications
Activity
Billing
Settings
Help
```

---

# 63. MOBILE SHEETS

Use bottom sheets for:

```text
filters
quick settings
order preview
confirmation
small forms
```

Use full pages for:

```text
risk configuration
broker setup
complex settings
position detail
```

---

# 64. MOBILE TOUCH TARGETS

Minimum:

```text
44x44 logical pixels
```

Critical actions should have larger targets.

---

# 65. MOBILE SAFE AREAS

Handle:

```text
iPhone Dynamic Island/notch
bottom home indicator
Android navigation bars
keyboard
```

Never allow critical actions behind system UI.

---

# 66. MOBILE KEYBOARD

Forms must scroll focused fields into view.

No input should be hidden behind keyboard.

---

# 67. MOBILE OFFLINE STATE

If connection is lost:

```text
You're offline

Displayed trading data may be outdated.
Trading actions are temporarily unavailable.
```

Reconcile state on reconnect.

---

# 68. PUSH NOTIFICATION DESIGN

Examples:

```text
SignalRank

BTC/USDT opportunity
High-quality LONG setup matched your profile.

Expires in 18 minutes.
```

AUTO_CONFIRM:

```text
Trade confirmation required

EUR/USD LONG is ready for review.

3m 40s remaining.
```

Safety:

```text
Automatic trading paused

Your daily loss limit has been reached.
```

Never put sensitive credentials/account information in push notifications.

---

# 69. APP LOCK / BIOMETRICS

If supported:

```text
Face ID
Touch ID
device biometrics
```

for re-entry and high-risk actions.

Do not use biometrics as a substitute for backend authentication.

---

# 70. NATIVE MOBILE SECURITY SCREEN

Show:

```text
Signed-in devices
Last login
Biometric unlock
App lock
Session timeout
```

---

# 71. OWNER / ADMIN PRODUCT

Admin navigation:

```text
Overview

USERS
Users
Subscriptions
Broker Accounts

TRADING
Signals
Positions
Executions
Risk
Portfolio

STRATEGIES
Strategies
Strategy Health
Research
Experiments
WFO
Backtest Audits

SYSTEM
Providers
Workers
Schedulers
Queues
Incidents
System Health

GOVERNANCE
Audit Log
Feature Flags
Policies
Release Evidence

CONFIGURATION
Entitlements
Brokers
Markets
Notifications
Settings
```

Staging only:

```text
QA
```

---

# 72. OWNER OVERVIEW

At top:

```text
PRODUCTION

Git SHA
Schema
Services
System Health
```

Then:

```text
Signals today
Deliveries
Executions
Active positions
Blocked executions
Critical incidents
Provider health
Strategy health
```

---

# 73. OWNER ENGINE FUNNEL

Visual:

```text
Scanned
 ↓
Ideas
 ↓
Candidates
 ↓
Risk Pass
 ↓
ML Pass
 ↓
Eligible
 ↓
Delivered
 ↓
Executed
```

Each step clickable.

This helps diagnose signal droughts.

---

# 74. STRATEGY HEALTH PAGE

Table:

```text
Strategy
Version
State
Trades
Expectancy
Profit Factor
Sharpe
Drawdown
Live Drift
Updated
```

State:

```text
Healthy
Watch
Degraded
Quarantined
Halted
```

---

# 75. STRATEGY DETAIL

Tabs:

```text
Overview
Performance
Regimes
WFO
Experiments
Backtest Audit
Live Health
History
```

---

# 76. RESEARCH PAGE

Display research lifecycle:

```text
Hypothesis
↓
Experiments
↓
Integrity
↓
WFO
↓
Multiple Testing
↓
Shadow
↓
Forward
↓
Canary
↓
Production
```

Each gate displays:

```text
PASS
FAIL
WAITING
BLOCKED
```

---

# 77. EXPERIMENT PAGE

Show:

```text
Hypothesis
Parameters
Dataset
Features
Code version
Trial lineage
Metrics
DSR
WFO
Regime stability
Execution stress
Risk survival
Verdict
```

No raw JSON as primary UI.

JSON/download can exist under advanced tools.

---

# 78. BACKTEST AUDIT PAGE

Matrix:

```text
Look-ahead          PASS
Survivorship        PASS
Repainting          PASS
Costs               PASS
Fill assumptions    WARN
Parameter fitting   PASS
Regime coverage     PASS
Alignment           PASS
```

Click any row for evidence.

---

# 79. INCIDENT CENTER

Cards ordered by severity.

Example:

```text
CRITICAL

MT5 reconciliation failure

Affected accounts
7

New execution
PAUSED

Started
4m ago

[Investigate]
```

---

# 80. PROVIDER HEALTH

Rows/cards:

```text
Provider
Service
Health
Latency
Data age
Error rate
Circuit state
Last success
```

---

# 81. WORKER HEALTH

Show:

```text
role
heartbeat
current job
last success
queue lag
error count
version
```

---

# 82. AUDIT LOG

Filter:

```text
actor
user
signal
strategy
broker
action
severity
date
environment
```

Display before/after changes where relevant.

---

# 83. RELEASE EVIDENCE PAGE

Show:

```text
Candidate SHA
Build
Schema
Tests
Security
Deployment
Staging soak
Demo broker
Audits
Production eligibility
```

This should align with SignalRank's evidence ledger.

---

# 84. STAGING QA PAGE

Only available in staging.

Allow deterministic safe scenarios:

```text
Generate test signal
Trigger broker rejection
Trigger timeout
Create partial fill
Trigger daily risk block
Disconnect provider
Expire signal
Trigger strategy quarantine
Test duplicate callback
```

Must never be exposed in production.

---

# 85. CHART DESIGN

Charts must:

```text
support hover/tap
support responsive labels
use accessible legends
avoid misleading Y scales
support loading/empty/error states
```

Charts should not dominate the dashboard unnecessarily.

---

# 86. TABLE DESIGN

Desktop tables:

```text
sticky header where useful
sortable columns
filters
pagination
row actions
column preferences for advanced pages
```

Tablet/mobile:

transform into cards when horizontal scrolling would hurt usability.

---

# 87. BUTTON SYSTEM

Primary:

high-intent main action.

Secondary:

normal alternative.

Tertiary:

low emphasis.

Danger:

destructive actions only.

Never have three unrelated primary buttons in one card.

---

# 88. INPUT SYSTEM

Inputs need:

```text
visible label
optional helper
unit
validation
error
disabled state
```

Do not rely on placeholder text as a label.

---

# 89. STATUS CHIP SYSTEM

Canonical visual states:

```text
Active
Paused
Paper
Live
Connected
Disconnected
Pending
Blocked
Expired
Healthy
Warning
Critical
```

Do not create page-specific equivalents with different wording.

---

# 90. MODALS

Use modal/dialog only for:

```text
short confirmation
destructive actions
critical consent
```

Do not place long multi-step configuration forms inside modals.

---

# 91. TOASTS

Toasts are supplementary.

Important financial state changes must also persist in:

```text
page state
activity
notifications
```

Never rely solely on a toast saying:

```text
Trade executed
```

---

# 92. LOADING DESIGN

Use skeletons matching final content.

Examples:

```text
Loading account...
Syncing broker...
Updating position...
Checking eligibility...
```

Avoid generic infinite spinners.

---

# 93. MICRO-INTERACTIONS

Use subtle motion:

```text
150–250ms
```

for:

```text
hover
sheet
accordion
tab
state transition
```

Respect reduced-motion preferences.

---

# 94. RESPONSIVE BREAKPOINT PHILOSOPHY

Do not merely shrink desktop.

Use layouts appropriate to:

```text
320–479
480–767
768–1023
1024–1439
1440+
```

Exact framework breakpoints may differ.

---

# 95. DESKTOP DENSITY

Trading/admin pages can use higher data density.

Customer pages should remain spacious.

Research/admin tables can be compact.

---

# 96. ACCESSIBILITY

Target WCAG 2.2 AA.

Test:

```text
keyboard
screen reader
focus
contrast
zoom
reduced motion
error announcements
dialog focus trap
```

---

# 97. DESIGN SYSTEM COMPONENTS

Build reusable production components such as:

```text
AppShell
Sidebar
MobileNav
TopBar
PageHeader
MetricCard
StatusCard
SignalCard
PositionCard
RiskMeter
AccountCard
StatusBadge
ReasonPanel
AlertBanner
EmptyState
ErrorState
Skeleton
DataTable
FilterBar
SegmentedControl
BottomSheet
ConfirmationDialog
ActivityTimeline
HealthIndicator
TradePreview
ExecutionReceipt
PortfolioExposureCard
```

Do not recreate the same component differently on every page.

---

# 98. SHARED DESIGN TOKENS

Where web/mobile share a monorepo, create common tokens for:

```text
colors
spacing
radius
semantic status
typography scale
```

Do not share browser-specific components directly into native code.

Share semantics, not inappropriate implementation.

---

# 99. WEB IMPLEMENTATION

Use the project's existing frontend architecture.

If currently Next.js:

retain Next.js App Router unless strong repository evidence requires otherwise.

Use production-quality:

```text
server/client boundaries
loading states
error boundaries
typed APIs
auth guards
entitlement guards
responsive design
```

Do not redesign by replacing working architecture unnecessarily.

---

# 100. MOBILE IMPLEMENTATION

If a native app is being created:

recommended structure:

```text
apps/web
apps/mobile
packages/ui-tokens
packages/api-client
packages/types
packages/validation
```

Adapt to the actual repository.

Do not introduce a monorepo migration solely for aesthetic reasons if the repository architecture makes this unsafe.

---

# 101. AUTH PARITY

Web/mobile should use the same canonical user identity and entitlements.

A user's:

```text
tier
brokers
risk
settings
signals
positions
notifications
```

must remain synchronized.

---

# 102. WEB ↔ TELEGRAM ↔ MOBILE PARITY

The same canonical signal should have the same:

```text
signal ID
status
entry
stop
targets
expiry
execution state
```

across:

```text
web
mobile
Telegram
```

Presentation can differ.

Truth cannot.

---

# 103. CUSTOMER UX LANGUAGE

Use simple language first.

Prefer:

```text
Automatic Trading
```

rather than:

```text
Autonomous Execution Engine
```

Prefer:

```text
Why wasn't this trade opened?
```

rather than:

```text
Execution rejection diagnostics
```

Advanced screens may use technical terms.

---

# 104. DESIGN COPY STYLE

Short.

Clear.

Calm.

Never hype.

Example:

Bad:

```text
🚀 MASSIVE SIGNAL DETECTED!!! DON'T MISS OUT
```

Correct:

```text
BTC/USDT opportunity

A high-quality LONG setup currently matches your profile.
```

---

# 105. NO-TUTORIAL STANDARD

The design is only complete if a first-time customer can discover how to:

```text
register
understand their plan
view a signal
connect a broker
choose Signals/Paper/Confirm/Auto
set risk
turn auto trading on
see which account is used
understand a blocked trade
see a live position
pause automation
view performance
```

without external instructions.

---

# 106. FINAL CUSTOMER ROUTE MAP

Web application should ultimately provide equivalent routes/components for:

```text
/app
/app/signals
/app/signals/[id]
/app/positions
/app/positions/[id]
/app/orders
/app/performance
/app/portfolio
/app/automation
/app/risk
/app/brokers
/app/brokers/[id]
/app/activity
/app/notifications
/app/billing
/app/settings
/app/settings/security
/app/settings/telegram
```

Advanced/customer-research where entitled:

```text
/app/strategies
/app/research
```

Adjust to existing routing where appropriate instead of duplicating working routes.

---

# 107. OWNER ROUTE MAP

Equivalent owner/admin areas:

```text
/owner
/owner/users
/owner/subscriptions
/owner/signals
/owner/positions
/owner/executions
/owner/risk
/owner/strategies
/owner/strategy-health
/owner/research
/owner/experiments
/owner/backtest-audits
/owner/providers
/owner/workers
/owner/schedulers
/owner/incidents
/owner/audit
/owner/policies
/owner/entitlements
/owner/releases
```

Staging only:

```text
/owner/qa
```

Route names may follow existing architecture.

---

# 108. APP NAVIGATION MAP

Bottom navigation:

```text
Overview
Signals
Positions
Performance
More
```

More:

```text
Automation
Brokers
Risk
Portfolio
Orders
Notifications
Activity
Billing
Settings
Support
```

---

# 109. DESIGN REVIEW REQUIREMENT

Codex must review existing screens before implementing.

Do not discard working functionality.

For every route determine:

```text
KEEP
REDESIGN
MERGE
REMOVE
NEW
```

Preserve all working features.

---

# 110. FRONTEND COMPLETION STANDARD

Do not consider a route implemented because a page component exists.

It is complete only when:

```text
real backend connected
real authorization
real state
loading handled
empty handled
error handled
permissions handled
mobile handled
tablet handled
desktop handled
light mode handled
dark mode handled
keyboard/accessibility handled
tests added
```

---

# 111. NO PLACEHOLDER UI

Prohibit production UI such as:

```text
Lorem ipsum
Demo data
Fake P/L
Fake signal
Placeholder chart
Coming soon
Mock broker
Hardcoded connected state
```

unless strictly inside an explicit staging/test-only environment.

---

# 112. DESIGN TESTING

At minimum test:

```text
320px
360px
375px
390px
414px
430px
768px
1024px
1280px
1440px
1920px
```

Include actual mobile/browser testing where possible.

---

# 113. CRITICAL USER JOURNEYS

Test visually and functionally:

```text
register
login
onboarding
signals-only
paper
broker connection
AUTO_CONFIRM
AUTO activation
signal execution
blocked execution
active position
manual intervention
broker disconnect
risk limit
emergency stop
performance
tier gating
mobile navigation
dark/light switch
```

---

# 114. DESIGN ACCEPTANCE STANDARD

The final application should feel like **one product**, not separate pages built at different times.

There must be consistent:

```text
spacing
typography
colour
cards
buttons
navigation
status
copy
forms
error handling
loading
responsive behavior
```

---

# 115. FINAL CODEX DESIGN AUDIT

Before completion, Codex must inspect the entire web and mobile application and ask:

```text
Does every page look like SignalRank?

Is any screen still using the old inconsistent design?

Are there any clipped or overflowing elements?

Does mobile feel intentionally designed rather than compressed desktop?

Can a new user understand every core workflow?

Are dangerous actions clearly distinguished?

Can users always tell PAPER from LIVE?

Can users always tell whether AUTO is active?

Can users always tell which broker/account is selected?

Can users understand why execution was blocked?

Are all values real backend values?

Are light and dark themes complete?

Are all customer-facing error messages understandable?

Are all admin pages consistent?

Is every backend capability requiring UI actually exposed?

Is every UI control connected to functioning backend logic?
```

Fix all material findings.

Run a second complete design audit after the fixes.

---

# FINAL PRODUCT FEEL

SignalRank should feel like:

```text
A sophisticated trading system underneath
+
A calm, simple financial product on top.
```

Users should never need to understand the complexity of:

```text
WFO
DSR
PBO
feature contracts
broker reconciliation
distributed locking
portfolio factor models
```

just to use SignalRank.

But advanced users, researchers and administrators should be able to inspect those systems when appropriate.

The product should progressively reveal complexity.

The default customer experience should remain:

```text
See opportunity
Understand opportunity
Understand risk
Choose how to participate
Track what happened
Remain in control
```

That principle should drive every design decision.