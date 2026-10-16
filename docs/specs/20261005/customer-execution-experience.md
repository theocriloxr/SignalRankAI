# FRONTEND, CUSTOMER UX, PERSONALIZATION & BROKER EXECUTION EXPERIENCE

Everything implemented in the backend must be surfaced correctly in the SignalRankAI frontend.

Do not implement powerful backend capabilities that ordinary customers cannot understand, configure, inspect, or safely control from the website.

The frontend must be designed so that a new customer can understand how SignalRank works **without reading external documentation or watching a tutorial**.

The product should explain itself through:

- clear information hierarchy;
- sensible defaults;
- progressive disclosure;
- contextual explanations;
- inline validation;
- meaningful status indicators;
- short microcopy;
- obvious next actions;
- clear confirmation flows;
- transparent reasons when actions are blocked.

Avoid overwhelming users with internal quantitative terminology unless they explicitly open advanced details.

---

# 44. CUSTOMER TRADING MODES

Implement the following canonical per-user/per-broker-account modes:

```text
SIGNALS_ONLY
PAPER
AUTO_CONFIRM
AUTO
```

## SIGNALS_ONLY

SignalRank:

- analyzes markets;
- generates validated opportunities;
- applies user/tier eligibility;
- sends eligible signals;
- tracks outcomes.

The customer trades manually.

Connecting a broker must NOT automatically enable auto-trading.

---

## PAPER

SignalRank performs simulated execution using the same eligible signals and risk configuration where possible.

Clearly label everything as:

```text
PAPER
SIMULATED
NO REAL MONEY
```

Paper and live statistics must never be mixed.

---

## AUTO_CONFIRM

SignalRank finds a valid trade but requests confirmation before execution.

Example UI:

```text
EUR/USD — LONG

Signal confidence: 86%
Strategy: Market Structure + Momentum
Entry: 1.17320
Stop Loss: 1.17040
TP1: 1.17600
TP2: 1.17890

Account:
MT5 — Account ••••4821

Estimated risk:
0.50% / ₦X or $X

Estimated position:
0.XX lots

Current portfolio exposure:
Low

[Reject]
[Review]
[Execute Trade]
```

The confirmation must expire with the signal.

Never execute an expired confirmation.

---

## AUTO

SignalRank may execute automatically only when ALL required eligibility, risk, broker, platform and strategy checks pass.

The UI must clearly show:

```text
AUTO TRADING
ON
```

and make disabling it immediate.

---

# 45. SEPARATE SIGNAL AND EXECUTION ELIGIBILITY

This must exist in both backend and UI.

Never treat:

```text
valid signal
```

as synonymous with:

```text
valid execution
```

Expose two separate states:

```text
Signal eligible
Execution eligible
```

Example:

```text
Signal
✓ Valid
✓ Eligible for your plan
✓ Matches your profile

Execution
✕ Blocked

Reason:
Insufficient available margin.
```

The customer should still receive the signal when manual delivery is permitted.

---

# 46. EXPLAIN WHY SOMETHING DID NOT TRADE

One of the most important UX requirements is a universal:

```text
Why didn't this trade execute?
```

experience.

Every blocked or skipped trade should expose a human-readable reason.

Possible examples:

```text
Auto trading is turned off.

This asset is disabled in your profile.

Your daily loss limit has been reached.

Your broker is disconnected.

The market is currently closed.

Spread is above your permitted maximum.

Available margin is insufficient.

The opportunity no longer meets SignalRank's execution threshold.

This trade would exceed your portfolio exposure limit.

You already have correlated exposure.

The signal expired before execution.

SignalRank's global safety switch temporarily blocked execution.

Broker rejected the order.

The price moved outside the permitted entry range.
```

Include technical details under:

```text
View details
```

for advanced customers/admins.

Do not show raw internal errors to ordinary users.

---

# 47. CUSTOMER ONBOARDING

Create a simple guided first-run flow.

Do not present a huge settings screen immediately.

Suggested onboarding:

```text
Welcome
↓
What do you want SignalRank to do?
↓
Choose markets
↓
Choose risk preference
↓
Connect broker (optional)
↓
Choose trading mode
↓
Review settings
↓
Finish
```

### Step 1 — Intent

Ask something simple:

```text
How do you want to use SignalRank?
```

Cards:

```text
Get trading signals
Trade on paper first
Confirm trades before SignalRank places them
Let SignalRank automatically trade eligible opportunities
```

Map these internally to the canonical modes.

---

# 48. PROGRESSIVE DISCLOSURE

