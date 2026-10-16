# SIGNALRANKAI — REPOSITORY GAP CLOSURE, MULTI-BROKER ROUTING & TRUTHFUL COMPLETION DIRECTIVE

This directive is additive to every previous SignalRank specification and prompt.

Its purpose is to close repository-level gaps discovered after reviewing the actual current codebase, particularly where:

- documentation says something is implemented but the actual product is incomplete;
- multiple generations of architecture coexist;
- old fallback behavior conflicts with the new multi-account safety model;
- backend capability exists without a complete customer-facing workflow;
- UI exists without the corresponding canonical backend behavior;
- multiple brokers/accounts create ambiguous routing;
- implementation-status documents are more optimistic than the actual runtime.

Do not simply implement the explicitly listed findings below.

Use them as evidence that a **fresh repository-wide verification audit is required**.

---

# 1. DO NOT TRUST EXISTING “IMPLEMENTED” OR “VERIFIED” LABELS BLINDLY

Existing repository documents contain implementation/evidence ledgers.

These are useful historical records, but they are NOT authoritative proof that the current default branch actually provides complete working functionality.

For every requirement marked:

```text
IMPLEMENTED
VERIFIED
UNIT_VERIFIED
INTEGRATION_VERIFIED
COMPLETE
```

re-check the actual current code.

Verification must inspect:

```text
runtime path
backend implementation
database/schema
frontend
mobile
Telegram
authorization
configuration
tests
deployment wiring
```

where relevant.

If documentation is incorrect, update the status truthfully.

Do not preserve a false green status simply because an older document says the feature is complete.

---

# 2. KNOWN FALSE-POSITIVE FRONTEND COMPLETION

The repository evidence ledger currently describes the replacement Next.js frontend as implemented/verified.

However, the actual current:

```text
frontend/src/app/page.tsx
```

is still essentially the default create-next-app starter page.

Treat this as an important evidence-integrity failure.

The existence of:

```text
Next.js
Tailwind
generated OpenAPI types
package.json
```

does NOT mean the replacement frontend is implemented.

Complete the full frontend according to the previously supplied SignalRank Web + Mobile Product Design Specification.

Then update the evidence ledger to reflect actual verified completion.

---

# 3. MULTIPLE FRONTEND GENERATIONS

The repository currently contains several frontend generations/surfaces, including:

```text
web/platform_app
web/userdash
frontend/
mobile/
```

Audit which surface is actually serving production and staging.

Establish explicit ownership:

```text
canonical public website
canonical authenticated web application
canonical admin/owner application
canonical native mobile application
legacy compatibility surfaces
```

Do not allow multiple customer UIs to independently implement different business logic.

The final target should normally be:

```text
Next.js web application
+
FastAPI canonical API
+
Expo/React Native mobile application
+
Telegram client
```

unless repository constraints prove another architecture safer.

Do NOT delete working legacy functionality until parity has been demonstrated.

Migration should follow:

```text
inventory
→ implement canonical replacement
→ verify parity
→ switch traffic
→ observe
→ deprecate legacy surface
→ remove only when safe
```

---

# 4. BROKER ROUTING IS CURRENTLY TOO SIMPLE

The current provider-neutral routing logic effectively makes a simple provider decision such as:

```text
crypto/USDT + Bybit connected
→ Bybit

otherwise
→ MT5
```

This is insufficient for a serious multi-broker platform.

Replace or extend it with a canonical **Broker Routing Engine**.

Do not scatter routing decisions across:

```text
Telegram
frontend
MT5 router
Bybit router
trading mode manager
```

All execution destinations must pass through one canonical routing policy.

---

# 5. CANONICAL BROKER ROUTING MODES

Implement explicit per-user/per-account-group routing modes.

At minimum:

```text
SINGLE_BEST_ACCOUNT
PRIORITY_FALLBACK
MIRROR_SELECTED_ACCOUNTS
```

For mirrored execution also support explicit risk modes:

```text
SPLIT_TOTAL_RISK
PER_ACCOUNT_RISK
```

Default:

```text
SINGLE_BEST_ACCOUNT
```

Connecting several brokers must NEVER imply that SignalRank automatically trades every broker.

---

# 6. SINGLE_BEST_ACCOUNT