A beginner should not have to understand:

```text
CVaR
DSR
PBO
MAE
MFE
calibration
embargo
purged WFO
```

to use SignalRank.

Default customer screens should communicate concepts like:

```text
Signal quality
Risk
Market conditions
Account exposure
Execution status
```

Advanced metrics can live under:

```text
Advanced analytics
Research evidence
Technical details
```

Owner/admin/research users can see the full quantitative evidence.

---

# 49. RISK PROFILE UX

Provide simple starting presets:

```text
Conservative
Balanced
Growth
Custom
```

These are UI concepts, not permission to bypass hard risk limits.

Each preset should explain itself.

Example:

### Conservative

```text
Lower risk per trade
Fewer simultaneous positions
Stricter exposure limits
Designed to prioritise capital preservation
```

### Balanced

```text
Moderate risk and exposure
Balanced opportunity frequency
```

### Growth

```text
Higher permitted risk within SignalRank's platform safety limits
```

### Custom

Expose advanced controls.

The platform must enforce hard maximums regardless of selected/custom settings.

---

# 50. SHOW EFFECT OF RISK CHANGES

When customers change risk settings, show the practical consequence.

Instead of only:

```text
Risk per trade: 1%
```

show:

```text
Account equity: $10,000

Risk per trade:
1.0%

Approximate maximum planned loss if stop is filled normally:
$100

This does not include abnormal gaps or execution beyond the intended stop.
```

If the user moves risk higher, update the estimate immediately.

---

# 51. BROKER CONNECTION CENTER

Create a polished:

```text
Broker Accounts
```

area.

Each account card should show:

```text
Broker
Account alias
Masked account ID
Connection status
Account type
Currency
Balance
Equity
Free margin
Trading mode
Auto-trading status
Last successful sync
Supported capabilities
```

Possible status states:

```text
Connected
Attention required
Disconnected
Authentication expired
Read-only
Trading unavailable
Temporarily unavailable
```

Never expose credentials.

---

# 52. BROKER CAPABILITY MATRIX

The UI should explain differences between connected brokers.

Example:

```text
MT5 Account
✓ Account analytics
✓ Signal matching
✓ Market orders
✓ Stop Loss
✓ Take Profit
✓ Partial exits
✓ Auto-confirm
✓ Auto execution

Broker X
✓ Account analytics
✓ Signal matching
✕ Automatic execution
```

Do not offer unsupported controls.

---

# 53. MULTIPLE BROKER ACCOUNTS

Support users connecting multiple accounts.

Each account can independently have:

```text
trading mode
risk profile
asset classes
allowed assets
strategies
exposure limits
execution settings
```

Example UI:

```text
My Accounts

MT5 — Main FX
AUTO
0.5% risk/trade
FX only

Bybit — Crypto
AUTO_CONFIRM
1% risk/trade
Crypto only

MT5 — Demo
PAPER / TEST
```

Do not assume one account per user.

---

# 54. BROKER CONNECT DOES NOT ENABLE AUTO

The UX must enforce:

```text
Connect Broker
≠
Enable Auto Trading
```

After connection, default to the safest appropriate mode.

The user must explicitly enable automated execution.

Before first AUTO activation show a clear review screen containing:

```text
Broker account
Markets enabled
Risk profile
Maximum risk per trade
Daily/weekly limits
Maximum simultaneous trades
Maximum exposure
News-event behaviour
Emergency stop location
```

Require deliberate confirmation.

---

# 55. AUTO-TRADING SAFETY CONTROL

Put an easily accessible master control in the account/trading dashboard:

```text
AUTO TRADING
ON / OFF
```

Turning it OFF must block new automated entries immediately.

Clearly distinguish:

```text
Stop new trades
```

from:

```text
Close existing positions
```

Never close positions merely because the user disabled new entries unless they explicitly choose that action.

---

# 56. EMERGENCY STOP

Provide an obvious emergency control.

Example:

```text
Emergency Stop
```

When activated, provide safe choices:

```text
Stop all new automatic trades

Stop automatic trades and automatic position management

Emergency close eligible auto-managed positions
```

The most destructive action must require additional confirmation.

Record all actions in the audit log.

---

# 57. SIGNAL CARD REDESIGN

Every customer-facing signal should be understandable at a glance.

Example:

```text
BTC/USDT

LONG

Signal quality
High

Market condition
Bullish momentum

Entry zone
$XX,XXX – $XX,XXX

Stop Loss
$XX,XXX

Targets
TP1
TP2
TP3

Risk/Reward
1 : X.X

Valid until
XX:XX

Your status
✓ Available on your plan
✓ Matches your preferences

Trading
Signal only / Paper / Confirm / Auto

[View Analysis]
[Trade Manually]
[Review Order]
```

Only expose appropriate actions for the customer's mode.

---

# 58. EXPLAIN SIGNALS WITHOUT DUMBING THEM DOWN

Provide a short customer explanation such as:

```text
Why SignalRank likes this setup

• Higher-timeframe trend is bullish
• Price reclaimed an important structure level
• Momentum supports continuation
• Liquidity conditions are acceptable
• No blocking high-impact event is currently active

Main risk

• Price is approaching a nearby resistance area
```

Then offer:

```text
View technical analysis
```

for advanced details.

Do not expose private strategy IP unnecessarily.

---

# 59. SIGNAL STATUS LIFECYCLE

Use understandable statuses.

Examples:

```text
New
Waiting for entry
Entry available
Executed
Partially filled
Active
TP1 reached
Stop moved
Break-even
Closed
Won
Lost
Cancelled
Expired
Skipped
Execution blocked
```

Ensure website and Telegram use the same canonical backend state.

---

# 60. TRADE EXECUTION PREVIEW

Before AUTO_CONFIRM/manual broker execution, show an order preview.

Example:

```text
Order Preview

EUR/USD
BUY

Broker
IC Markets MT5 ••••4821

Requested entry
1.17320

Current executable price
1.17327

Expected slippage
0.00007

Position size
0.40 lots

Planned risk
$74.30
0.49%

Stop Loss
1.17141

Targets
...

Estimated commission
...

Estimated spread cost
...

[Cancel]
[Execute]
```

If conditions materially change before submission, invalidate/recalculate the preview.

---

# 61. LIVE EXECUTION RECEIPT

After execution show:

```text
Trade opened
```

with:

```text
broker order ID
actual fill price
requested price
actual size
planned risk
actual estimated risk
slippage
stop
targets
timestamp
```

Do not claim success until broker confirmation exists.

Distinguish:

```text
Order submitted
```

from:

```text
Broker confirmed
```

---

# 62. PAPER VS LIVE VISUAL SEPARATION

It should be almost impossible to confuse PAPER with LIVE.

Use persistent textual badges, not colour alone.

Example:

```text
PAPER ACCOUNT
SIMULATED TRADING
```

versus:

```text
LIVE ACCOUNT
REAL MONEY
```

Never display combined performance totals.

---

# 63. CUSTOMER HOME DASHBOARD

The main dashboard should answer, within seconds:

```text
Is SignalRank working?

What opportunities do I have?

Is auto trading running?

Are my brokers connected?

How much am I risking?

What positions are active?

How have I performed?

Is anything requiring my attention?
```

Suggested layout:

```text
Account status

Active positions
Today's opportunities
Today's P/L
Risk used today

Broker health

Auto trading status

Recent signals

Recent executions

Attention required
```

Avoid filling the first screen with research-level metrics.

---

# 64. ATTENTION CENTER

Create one place for actionable issues.

Examples:

```text
Broker authentication expired

Daily loss limit reached

Auto trading paused

Payment/subscription issue

Strategy temporarily unavailable

New terms require confirmation

Broker rejected recent execution

Risk settings incomplete
```

Each item must explain:

```text
What happened
What it affects
What the user should do
```

---

# 65. NOTIFICATION PREFERENCES

Allow per-user configuration for:

```text
new signal
auto-confirm request
trade opened
partial target hit
stop moved
trade closed
execution blocked
broker disconnected
risk limit reached
auto trading paused
payment/tier issue
```

Channels may include supported:

```text
Telegram
web
email
push
```

Keep high-severity safety notifications enabled where legally/product-wise appropriate.

---

# 66. TIER UX

Do not make customers guess why something is unavailable.

When an unavailable feature is tier-gated:

```text
Auto trading is available on [eligible tier].
```

Show the actual benefit.

Do not use deceptive upgrade prompts.

Tier logic must come from the canonical entitlement backend.

Never hard-code subscription names throughout frontend components.

---

# 67. PERSONALIZATION

Allow customers to personalize:

```text
asset classes
assets
timeframes
signal frequency
strategies where customer-facing
sessions
directions
confidence preferences
notification preferences
risk profile
execution mode
broker routing
news-event behaviour
```

But clearly distinguish:

```text
Your preference
```

from:

```text
SignalRank safety rule
```

Users may make their settings stricter.

They must not be able to weaken hard platform safety controls.

---