For one valid signal available on multiple connected accounts:

evaluate all eligible destinations.

Select exactly one.

Example:

```text
BTC LONG

Available:
Bybit Crypto
Broker A MT5
Broker B MT5

SignalRank routing result:

Bybit Crypto
```

Persist why it was chosen.

The other accounts receive no order.

---

# 7. PRIORITY_FALLBACK

Allow users to define routing priorities.

Example:

```text
Crypto
1. Bybit
2. Binance
3. MT5 Crypto

FX
1. IC Markets
2. Pepperstone
3. OANDA
```

The system should attempt the next route only when the previous destination becomes **ineligible before order submission**.

Do not send to Broker B merely because Broker A's order acknowledgement is temporarily uncertain.

If submission state is uncertain:

```text
UNKNOWN / RECONCILING
```

must block fallback until the first destination is reconciled.

Otherwise duplicate exposure can occur.

---

# 8. MIRROR_SELECTED_ACCOUNTS

Allow deliberate execution across multiple selected accounts.

This feature must be OFF by default.

Example:

```text
BTC LONG

Mirror to:
✓ Bybit Main
✓ MT5 Personal
✕ Prop Account
```

Require explicit user consent.

Mirroring must remain subject to every per-account and portfolio-level safety gate.

---

# 9. MIRRORED RISK MODES

## SPLIT_TOTAL_RISK

Example:

```text
Total desired risk:
1.00%

Bybit:
0.40%

MT5 Personal:
0.35%

Broker C:
0.25%
```

The sum across destinations must remain within the requested total.

Risk can be allocated by configurable logic such as:

```text
equal
equity weighted
available-risk weighted
execution-quality weighted
custom percentages
```

Validate totals.

---

## PER_ACCOUNT_RISK

Example:

```text
Each account:
1.00%
```

Three accounts therefore create approximately three account-level risk allocations.

This is substantially more aggressive.

Require an explicit warning and confirmation.

Do not confuse it with SPLIT_TOTAL_RISK.

---

# 10. ASSET-CLASS ROUTING

Allow default routing by asset class.

Example:

```text
Crypto      → Bybit
FX          → IC Markets
Indices     → FTMO Demo/Prop profile where eligible
Equities    → Broker X
Commodities → Pepperstone
```

---

# 11. ASSET-SPECIFIC ROUTING OVERRIDES

Allow individual instruments to override the class rule.

Example:

```text
XAUUSD
→ Broker A

NAS100
→ Broker B

BTCUSDT
→ Bybit
```

Validate broker symbol mapping before allowing a routing override.

---

# 12. ROUTING POLICY MODEL

Create a versioned routing-policy representation.

Conceptually:

```text
routing_policy_id
user_id
policy_version

default_mode

asset_class_routes
asset_routes

allowed_connection_ids
blocked_connection_ids

priority_order

fallback_enabled

mirror_connection_ids

mirror_risk_mode

allocation_policy

maximum_destinations

execution_quality_weight
spread_weight
fee_weight
slippage_weight
latency_weight

created_at
updated_at
```

Follow existing repository conventions.

---

# 13. BROKER ROUTING ELIGIBILITY

A connected broker account is NOT automatically a valid execution destination.

Before selection evaluate:

```text
user ownership
account enabled
account classification
account execution permission
policy certification
reconciliation health
broker authentication
instrument availability
symbol mapping
market open
order capability
free margin
balance/equity
risk budget
daily loss
weekly loss
drawdown
position count
asset exposure
portfolio exposure
prop rules
spread
slippage
quote freshness
latency
provider health
execution kill switch
```

Ineligible accounts must be excluded before scoring.

---

# 14. EXECUTION-QUALITY ROUTING

When multiple accounts remain eligible, routing may consider:

```text
spread
commission
expected slippage
latency
fill quality
broker rejection history
quote freshness
liquidity
free margin
historical execution quality
```

Do not optimize solely for the cheapest spread.

Safety and account-policy eligibility come before cost optimization.

---

# 15. ROUTING EXPLAINABILITY

Every routing decision must answer:

```text
Why this broker?
Why not the other brokers?
Was fallback used?
Was mirroring used?
What risk was assigned to each account?
```

Persist structured reason codes.

Example:

```text
ROUTE_SELECTED_BYBIT

Reasons:
instrument_supported
preferred_crypto_account
spread_better
healthy_reconciliation
risk_available

Skipped MT5-2:
insufficient_margin

Skipped PROP-1:
news_restriction_active
```

---

# 16. CUSTOMER ROUTING UI

Implement a clear Broker Routing section.

Path may be:

```text
Automation
→ Broker Routing
```

or another design-consistent location.

Show:

```text
Routing mode
Default broker by market
Fallback order
Asset overrides
Mirroring
Risk allocation
```

Use understandable language.

Example:

```text
When the same trade is available on more than one account:

○ Use the best eligible account
○ Follow my broker priority
○ Trade selected accounts
```

Do not expose database terminology.

---

# 17. ROUTING PREVIEW

Before saving routing settings show examples.

Example:

```text
BTC/USDT
Bybit → preferred

EUR/USD
IC Markets → preferred
Pepperstone → fallback

NAS100
Prop Account → only eligible destination
```

---

# 18. SIGNAL DETAIL ROUTING VISIBILITY

For AUTO/AUTO_CONFIRM customers show:

```text
Execution destination

Bybit — Crypto Main
```

or:

```text
Routing

IC Markets
Fallback: Pepperstone
```

For mirrored trade:

```text
3 accounts selected
Total portfolio risk: 1.0%
```

---

# 19. AUTO_CONFIRM + ROUTING

AUTO_CONFIRM must run routing before order confirmation.

The preview should show:

```text
Selected account(s)
Risk per account
Total combined risk
Expected cost
Portfolio effect
```

If conditions materially change before confirmation:

re-route/revalidate.

Never execute against stale routing results.

---

# 20. CANONICAL CROSS-BROKER RISK

The repository currently has strong per-account risk primitives, but the scan did not find a complete canonical **cross-broker aggregate exposure implementation**.

Implement it.

SignalRank must understand:

```text
BTC LONG on Bybit
BTC LONG on MT5
BTC LONG on another exchange
```

as one combined underlying exposure.

---

# 21. CROSS-BROKER RISK AUTHORITY

Before creating multiple execution intents calculate:

```text
total user exposure
asset exposure
asset-class exposure
currency exposure
factor exposure where available
correlated exposure
daily risk
weekly risk
total drawdown budget
```

across all included accounts.

Account-level limits still apply independently.

---

# 22. ATOMIC PORTFOLIO RISK RESERVATION

Multiple simultaneous signals must not each believe the same portfolio risk budget is available.

Before submitting:

```text
signal
↓
routing
↓
combined risk calculation
↓
atomic portfolio risk reservation
↓
per-account reservation
↓
order intent(s)
↓
submission
```

Release/adjust reservations as broker outcomes become known.

---

# 23. MULTI-CURRENCY ACCOUNT AGGREGATION

If accounts use:

```text
USD
EUR
GBP
NGN
USDT
```

do not sum balances directly.

Convert through timestamped, provenance-backed FX/conversion rates.

Store:

```text
source currency
target currency
conversion rate
source
timestamp
```

Allow the user to choose a portfolio reporting currency.

---

# 24. ACCOUNT BALANCE / EQUITY AWARENESS

Audit every broker adapter.

For each execution destination verify SignalRank uses fresh broker truth for:

```text
balance
equity
used margin
free margin
currency
leverage
open positions
pending orders
unrealized P/L
```

Position sizing must use the correct account state.

Do not rely on old cached balance when live execution is being considered.

---

# 25. MANUAL SIGNAL USERS

Users without a connected broker may optionally set:

```text
Manual account size
```

for position-sizing estimates.

This value must be clearly labelled:

```text
Self-reported
```

and must NEVER be confused with broker-verified equity.

---

# 26. LEGACY “FIRST ACTIVE ACCOUNT” FALLBACK

The current:

```text
db/mt5_models.py
```

contains logic that falls back from a missing default account to:

```text
first active account
```

This conflicts with the newer explicit multi-account execution model.

Audit whether this module is still used.

Repository search currently suggests much of this module may be legacy/dead.

If dead:

```text
deprecate/remove it safely
```

after proving no production references.

If active:

replace ambiguous fallback behavior with canonical connection resolution.

Never silently execute on “the first account.”

---