# 68. SMART DEFAULTS

A new customer should be able to use SignalRank safely without changing 30 settings.

Create strong defaults based on:

```text
tier
broker
account type
asset class
trading mode
```

Advanced users can customize.

Do not automatically choose aggressive risk.

---

# 69. USER-SPECIFIC SIGNAL DELIVERY

Signal generation remains canonical.

Then calculate per-user:

```text
signal_eligible
```

based on:

```text
subscription
profile
asset preferences
timeframes
strategy access
risk constraints
session
cooldown
duplicates
existing exposure
delivery rules
```

Only eligible signals are sent to that customer.

---

# 70. USER-SPECIFIC EXECUTION

For each eligible signal calculate separately:

```text
execution_eligible
```

against the selected broker account.

Check:

```text
AUTO/AUTO_CONFIRM enabled
broker connected
broker healthy
instrument supported
symbol mapped
market open
margin available
risk limits
daily loss
weekly loss
drawdown
portfolio exposure
correlation
spread
slippage
latency
news rules
provider health
kill switches
signal freshness
execution price tolerance
```

Every decision must generate reason codes.

---

# 71. SIGNAL DELIVERY MUST SURVIVE EXECUTION FAILURE

Example:

```text
SignalRank finds EUR/USD LONG.

User can receive signal:
YES

Automatic execution:
NO

Reason:
Broker connection temporarily unavailable.
```

The user should still receive:

```text
EUR/USD LONG
Auto-execution could not occur because your broker is disconnected.
You may still trade this signal manually if appropriate.
```

where allowed by the product's rules.

---

# 72. NO DUPLICATE TRADES

Implement frontend/backend visibility for idempotency.

Repeated button taps, reconnects, retries, worker restarts, webhook replays or browser refreshes must not produce duplicate orders.

UI states:

```text
Submitting…
Order submitted
Broker confirmation pending
Executed
```

Disable unsafe duplicate submission while processing.

---

# 73. POSITION MANAGEMENT

Customers should be able to understand:

```text
entry
current price
stop
targets
filled quantity
remaining quantity
realized P/L
unrealized P/L
risk remaining
execution source
strategy
```

Where allowed, provide safe actions such as:

```text
Close
Partial close
Move stop
Disable automatic management
```

Respect broker and strategy rules.

Require confirmation for destructive actions.

---

# 74. MANUAL INTERVENTION

If a customer manually modifies a broker position that SignalRank is managing:

detect it.

Do not blindly overwrite customer actions.

Possible states:

```text
MANAGED
MANUALLY_MODIFIED
MANAGEMENT_PAUSED
MANUAL_TAKEOVER
```

Explain the consequence.

Example:

```text
You changed the Stop Loss directly with your broker.

SignalRank automatic management for this position has been paused.

[Resume SignalRank Management]
[Keep Manual Control]
```

---

# 75. RECONCILIATION UX

SignalRank's database must reconcile against broker truth.

If discrepancies exist show:

```text
Sync issue detected
```

Examples:

```text
SignalRank believes position is open
Broker reports it closed
```

or:

```text
Broker reports an unknown position
```

Never silently fabricate state.

---

# 76. PERFORMANCE DASHBOARD

Customers should see meaningful performance.

Separate:

```text
Signals
Paper
Live
```

Do not combine them.

Show appropriate:

```text
trades
win rate
expectancy
profit factor
net P/L
fees
drawdown
average risk
best/worst trade
```

For ordinary customers avoid overloading with research metrics.

Advanced analytics can expose more.

---

# 77. PERSONAL PERFORMANCE VS SIGNALRANK PERFORMANCE

Distinguish:

```text
SignalRank strategy performance
```

from:

```text
Your account performance
```

because users can:

- enter late;
- manually close;
- ignore signals;
- change size;
- change stops;
- alter positions.

Never attribute manual-user outcomes entirely to SignalRank.

---

# 78. MOBILE-FIRST REQUIREMENTS

Every critical trading action must work properly on mobile.

Test at minimum:

```text
320px
360px
375px
390px
414px
430px
tablet
desktop
large desktop
```

No:

- horizontal page scrolling;
- clipped controls;
- overlapping bottom bars;
- fixed headers covering content;
- tiny touch targets;
- tables extending outside the viewport;
- modal overflow;
- keyboard-covered form fields.

Use responsive card layouts where tables become unusable.

---

# 79. MOBILE TRADING CONTROLS

Important actions should remain accessible without being dangerous.

Avoid placing:

```text
Close Position
Emergency Stop
Execute
```

too close to routine actions.

Use appropriate confirmation.

Do not use swipe gestures as the only method for critical actions.

---

# 80. NAVIGATION

The information architecture should be understandable.

A possible customer navigation:

```text
Overview
Signals
Positions
Performance
Brokers
Trading Settings
Notifications
Account
```

Advanced areas:

```text
Research
Strategy Analytics
System Health
```

should be role/tier gated where appropriate.

Do not expose internal admin pages to customers.

---

# 81. TRADING SETTINGS INFORMATION ARCHITECTURE

Do not dump all settings on one page.

Organize into:

```text
Trading Mode
Risk
Markets
Strategies
Broker Routing
Execution
News & Events
Notifications
Advanced
```

Each section should have:

```text
current status
short explanation
safe default
```

---

# 82. INLINE EDUCATION

Although the interface should require no tutorial, use small explanations.

Example:

```text
Daily loss limit

SignalRank will stop opening new automatic positions after your realized and configured loss threshold is reached.
```

Avoid long walls of text.

Use:

```text
ⓘ
Learn more
```

for advanced explanation.

---

# 83. ADVANCED MODE

Provide optional:

```text
Advanced controls
```

for sophisticated users.

Expose things such as:

```text
max spread
max slippage
correlation limits
session rules
strategy filters
confidence floor
trade expiry behavior
execution tolerance
```

Do not require beginners to configure them.

---

# 84. VALIDATION & FORM UX

Every input must have:

```text
label
description where necessary
units
minimum
maximum
validation
useful error
```

Bad:

```text
Invalid value
```

Better:

```text
Risk per trade must be between 0.10% and 2.00%.
```

---

# 85. DANGEROUS SETTINGS

When a change increases risk materially, show its consequence.

Example:

```text
You're increasing risk per trade from 0.5% to 1.5%.

Maximum planned loss per stopped trade will increase approximately 3×.

[Cancel]
[Confirm Change]
```

Do not use manipulative language.

---

# 86. ACCESSIBILITY

Meet at least WCAG 2.2 AA where practical.

Ensure:

```text
keyboard navigation
visible focus
screen-reader labels
semantic controls
sufficient contrast
reduced-motion support
proper heading structure
error associations
accessible dialogs
```

Do not communicate:

```text
profit/loss
enabled/disabled
risk
warnings
```

using colour alone.

---

# 87. LIGHT AND DARK MODE

Ensure all customer and admin pages work correctly in both themes.

Audit:

```text
text
icons
cards
charts
tables
forms
dropdowns
modals
tooltips
badges
alerts
empty states
loading states
```

No black-on-black, white-on-white, or low-contrast text.

---

# 88. LOADING STATES

Do not show blank pages while financial data loads.

Use:

```text
skeleton states
specific loading messages
```

Example:

```text
Syncing broker account…
```

rather than a generic spinner everywhere.

---

# 89. EMPTY STATES

Every empty screen must explain why.

Example:

```text
No active positions

SignalRank has not opened any active trades for this account.

[View Signals]
```

or:

```text
No eligible signals right now

The engine is operating normally. Current opportunities do not meet your configured criteria.
```

Do not make customers think the product is broken simply because there is no trade.

---

# 90. ERROR UX

Separate:

```text
temporary system problem
configuration problem
broker problem
eligibility restriction
normal no-trade state
```

Example:

Bad:

```text
Something went wrong.
```

Better:

```text
We couldn't sync your broker account.

Your existing settings are safe and no new automatic trades will be placed until the connection is restored.

[Retry]
[Broker Settings]
```

---

# 91. DEGRADED SYSTEM UX

If some providers or services are unhealthy:

show what is affected.

Example:

```text
Partial service degradation

Crypto market data:
Operating normally

FX:
Temporarily unavailable

Automatic FX entries:
Paused

Existing managed positions:
Still monitored
```

Do not display a generic "SignalRank unavailable" when only one subsystem has failed.

---

# 92. SYSTEM SAFETY STATUS

Provide a simple status panel:

```text
Market data     Healthy
Signal engine   Healthy
Broker sync     Healthy
Auto trading    Active
Risk system     Healthy
```

Advanced details may be hidden.

---

# 93. TRADING ACTIVITY TIMELINE

For each trade, provide an understandable timeline:

```text
14:03 Signal generated
14:03 Signal passed validation
14:03 Eligible for your account
14:04 Order submitted
14:04 Broker confirmed fill
14:27 TP1 reached
14:27 Stop moved to break-even
15:18 Position closed
```

This builds trust and simplifies support.