# 27. LEGACY UNSCOPED ACCOUNT LOOKUP

Audit helpers such as:

```text
get_account_by_id(account_id)
```

that do not obviously require canonical:

```text
user_id + connection_id
```

ownership.

Even if currently unused, remove/deprecate unsafe patterns so future code cannot accidentally reintroduce BOLA/IDOR or wrong-account execution.

Every broker-account lookup for user operations must be owner scoped.

---

# 28. LEGACY MT5 ACCOUNT MODEL CONSOLIDATION

The repository has newer canonical:

```text
broker connections
account policies
reconciliation
account ledger
connection_id
```

alongside older:

```text
MT5Account
MT5ExecutionLog
MT5Position
```

models/helpers.

Audit overlap.

Do not maintain two competing account identity systems indefinitely.

Establish canonical models.

Migrate necessary data.

Deprecate/remove obsolete models only after compatibility and evidence requirements are satisfied.

---

# 29. EXECUTION MODE FRAGMENTATION

Current code uses overlapping values including:

```text
signals_only
none
manual
manual_confirmed
semi_auto
auto
live
copy
copy_trade

paper
live
both
```

This is too ambiguous.

Create one canonical model.

Customer-facing modes:

```text
SIGNALS_ONLY
PAPER
AUTO_CONFIRM
AUTO
```

Copy/mirroring behavior should be represented separately from the main trading mode unless there is a strong architectural reason otherwise.

Example:

```text
trading_mode=AUTO
routing_mode=MIRROR_SELECTED_ACCOUNTS
```

is clearer than overloading:

```text
copy_trade
```

to mean several things.

---

# 30. LEGACY MODE COMPATIBILITY

Support old stored values through a migration/compatibility layer.

Map deliberately.

Example:

```text
none          → SIGNALS_ONLY
signals_only  → SIGNALS_ONLY
semi_auto     → AUTO_CONFIRM
manual_confirmed → AUTO_CONFIRM
auto          → AUTO
```

Do not silently map plain `manual` unless its exact historical meaning is verified.

Migration must preserve user intent.

---

# 31. TRADING MODE MANAGER AUDIT

Repository search suggests:

```text
services/trading_mode_manager.py
```

is largely unused outside tests.

Audit it.

Do not leave a dead parallel execution architecture.

Either:

```text
integrate it as the canonical policy layer
```

or:

```text
deprecate/remove it
```

in favor of the current canonical execution service.

There must be one authoritative execution path.

---

# 32. PROVIDER ROUTER CONSOLIDATION

The canonical provider router should receive:

```text
user
signal
routing policy
account policies
portfolio state
```

and produce:

```text
ExecutionPlan
```

instead of simply returning one provider name.

Conceptual:

```text
ExecutionPlan
    destinations[]
        connection_id
        provider
        symbol
        requested_risk
        requested_quantity
        reason
    combined_risk
    routing_mode
    policy_version
```

---

# 33. ORDER INTENTS PER DESTINATION

One signal may produce:

```text
0
1
or multiple
```

order intents.

Each intent needs:

```text
signal_id
user_id
connection_id
routing_plan_id
idempotency_key
risk reservation
account policy version
routing policy version
```

---

# 34. CROSS-BROKER IDEMPOTENCY

Default single-account routing must guarantee:

```text
one signal
→ no more than one intended execution destination
```

unless mirror mode is explicitly active.

For mirror mode:

```text
one signal + one connection
→ maximum one execution effect
```

Retries must never duplicate a mirrored destination.

---

# 35. FALLBACK IDEMPOTENCY

If Broker A times out after submission:

do not immediately route to Broker B.

First reconcile Broker A.

Only fallback when the system can prove:

```text
no order / no fill / no exposure
```

at Broker A.

---

# 36. MANUAL BROKER INTERVENTION

The scan did not identify a complete implementation of customer manual-modification handling.

Implement reconciliation that detects when a user manually changes a SignalRank-managed position through the broker.

Detect at least where supported:

```text
manual stop change
manual take-profit change
partial close
full close
size change
manual opposite trade
```

Possible states:

```text
MANAGED
MANUALLY_MODIFIED
MANUAL_TAKEOVER
MANAGEMENT_PAUSED
```

Do not repeatedly overwrite deliberate user actions.