---

# 94. AUDIT HISTORY FOR CUSTOMERS

Show important account changes:

```text
Auto trading enabled
Risk profile changed
Broker connected
Broker disconnected
Emergency stop activated
Trading mode changed
```

Include timestamps.

Sensitive internal audit data can remain admin-only.

---

# 95. CUSTOMER TRUST

Never make claims the evidence cannot support.

Avoid customer-facing language such as:

```text
Guaranteed
Risk-free
Certain
Always profitable
```

Performance screens must clearly distinguish:

```text
historical
backtest
paper
shadow
live
```

and provide appropriate contextual disclaimers without making the interface unusable.

---

# 96. FIRST AUTO-TRADE SAFETY FLOW

Before first real-money automatic trading:

```text
Broker connected
↓
Account verified
↓
Risk settings reviewed
↓
Auto mode selected
↓
Required disclosures/consent
↓
Execution compatibility check
↓
Small-scale/canary eligibility if platform requires
↓
AUTO ready
```

Do not enable real-money automation because a broker token merely exists.

---

# 97. DEMO / PAPER-FIRST OPTION

Strongly encourage—but do not deceptively force—new auto-trading customers to test:

```text
PAPER
```

or an actual broker demo account first.

Where appropriate provide:

```text
Try these settings with a demo account first
```

---

# 98. LIVE/PAPER SWITCHING

Switching modes must never accidentally send live orders.

Require deliberate transitions:

```text
PAPER → LIVE AUTO
```

must be explicit.

Persist environment/account identity.

Never infer live mode from UI state alone.

---

# 99. ACCOUNT-SPECIFIC RISK

Risk belongs to:

```text
user
+
broker account
```

where appropriate.

A user may have:

```text
Main account:
Conservative

Demo account:
Custom

Crypto account:
Balanced
```

Do not share unsafe values across accounts accidentally.

---

# 100. EXECUTION PRICE PROTECTION

Allow platform-level protection against chasing trades.

Example:

```text
Signal entry:
$100

Current:
$103

Maximum permitted deviation:
1%

Execution:
BLOCKED
```

Customer explanation:

```text
Price moved too far from the validated entry.
The signal remains visible, but SignalRank will not chase the trade automatically.
```

---

# 101. SIGNAL EXPIRY

Clearly show:

```text
Valid for 12 minutes
```

or exact expiration.

Expired signals cannot auto-execute.

If the user opens an old page, the UI must obtain current canonical status before showing an Execute button.

---

# 102. REAL-TIME STATE

Where practical, use real-time updates for:

```text
broker connection
order status
fills
positions
prices
signal state
kill switches
```

Fallback safely if real-time transport fails.

Never allow stale UI to imply trading is active when backend safety has disabled it.

---

# 103. CONFLICT RESOLUTION

If multiple signals compete for limited risk budget, the customer should see:

```text
Signal valid but skipped because a higher-ranked opportunity used your available risk budget.
```

Do not make it appear as an engine failure.

---

# 104. PORTFOLIO EXPOSURE UX

Translate correlation into understandable language.

Example:

```text
Portfolio concentration

High crypto exposure

BTC, ETH and SOL positions are strongly correlated.

SignalRank blocked another crypto LONG to prevent excessive concentration.
```

Advanced users can inspect correlations.

---

# 105. NEWS/EVENT UX

If execution is affected by a high-impact event:

```text
Automatic entry paused

US CPI is scheduled in 18 minutes.

Your profile blocks new entries around high-impact events.
```

Provide:

```text
View event
View setting
```

where supported.

---

# 106. STRATEGY HEALTH CUSTOMER UX

Do not expose unnecessarily technical research internals.

If a strategy is quarantined:

```text
Strategy temporarily unavailable

SignalRank detected performance or market-condition deterioration and paused this strategy while it is re-evaluated.
```

Do not pretend it is simply a technical outage.

---

# 107. OWNER/ADMIN CONTROL CENTER

Admin/owner users should have deeper visibility than customers.

Include:

```text
strategy health
research experiments
WFO
multiple-testing results
backtest audits
quarantines
provider health
execution failures
broker failures
kill switches
global exposure
user execution states
```

Allow filtering by:

```text
asset
strategy
timeframe
broker
user
tier
environment
health state
```

All sensitive administrative mutations must be audited.

---

# 108. OWNER GLOBAL EXECUTION CONTROLS

Provide audited controls for:

```text
disable all new auto execution
disable broker
disable asset
disable asset class
disable strategy
disable timeframe
disable account/user execution
```

Do not confuse:

```text
disable signal generation
```

with:

```text
disable execution
```

unless explicitly selected.

---

# 109. TIER-BASED FEATURE MATRIX

Create a canonical backend-driven entitlement matrix.

The frontend should render features from it.

Examples include eligibility for:

```text
signal volume
asset classes
timeframes
advanced analysis
broker connections
number of broker accounts
paper trading
AUTO_CONFIRM
AUTO
advanced risk controls
portfolio analytics
research analytics
```

Do not duplicate tier logic in multiple components.

---

# 110. FEATURE DISCOVERY WITHOUT CLUTTER

Customers should be able to discover features naturally.

Use:

```text
small contextual banners
empty-state actions
relevant settings links
```

rather than intrusive modal advertising.

---

# 111. SEARCH/FILTERING

For signals/trades/history support sensible filters:

```text
asset
asset class
strategy
direction
status
broker
account
timeframe
date
execution mode
```

On mobile use responsive filter sheets rather than overflowing controls.

---

# 112. CUSTOMER SUPPORT CONTEXT

Generate useful support/debug IDs for failed actions.

Example:

```text
We couldn't complete this broker action.

Reference:
SR-EXEC-8A7F…
```

Owner/admin diagnostics should be able to find the corresponding event.

Do not expose stack traces.

---

# 113. CONSISTENT DESIGN SYSTEM

Audit the entire frontend.

Unify:

```text
spacing
margins
padding
typography
buttons
inputs
cards
badges
tables
modals
drawers
navigation
icons
alerts
charts
loading states
empty states
```

Build reusable primitives rather than page-specific hacks.

Ensure consistency across all SignalRank routes.

---

# 114. DESIGN QUALITY

The desired experience is:

```text
premium
professional
financial
modern
calm
trustworthy
clear
```

Avoid:

```text
casino styling
excessive neon
flashing profit animations
gamified risk
fake urgency
confetti for trades
```

SignalRank should feel like a serious trading-intelligence platform.

---

# 115. CHARTS

Charts must work on all screen sizes.

Provide useful:

```text
equity
drawdown
P/L
exposure
performance
```

visualizations.

Never distort chart scales in ways that exaggerate performance.

Use proper labels and tooltips.

---

# 116. CUSTOMER JOURNEY TESTING

Test complete journeys, not only components.

At minimum:

### Manual signal customer

```text
register
→ choose plan
→ configure preferences
→ receive signal
→ inspect signal
→ record/manual interaction
```

### Paper customer

```text
configure paper
→ receive signal
→ simulated execution
→ position management
→ close
→ analytics
```

### Auto-confirm customer

```text
connect broker
→ choose AUTO_CONFIRM
→ receive opportunity
→ preview order
→ confirm
→ broker execution
→ lifecycle
```

### Auto customer

```text
connect broker
→ configure risk
→ explicitly enable AUTO
→ valid signal
→ eligibility
→ execution
→ broker confirmation
→ management
→ closure
```

### Blocked execution

```text
valid signal
→ risk/broker rejection
→ signal still available
→ understandable reason
```

### Broker failure

```text
broker disconnects
→ new auto trades paused
→ user informed
→ manual signals continue where permitted
→ reconnect
```

### Kill switch

```text
emergency stop
→ new entries stop
→ existing positions behave according to selected action
```

---

# 117. CROSS-DEVICE TESTING

Test manually and automatically on:

```text
Chrome
Safari
Firefox
Edge
Android Chrome
iOS Safari
```

where available.

Test actual touch interaction where possible.

Do not rely only on desktop responsive emulation.

---

# 118. REFRESH AND SESSION STATE

Fix any behaviour where:

```text
refresh
```

temporarily shows login or the wrong page before authentication resolves.

Use correct authenticated loading states.

Preserve intended destination after authentication when safe.

---

# 119. REAL-TIME AUTHORIZATION

Frontend hiding is not authorization.

Every action must be enforced server-side.

If a user's:

```text
tier
role
broker
AUTO permission
```

changes while their browser is open, backend authorization remains authoritative.

---

# 120. CUSTOMER CONSENT AND REGULATORY READINESS

Build clean product primitives for:

```text
risk acknowledgement
auto-trading consent
broker authorization
terms versions
privacy versions
material setting changes
```

Store versions/timestamps.

Do not create legal claims or assume regulatory compliance from implementation alone.

Keep jurisdiction-specific legal language configurable and reviewable.

---

# 121. ONE-CLICK CLARITY

At any moment an ordinary customer should be able to answer:

```text
Am I trading live?

Is automatic trading enabled?

Which account will SignalRank trade?

How much can SignalRank risk?

What markets can it trade?

What positions does it currently manage?

Why was this signal not executed?

How do I stop new trades?
```

If any of those answers require reading documentation, improve the interface.

---

# 122. ADDITIONAL HIGH-VALUE IMPROVEMENTS

While implementing the above, investigate and add sensible improvements including:

### Safe Mode

A one-click configuration:

```text
Signals + alerts only
No broker execution
```

### Vacation/Pause Mode

Allow:

```text
Pause automatic new entries until:
date/time
manual resume
```

Existing position management must follow explicit user selection.

### Risk Budget Meter

Show:

```text
Today's risk budget
Used: X%
Available: Y%
```

### Broker Health Score

Condense:

```text
authentication
latency
recent failures
sync freshness
```

into an understandable health state.

### Execution Quality

Show users:

```text
average slippage
fill quality
broker rejection rate
```

where enough evidence exists.

### Pre-Trade Portfolio Preview

Before AUTO_CONFIRM:

```text
Current crypto exposure: 34%
After trade: 48%
```

### Strategy Diversification

Show a simple:

```text
Your automated portfolio is currently concentrated in momentum strategies.
```

when materially relevant.

### Smart Notification Grouping

Avoid sending ten nearly identical alerts during volatile periods.

### Quiet Hours

Allow notification quiet hours without silently disabling required safety alerts.

### In-App Activity Inbox

Provide a persistent history of important actions/alerts.

### Session Security

Provide:

```text
active sessions
recent logins
revoke sessions
```

where supported.

### Broker Credential Security

Never return raw broker secrets after initial submission.

Provide:

```text
Replace credentials
Reconnect
Disconnect
```

instead.

### Account Alias

Allow customers to name accounts:

```text
Main FX
Crypto
Prop Demo
```

instead of displaying broker IDs everywhere.

### Dry-Run Preview

Before enabling AUTO, allow:

```text
Show me what SignalRank would have traded under these settings.
```

using appropriate paper/shadow evidence without pretending it is future performance.

### Configuration Impact Summary

Whenever a major setting changes, show:

```text
What changes now?
```

Example:

```text
You disabled crypto.

3 active crypto signals will no longer be eligible for new execution.
Existing positions are unaffected.
```

### Policy Simulator

For advanced users/admins, allow a risk profile to be tested against historical/paper signals:

```text
Under these settings:
47 opportunities eligible
13 blocked by correlation
8 blocked by risk
...
```

without presenting this as guaranteed performance.

---

# 123. FINAL FRONTEND AUDIT

Before completion inspect every customer-facing and admin route at:

```text
mobile
tablet
desktop
```

Audit:

```text
navigation
layout
spacing
padding
margins
text contrast
typography
forms
buttons
modals
drawers
tables
charts
overflow
loading
empty
error
disabled
success
warning
light mode
dark mode
```

Do not only inspect the newly-created pages.

Fix existing frontend inconsistencies encountered during the audit when safe.

---

# 124. NO-TUTORIAL TEST

Perform this final exercise:

Assume the customer has never seen SignalRank before.

Can they successfully:

```text
create account
understand their plan
choose their markets
receive signals
connect a broker
understand that broker connection ≠ auto trading
choose PAPER/AUTO_CONFIRM/AUTO
configure safe risk
understand which account will be traded
turn automation on
understand a blocked execution
view an active position
stop new automatic trades
review performance
```

without external instructions?

If not, continue improving the UX.

---

# 125. COMPLETION EVIDENCE

For each frontend/customer requirement report:

```text
IMPLEMENTED
VERIFIED
BLOCKED_EXTERNAL
DEFERRED
NOT_APPLICABLE
```

Verification must include relevant:

```text
route/component
API/backend integration
responsive test
role/tier test
live state test
error state
```

Do not mark a page complete merely because it renders.

The feature must be connected to the real backend and behave correctly.

---

# FINAL PRODUCT PRINCIPLE

SignalRankAI should not feel like a bot where users blindly switch something on.

It should feel like a controlled trading platform where the customer always understands:

```text
what SignalRank found,
why they received it,
whether SignalRank can trade it,
which account would be used,
how much risk is involved,
what happened after submission,
and how to stop or change the behaviour.
```

The backend should be quantitatively rigorous.

The frontend should make that rigor understandable.

The customer experience should be simple without hiding important risk.

Powerful features should become progressively available as the user asks for more control, rather than overwhelming them on day one.