---

# 37. MANUAL INTERVENTION UX

Example:

```text
Position modified at broker

You changed the Stop Loss outside SignalRank.

Automatic management is paused for this position.

[Resume SignalRank Management]
[Keep Manual Control]
```

---

# 38. SUBSCRIPTION / BILLING SAFETY

The specifications describe safe downgrade behavior, but verify actual implementation.

A:

```text
PAST_DUE
SUSPENDED
DOWNGRADED
CANCELLED
```

subscription must not cause managed open positions to be abandoned.

Separate:

```text
permission to create new exposure
```

from:

```text
permission/responsibility to safely manage existing exposure
```

Implement missing behavior and tests.

---

# 39. BROKER DISCONNECT SAFETY

Before account disconnection:

detect:

```text
open positions
pending orders
active management
```

Tell the user exactly what will happen.

Do not silently stop managing live risk.

Persist a final broker snapshot.

---

# 40. PRICE REVALIDATION BEFORE EXECUTION

Existing code contains price-drift/slippage protections, but ensure there is a canonical final revalidation between:

```text
signal generation
and
actual submission
```

Re-check:

```text
current quote
signal entry range
maximum deviation
spread
slippage estimate
stop geometry
reward/risk
regime if required
signal expiry
```

If the trade is no longer valid:

```text
signal remains visible where appropriate
execution blocked
```

Reason:

```text
PRICE_MOVED_OUTSIDE_VALIDATED_ENTRY
```

---

# 41. ACCOUNT-SPECIFIC ASSET AVAILABILITY

Do not merely ask:

```text
does provider support BTC?
```

Ask:

```text
does THIS connected account support THIS instrument right now?
```

Account-specific availability can differ because of:

```text
broker
server
region
account type
prop rules
instrument permissions
market session
```

---

# 42. SYMBOL MAPPING PER ACCOUNT

Use:

```text
canonical asset
→ provider
→ broker account/server
→ executable symbol
```

Never assume that two MT5 accounts use identical symbols.

Example:

```text
XAUUSD
GOLD
XAUUSD.a
XAUUSDm
```

must resolve explicitly.

---

# 43. FRONTEND EXECUTION-MODE UX

The current legacy web form uses older concepts such as:

```text
Paper only
Paper + broker
Broker only

signals_only
manual
auto
copy_trade
```

Replace the customer experience with the canonical:

```text
Signals Only
Paper
Confirm Each Trade
Automatic
```

Advanced routing lives separately.

Backend aliases may remain temporarily for migration only.

---

# 44. NEXT.JS FRONTEND MUST BECOME REAL

The current Next.js frontend must be completed.

Implement all required authenticated routes from the previous full design specification.

Do not leave:

```text
Next.js logo
“edit page.tsx”
Vercel starter links
```

in any production-facing code.

Create the full:

```text
Overview
Signals
Signal Detail
Positions
Orders
Performance
Portfolio
Automation
Broker Accounts
Broker Routing
Risk
Activity
Notifications
Billing
Settings
Owner/Admin
Research
Strategy Health
```

experience as applicable.

---

# 45. LEGACY WEB MIGRATION

The current `web/platform_app` contains significant working functionality.

Do not discard it blindly.

Create a route/capability parity inventory:

```text
legacy feature
canonical API
new Next.js route
verification
```

Only retire the legacy customer interface after all required functionality is reproduced and verified.

---

# 46. MOBILE APP GAP

A native Expo application exists.

Current implementation is comparatively simple and primarily includes:

```text
overview
signals
markets
paper
portfolio
performance
journal
support
account/auth
```

Complete it according to the full mobile design.

Add required native flows for:

```text
Positions
Orders
Automation
Trading Modes
Broker Accounts
Broker Routing
Risk
AUTO_CONFIRM
Execution Receipt
Activity
Notifications
Emergency Stop
Security
```

as permitted by tier/account state.

---

# 47. MOBILE ARCHITECTURE

The current application is heavily concentrated in:

```text
mobile/App.tsx
```

Refactor into maintainable:

```text
screens
navigation
components
hooks
services
state
design tokens
```

without gratuitous rewrites.

Use production navigation rather than a horizontal list of every screen as the final product navigation.

---

# 48. MOBILE PRIMARY NAV

Implement the previously specified native navigation:

```text
Overview
Signals
Positions
Performance
More
```

with advanced destinations under `More`.

---

# 49. STRATEGY HEALTH CUSTOMER UX

The repository contains strategy/adaptive quarantine concepts, but the scan found little complete customer-facing strategy-health UX.

When a strategy becomes unavailable:

show:

```text
Strategy temporarily paused

SignalRank detected deterioration or incompatible market conditions.

No new trades will use this strategy while it is being re-evaluated.
```

Do not expose unnecessary proprietary detail.

Admin/owner gets full evidence.

---

# 50. OWNER STAGING QA CONTROL SURFACE

The repository does not appear to contain the complete previously requested:

```text
/owner/qa
```

staging-only scenario-control UI.

Implement it.

Allow safe deterministic simulation of:

```text
valid signal
rejected signal
expired signal
broker timeout
broker rejection
partial fill
unknown broker state
manual intervention
daily risk block
portfolio risk block
provider failure
strategy quarantine
duplicate callback
notification failure
```

Production must reject/omit these controls.

---

# 51. ROUTING TEST MATRIX

Add deterministic tests.

At minimum:

```text
same asset available on 3 brokers
→ SINGLE_BEST_ACCOUNT selects exactly one

preferred broker eligible
→ first priority selected

preferred broker ineligible before submission
→ fallback selected

first broker submission uncertain
→ NO fallback until reconciliation

mirror 3 accounts
→ exactly 3 distinct intents

SPLIT_TOTAL_RISK
→ destination risk sum <= requested total

PER_ACCOUNT_RISK
→ independent account risk applied

one mirror destination fails
→ no duplicate orders on successful accounts

retry
→ no duplicate execution

broker disconnect
→ destination ineligible

insufficient margin
→ destination ineligible

prop restriction
→ destination ineligible

different currencies
→ aggregate risk converted correctly

same BTC exposure on multiple venues
→ combined portfolio exposure enforced

concurrent signals
→ atomic risk reservation prevents oversubscription
```

---

# 52. ROUTING PROPERTY TESTS

Where suitable, add property/invariant tests:

```text
default routing never creates >1 destination

mirror routing never includes unselected accounts

blocked account never receives intent

every execution destination belongs to the user

every intent references one valid connection_id

total split risk never exceeds allowed total

retry does not increase destination count
```

---

# 53. EXECUTION MODE TESTS

Verify every canonical mode:

```text
SIGNALS_ONLY
→ delivery, no order

PAPER
→ simulated execution only

AUTO_CONFIRM
→ no broker order before explicit confirmation

AUTO
→ broker order only after all gates
```

---

# 54. CROSS-SURFACE PARITY

For:

```text
Web
Mobile
Telegram
```

the same user/account must see consistent:

```text
mode
routing policy
selected account
signal status
execution eligibility
broker state
risk settings
```

Presentation may differ.

Truth may not.

---

# 55. ROUTING AUDIT EVENTS

Persist events for:

```text
routing policy created
routing policy changed
account priority changed
mirror enabled
mirror disabled
risk-allocation mode changed
route selected
fallback used
routing blocked
```

---

# 56. HIGH-RISK ROUTING CHANGES

Treat these as high-risk settings:

```text
enable mirroring
switch to PER_ACCOUNT_RISK
add a live/prop destination
increase account risk
```

Require:

```text
recent authentication where appropriate
explicit confirmation
audit reason/evidence
```

---

# 57. PROP ACCOUNT ROUTING

PROP accounts must never become generic fallback destinations simply because another broker failed.

They require:

```text
explicit inclusion
certified prop policy
instrument eligibility
news rules
drawdown rules
account reconciliation
```

---

# 58. DEMO VS LIVE ROUTING

Demo accounts and live accounts must remain distinguishable.

A routing policy must not accidentally substitute:

```text
DEMO
```

for:

```text
LIVE_PERSONAL
```

or vice versa.

---

# 59. ACCOUNT GROUPS

Allow users to create optional logical account groups.

Example:

```text
Personal
Prop
Crypto
Testing
```

Routing policies may target a group.

Do not make grouping required for simple users.

---

# 60. BEST ACCOUNT DOES NOT MEAN HIGHEST BALANCE

Destination scoring must not simply choose the largest account.

Risk, execution quality, policy and portfolio state come first.

---

# 61. NO SILENT ROUTING

Whenever SignalRank changes destination because of fallback:

record it and surface it where appropriate.

AUTO_CONFIRM must show the updated destination before execution.

AUTO users should see it in the trade timeline/activity.

---

# 62. ACCOUNT ROUTING TIMELINE

Example:

```text
14:03 Signal validated
14:03 Bybit preferred
14:03 Bybit blocked — insufficient available margin
14:03 MT5 Main selected
14:04 Order submitted
14:04 Broker acknowledged
```

---

# 63. EVIDENCE LEDGER CORRECTION

During this work audit:

```text
EVIDENCE_LEDGER*
COMPLETION*
IMPLEMENTATION_MATRIX*
REQUIREMENTS_TRACEABILITY_MATRIX*
```

If a record claims complete functionality contradicted by current code:

correct it.

Do not rewrite history.

Record:

```text
previous claim
current audit result
correction
evidence
```

---

# 64. SEARCH FOR OTHER DOCUMENTATION/CODE DIVERGENCE

Perform repository-wide checks for claims such as:

```text
implemented
verified
complete
production ready
```

and compare them to actual runtime implementation.

Prioritize:

```text
frontend
mobile
broker execution
research
payments
notifications
security
admin operations
```

---

# 65. SEARCH FOR PARALLEL/LEGACY IMPLEMENTATIONS

Audit duplicate generations of:

```text
authentication
broker connections
execution routing
account models
risk models
frontend
Telegram commands
payments
notification delivery
```

For each classify:

```text
CANONICAL
LEGACY_COMPAT
DEPRECATED
DEAD
```

Do not leave ambiguous competing implementations.

---

# 66. REPOSITORY-WIDE INCOMPLETE CODE SCAN

Search production code for:

```text
TODO
FIXME
HACK
XXX
NotImplementedError
pass
stub
placeholder
mock
dummy
temporary
coming soon
```

Inspect each result manually.

Do not blindly treat Python `pass` as incomplete when semantically valid.

Complete genuine production-path gaps.

---

# 67. HARDCODED FALLBACK SCAN

Search for patterns such as:

```text
first()
limit(1)
default account
fallback account
first active
first linked
auto provider
default broker
```

Any place where financial routing guesses an account must be reviewed.

A deterministic safe default is acceptable only when user intent is unambiguous and policy-certified.

---

# 68. EXCEPTION SWALLOWING SCAN

Audit trading-critical code for patterns such as:

```python
except Exception:
    return False
```

or silent fallback.

Failures involving:

```text
broker state
risk
authentication
policy
reconciliation
```

must fail safely and produce observability.

---

# 69. STALE DATA SCAN

Audit any:

```text
balance
equity
margin
quote
symbol metadata
risk budget
subscription
```

cache used during execution.

Execution-critical data needs appropriate freshness rules.

---

# 70. CUSTOMER/ADMIN API PARITY

Verify every backend feature requiring control or visibility has an appropriate UI.

Examples:

```text
routing policy
broker policy
reconciliation freeze
strategy quarantine
kill switch
risk limit
```

Do not require database manipulation for normal operations.

---

# 71. WEB/MOBILE FEATURE PARITY POLICY

Not every admin/research feature needs mobile parity.

But core customer functions must have web/mobile parity:

```text
signals
positions
orders
brokers
routing
risk
automation
notifications
performance
safety controls
```

---

# 72. TEST DOCUMENTATION CLAIMS

Add regression tests that ensure obvious placeholder implementations cannot again be marked complete.

Examples:

```text
Next.js route inventory must exceed starter page
required customer routes must exist
required API integration must exist
default Next.js/Vercel starter text must not exist
```

---

# 73. DESIGN SYSTEM CONSOLIDATION

Apply the previously specified SignalRank design system to:

```text
Next.js web
Expo mobile
```

Use the same semantic:

```text
colors
spacing
status meanings
copy language
reason codes
```

while respecting native platform conventions.

---

# 74. NO NEW DUPLICATE BUSINESS LOGIC IN UI

Frontend/mobile must not independently decide:

```text
signal eligibility
execution eligibility
routing
risk
tier access
```

These come from backend policy.

UI may preview/explain them.

Backend remains authoritative.

---

# 75. ADDITIONAL GAP DISCOVERY

After all known issues above are fixed, perform another full audit.

Specifically look for issues analogous to the multi-broker problem:

```text
feature appears to exist
but only supports one provider/account/path

documentation says complete
but only foundation exists

UI displays capability
but backend does not enforce it

backend supports capability
but customer cannot configure it

one asset class is fully implemented
but others silently use inappropriate defaults

a “default” masks ambiguity

legacy fallback bypasses newer safety architecture
```

Fix every material instance.

---

# 76. REQUIREMENT COMPLETENESS

Do not stop with:

```text
foundation implemented
architecture ready
backend prepared
UI placeholder
future integration point
```

If a requirement is technically implementable inside the repository:

finish it.

---

# 77. NO PARTIAL ROUTING IMPLEMENTATION

Broker routing is complete only when:

```text
data model exists
migration exists if needed
policy service exists
routing engine exists
risk integration exists
account eligibility exists
cross-broker exposure exists
idempotency exists
fallback safety exists
frontend exists
mobile exists
Telegram behavior is consistent
audit events exist
tests pass
```

---

# 78. NO PARTIAL FRONTEND COMPLETION

Next.js replacement is complete only when:

```text
full customer routes exist
backend integration exists
auth exists
tier/role gating exists
responsive behavior exists
light/dark exists
loading/empty/error states exist
tests exist
production traffic can actually use it
legacy parity has been demonstrated
```

---

# 79. NO PARTIAL MOBILE COMPLETION

Mobile is complete only when:

```text
production navigation
auth
signals
positions
orders
paper
brokers
routing
risk
automation
performance
notifications
activity
settings/security
AUTO_CONFIRM
safety controls
```

work against canonical APIs where applicable.

---

# 80. FINAL AUDIT QUESTIONS

Before completion ask:

```text
Can connecting multiple brokers unexpectedly multiply risk?

Can the same signal accidentally trade multiple accounts?

Can fallback create duplicate exposure after an unknown broker response?

Can a PROP account become an unintended fallback?

Can “auto” choose a broker using only asset class?

Can an old first-account fallback bypass explicit account selection?

Can the user see why a broker was selected?

Can cross-broker BTC exposure bypass portfolio limits?

Can different-currency accounts be aggregated incorrectly?

Can stale equity produce the wrong size?

Can a manually edited broker position be overwritten?

Can subscription downgrade abandon an open position?

Can the frontend claim a feature exists when only backend foundations exist?

Can documentation say VERIFIED while a starter/template page remains?

Can legacy and new execution paths disagree?

Can web/mobile/Telegram display different execution modes?

Can a mobile customer enable AUTO without understanding which account will trade?

Can routing settings exist without backend enforcement?
```

Fix every material answer of YES.

Then repeat the audit.

---

# 81. FINAL STATUS FORMAT

For every discovered gap report:

```text
ID
Finding
Root cause
Affected files
Severity
Resolution
Tests
Status
```

Allowed final statuses:

```text
VERIFIED
BLOCKED_EXTERNAL
NOT_APPLICABLE
```

Do not leave technically implementable findings as:

```text
TODO
DEFERRED
PARTIAL
FOUNDATION_ONLY
```

---

# 82. FINAL DELIVERABLE

Provide:

```text
branch
commit SHA
PR
migration head
frontend route inventory
mobile screen inventory
broker routing modes
routing tests
cross-broker risk tests
legacy components removed/deprecated
corrected evidence-ledger entries
remaining external blockers
```

Do not declare completion until the actual repository state supports the claim.

---

# FINAL PRINCIPLE

Multiple broker connections must give the user:

```text
more coverage
better routing
better execution resilience
```

not:

```text
accidental duplicated trades
unclear broker selection
multiplied risk
```

The final system should always be able to answer:

```text
Why did SignalRank trade this account?
Why did it not trade the others?
How much total risk did this signal create?
What happens if the preferred broker fails?
What happens if I deliberately want the same signal on several accounts?
```

And the repository as a whole must be held to the same standard:

```text
If SignalRank says a capability exists,
the code, UI, tests and runtime must prove that it actually exists.
```