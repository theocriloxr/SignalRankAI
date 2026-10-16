# 126. FINAL COMPLETION, AUTONOMOUS IMPROVEMENT & ZERO-PLACEHOLDER DIRECTIVE

This section overrides any tendency to stop at scaffolding, partial implementation, proof-of-concept code, disconnected UI, TODOs, placeholders, fake data, mocked success paths, or documentation-only completion.

The objective is to leave SignalRankAI as a cohesive, production-oriented trading-intelligence platform whose implemented functionality actually works together end-to-end.

This applies to:

- backend;
- frontend;
- workers;
- schedulers;
- databases;
- Redis;
- APIs;
- Telegram;
- web;
- broker integrations;
- paper trading;
- automatic execution;
- risk;
- subscriptions;
- permissions;
- adaptive strategies;
- research;
- ML;
- AI;
- observability;
- security;
- deployment;
- recovery;
- testing.

---

# 127. CODEX MUST ADD ITS OWN IMPROVEMENTS

After implementing everything explicitly requested in:

1. the existing SignalRank specifications;
2. the current repository;
3. the Google trading-research document;
4. the research/anti-overfitting prompt;
5. the frontend/customer-experience prompt;
6. this final directive;

perform another independent architecture and product audit.

Identify any additional improvement that would materially improve:

```text
signal quality
statistical integrity
risk safety
execution reliability
customer experience
broker reliability
security
availability
observability
maintainability
performance
data quality
research reproducibility
portfolio management
operational control
```

Implement those improvements too when:

```text
the benefit is material
AND
the change is compatible with SignalRank's goals
AND
there is sufficient evidence to implement it correctly
AND
it does not introduce unjustified complexity
AND
it does not weaken an existing safety control.
```

Do not merely list good ideas at the end.

If a newly discovered improvement is materially necessary and technically implementable within the repository, implement it.

If it genuinely requires an unavailable external dependency, real-world evidence, credentials, legal approval, prolonged live observation, or a third-party capability, classify it truthfully as:

```text
BLOCKED_EXTERNAL
```

and explain exactly what remains.

Do not use `DEFERRED` simply because the work is difficult.

---

# 128. ZERO PLACEHOLDER POLICY

The completed repository must not contain newly introduced fake implementations such as:

```python
pass
```

where actual implementation is required.

Also prohibit newly introduced:

```text
TODO: implement later
FIXME: temporary
mock return
fake success
hardcoded demo result
placeholder response
dummy metrics
sample trade presented as real
coming soon
temporary always-true validation
temporary bypass
```

in production paths.

A feature must not appear enabled in the UI unless its backend capability exists and works.

A backend capability must not be considered customer-ready if no required frontend/customer interaction exists.

---

# 129. SEARCH FOR EXISTING INCOMPLETE IMPLEMENTATIONS

Perform repository-wide searches for patterns indicating unfinished functionality, including where relevant:

```text
TODO
FIXME
HACK
XXX
NotImplementedError
pass
return None
return {}
stub
placeholder
mock
dummy
temporary
coming soon
not implemented
unsupported
hardcoded
```

Do not blindly remove legitimate occurrences.

Classify each finding:

```text
legitimate
test-only
documentation
intentional unsupported capability
incomplete production functionality
dead code
```

Complete or remove genuine incomplete production functionality that falls within SignalRank's intended system.

---

# 130. NO FAKE SUCCESS STATES

Never return:

```text
200 OK
success: true
completed
connected
executed
verified
```

when the underlying action failed or was not confirmed.

Examples:

### Broker connection

Do not report:

```text
Connected
```

until the broker connection was actually validated.

### Trade submission

Do not report:

```text
Executed
```

until broker confirmation is available.

Use:

```text
REQUESTED
SUBMITTED
ACKNOWLEDGED
PARTIALLY_FILLED
FILLED
REJECTED
CANCELLED
UNKNOWN_REQUIRES_RECONCILIATION
```

where appropriate.

### Email/Telegram delivery

Distinguish:

```text
queued
attempted
provider accepted
confirmed delivery where available
failed
```

### Research

Do not label:

```text
validated
```

because a test suite passed.

### Deployment

Do not claim:

```text
production healthy
```

merely because a container started.

---

# 131. CANONICAL EVENT / STATE MODEL

Audit SignalRank for inconsistent definitions of:

```text
generated
candidate
accepted
rejected
eligible
suppressed
queued
delivered
opened
submitted
filled
active
managed
closed
cancelled
invalidated
expired
missed
```

Create one canonical state machine.

All:

```text
backend
database
workers
Telegram
web
analytics
admin
broker execution
research
```

must use the same semantics.

Invalid transitions must be rejected.

State changes must be:

```text
transactional
idempotent
auditable
timestamped
```

---

# 132. EVENT REPLAY AND RECONSTRUCTION

SignalRank should be able to reconstruct important decisions.

Implement or improve event/replay functionality so owner/admin can investigate:

```text
Why was this signal generated?
Why was this user eligible?
Why was another user not eligible?
Why did this trade execute?
Why was execution blocked?
Why was this quantity chosen?
Why was this trade closed?
Why was this strategy quarantined?
```

Where practical, maintain append-only decision events.

Each important event should contain:

```text
event_id
correlation_id
signal_id
user_id where applicable
broker_account_id where applicable
strategy_version
model_version
config_version
code_version
timestamp
reason_codes
```

---

# 133. END-TO-END CORRELATION IDs

Use trace/correlation IDs across:

```text
market data
signal generation
risk
ML
AI
eligibility
delivery
execution
broker
position management
outcome tracking
learning
```

A support/admin lookup should be able to trace one customer-facing event across the whole system.

---

# 134. CONFIGURATION VERSIONING

Every material trading decision should be reproducible against the configuration that existed at that moment.

Version important configuration such as:

```text
strategy settings
risk policy
tier entitlements
execution policy
broker capability policy
regime policy
model thresholds
signal thresholds
kill-switch state
```

Do not rely only on current settings when reconstructing historical decisions.

---

# 135. CENTRAL POLICY ENGINE

Avoid duplicating business rules across:

```text
Telegram
frontend
worker
engine
API
```

Create or consolidate canonical policy evaluation for:

```text
signal eligibility
execution eligibility
subscription entitlements
risk constraints
portfolio constraints
broker capabilities
strategy permissions
```

Consumers should ask the policy layer rather than recreating rules independently.

Return structured:

```text
allowed
reason_codes
constraints
policy_version
```

---

# 136. FEATURE FLAG GOVERNANCE

Any risky new feature should support controlled rollout.

Use feature flags for appropriate capabilities such as:

```text
new strategy family
new broker execution
new ML model
new risk system
new account workflow
```

Flags must be:

```text
server-side authoritative
environment-aware
audited
safe-by-default
```

Do not leave permanent temporary flags with unclear ownership.

---

# 137. RELEASE COMPATIBILITY

Before deployment verify compatibility between:

```text
code version
database schema
Redis schema/key format
model artifacts
feature versions
frontend API contract
worker API contract
```

Prevent mixed incompatible releases.

Every deployed role should expose:

```text
environment
Git SHA
branch
build timestamp
application version
database migration head
model version where relevant
```

---

# 138. API CONTRACT SAFETY

Use explicit API schemas.

Prevent frontend/backend drift.

Validate:

```text
request
response
enum values
nullable fields
pagination
errors
versions
```

Generate or test API contracts where appropriate.

Breaking changes must not silently reach production.

---

# 139. DATABASE TRANSACTION SAFETY

Audit all financial/trading state changes for transaction correctness.

Especially:

```text
order creation
position transitions
risk-budget reservations
subscription entitlement changes
broker-link changes
trade closure
outcome recording
```

Avoid partially committed state.

Use appropriate:

```text
transactions
constraints
locking
optimistic concurrency
idempotency
```

---

# 140. IDEMPOTENCY EVERYWHERE IT MATTERS

Ensure duplicate events cannot create duplicate effects.

Protect:

```text
broker order submission
Telegram webhook
payment webhook
subscription update
email notification
trade close
partial exit
stop modification
worker retry
scheduler retry
event replay
```

Store idempotency keys where needed.

---

# 141. DISTRIBUTED LOCKING REVIEW

Audit Redis/distributed locking.

Ensure:

```text
locks expire safely
lock ownership is verified
stale locks recover
critical jobs cannot run concurrently accidentally
```

Consider fencing tokens or equivalent protections where stale workers could cause dangerous writes.

---

# 142. BACKPRESSURE

SignalRank must degrade safely during overload.

Implement queue/backpressure handling for:

```text
market bursts
news bursts
broker delays
provider rate limits
notification spikes
research workloads
```

Trading-critical work should not be starved by lower-priority analytics.

Use priority classes where appropriate.

---

# 143. WORKLOAD SEPARATION

Keep:

```text
live execution
position management
market ingestion
signal generation
research
model training
backtesting
analytics
notifications
```

appropriately isolated.

A massive backtest must not delay a live stop-management action.

---

# 144. RESOURCE LIMITS

Set appropriate limits for:

```text
CPU
memory
worker concurrency
database connections
Redis connections
API concurrency
research jobs
```

Avoid unbounded task creation.

---

# 145. RATE-LIMIT GOVERNANCE

Create centralized provider-aware rate limiting.

Track:

```text
limit
remaining
reset
backoff
throttling
provider errors
```

Support:

```text
exponential backoff
jitter
circuit breakers
```

Do not let retries amplify outages.

---

# 146. CIRCUIT BREAKERS

Use circuit breakers where appropriate for:

```text
market providers
AI providers
brokers
email
Telegram
news
economic calendar
```

State should be observable.

Possible states:

```text
CLOSED
OPEN
HALF_OPEN
```

Do not keep hammering a failed service.

---

# 147. PROVIDER DISAGREEMENT ENGINE

For market data, where multiple providers exist:

detect material disagreement.

Do not silently select one when prices materially conflict.

Possible action:

```text
reduce confidence
quarantine symbol
switch provider
block execution
owner alert
```

Record provenance.

---

# 148. DATA PROVENANCE

Every important market/research datum should be traceable to:

```text
provider
symbol
timestamp
ingestion timestamp
normalization version
quality result
```

For aggregated features also preserve:

```text
source window
feature version
```

---

# 149. CLOCK AND TIME SYNCHRONIZATION

Trading systems depend on time.

Audit:

```text
server clock
broker timestamps
exchange timestamps
provider timestamps
UTC conversions
session boundaries
DST
```

Detect unreasonable clock drift.

Avoid local-time arithmetic in core trading logic.

Use UTC internally and local display time only where appropriate.

---

# 150. MARKET CALENDAR SERVICE

Create/consolidate a canonical calendar system for:

```text
FX
equities
indices
commodities
futures
crypto
```

Handle:

```text
holidays
half-days
closures
DST
session transitions
```

Do not hardcode universal market-open assumptions.

---

# 151. SYMBOL MAPPING GOVERNANCE

Maintain canonical mapping:

```text
SignalRank asset
→ market-data provider symbol
→ broker symbol
```

Version and validate mappings.

A missing/ambiguous mapping must block automatic execution.

Never guess broker symbols.

---

# 152. BROKER CAPABILITY DISCOVERY

Store broker/account capabilities such as:

```text
market orders
limit orders
stop orders
partial close
trailing stop
hedging/netting
fractional quantity
supported instruments
minimum size
precision
```

Execution must adapt to actual capability.

UI must only display supported actions.

---

# 153. BROKER RECONCILIATION LOOP

Continuously reconcile:

```text
SignalRank intended state
vs
broker actual state
```

Check:

```text
orders
fills
positions
stop loss
take profits
quantities
closed trades
```

Unknown state must fail safe.

Do not automatically duplicate an order because confirmation was lost.

---

# 154. BROKER-DEGRADED MODE

When broker state becomes uncertain:

```text
block new auto entries
continue safe monitoring where possible
attempt reconciliation
notify owner/user
```

Do not assume the trade failed.

Use:

```text
EXECUTION_STATE_UNKNOWN
```

until resolved.

---

# 155. PARTIAL-FILL ROBUSTNESS

Correctly handle:

```text
partial entry fills
partial exits
multiple fills
different prices
fees per fill
```

Risk and position state must reflect actual filled quantity, not requested quantity.

---

# 156. ORDER MODIFICATION RACES

Prevent races involving:

```text
stop update
manual close
partial take profit
broker callback
worker retry
```

Use versioning/locking and broker reconciliation.

---

# 157. ACCOUNT MODE DETECTION

Correctly distinguish:

```text
DEMO
LIVE
PROP/FUNDED if identifiable
```

Do not infer merely from the user choosing a label.

Where broker metadata cannot prove it, show:

```text
Unverified account type
```

---

# 158. PROP-FIRM COMPATIBILITY

Where users may connect funded/prop accounts, allow configurable constraints such as:

```text
daily drawdown
overall drawdown
trading-day requirements
news restrictions
weekend rules
lot limits
consistency rules
```

Do not claim compatibility with a prop firm unless its current rules are actually configured/verified.

Design the policy engine so rule profiles can be maintained without rewriting execution code.

---

# 159. PORTFOLIO RISK RESERVATION

Avoid race conditions where multiple signals simultaneously believe the same available risk budget is free.

Implement atomic risk reservation before automatic execution.

Flow:

```text
candidate
↓
calculate risk
↓
reserve risk budget atomically
↓
submit
↓
confirm/adjust reservation from actual fill
```

Release reservation if execution fails safely.

---

# 160. CROSS-ACCOUNT RISK OPTION

Where appropriate, support owner/user-defined aggregation across related accounts.

Example:

```text
MT5 account
+
crypto account
```

may share an overall risk budget.

Keep this optional and explicit.

---

# 161. PORTFOLIO FACTOR EXPOSURE

Improve portfolio-risk modelling beyond simple pairwise correlation.

Where data supports it, detect common exposures such as:

```text
USD
crypto beta
technology
equity risk-on
interest rates
oil
gold
country/sector
```

Do not pretend exact factor precision where data is weak.

---

# 162. TAIL-RISK EVENTS

Add defensive handling for:

```text
flash crash
exchange outage
large gap
extreme spread
abnormal volatility
liquidity collapse
```

The appropriate response may include:

```text
no new entries
reduced size
manual review
provider failover
```

Avoid automatically selling into an invalid/stale quote.

---

# 163. VOLATILITY HALTS

Create configurable abnormal-volatility detection.

Differentiate:

```text
legitimate high volatility
bad data spike
```

using provider agreement and quality checks.

---

# 164. NEWS/EVENT FAILSAFE

If required event data is unavailable and a strategy depends on news-risk filtering:

fail according to a defined safe policy.

Do not silently assume:

```text
no news
```

because the news provider failed.

---

# 165. AI PROVIDER FAILURE

SignalRank must continue safely if OpenAI or another AI provider is unavailable.

Classify AI functions:

```text
critical
optional
advisory
```

No trading-critical pipeline should unknowingly bypass a mandatory AI gate because the provider returned an error.

Use explicit:

```text
AI_GATE_UNAVAILABLE
```

with configured safe behavior.

---

# 166. AI PROMPT VERSIONING

Version prompts used for:

```text
news analysis
market context
research critic
trade explanation
post-trade review
```

Log prompt version with decisions.

Changes in prompts must be testable and auditable.

---

# 167. AI OUTPUT VALIDATION

Schema validation is mandatory.

Reject:

```text
malformed
missing
out-of-range
contradictory
```

AI outputs.

Do not parse critical decisions from free-form prose.

---

# 168. AI COST & USAGE GOVERNANCE

Track:

```text
provider
model
tokens
cost
latency
purpose
user/system attribution
```

Use caching/deduplication where safe.

Prevent runaway AI calls.

---

# 169. MODEL ARTIFACT SECURITY

Verify:

```text
artifact hash
source
version
feature contract
```

before loading ML models.

Avoid unsafe serialization formats where possible.

Never load arbitrary user-supplied model code.

---

# 170. FEATURE CONTRACTS

Every ML model should declare required:

```text
feature names
types
units
order
version
missing-value policy
```

Reject prediction if the runtime feature contract does not match.

Do not silently reorder or drop features.

---

# 171. FEATURE FRESHNESS

Track how old each feature is.

A current price combined with stale:

```text
news
higher-timeframe data
order book
macro
```

can produce invalid decisions.

Define feature freshness policies.

---

# 172. DATASET IMMUTABILITY

Research results should reference immutable dataset snapshots/hashes where possible.

Do not allow a backtest to silently change because historical source data was modified.

---

# 173. REPRODUCIBLE RESEARCH

Given an experiment ID, the system should be able to reproduce or closely reconstruct:

```text
dataset
features
configuration
code version
model
random seed
execution assumptions
```

Document exceptions for external data that cannot be perfectly reproduced.

---

# 174. STATISTICAL CONFIDENCE

Where reporting strategy performance, include uncertainty.

For suitable metrics calculate:

```text
confidence intervals
bootstrap intervals
sample size
```

Avoid presenting:

```text
67.4% win rate
```

with false precision from 19 trades.

---

# 175. SERIAL DEPENDENCE

Returns/trades may not be IID.

Where appropriate, account for:

```text
autocorrelation
clustered trades
regime dependence
```

when estimating significance.

Use block/bootstrap techniques where justified.

---

# 176. PARAMETER STABILITY

Strategies whose performance exists only around one tiny parameter point should be penalized.

Analyze neighboring parameter configurations.

Prefer:

```text
stable plateau
```

over:

```text
single sharp optimum
```

when other evidence is comparable.

---

# 177. STRATEGY COMPLEXITY PENALTY

Consider complexity when strategies perform similarly.

Prefer a simpler robust rule over an extremely complex rule with marginally higher backtest performance.

Track:

```text
parameter count
feature count
rule complexity
```

as research metadata.

---

# 178. DATA-SNOOPING GOVERNANCE

Ensure repeated manual researcher interaction is also reflected in experimentation history where practical.

A human manually testing 50 combinations is still multiple testing.

Do not count only automated Optuna trials.

---

# 179. NEGATIVE RESEARCH RESULTS

Preserve rejected experiments.

Do not delete failed ideas.

Store them to:

```text
prevent retesting identical failed hypotheses
improve multiple-testing accounting
learn what does not work
```

---

# 180. RESEARCH BUDGETS

Avoid infinite strategy search.

Allow bounded:

```text
compute budget
experiment count
time budget
```

per research job.

This makes experimentation reproducible and prevents resource exhaustion.

---

# 181. CHAMPION / CHALLENGER COMPETITION

Maintain:

```text
CHAMPION
CHALLENGER
RETIRED
REJECTED
QUARANTINED
```

A challenger must defeat the champion on predefined criteria, not simply one metric.

Promotion must not automatically increase real-money risk immediately.

---

# 182. STAGED RISK PROMOTION

When a new strategy/model reaches live use:

```text
CANARY
→ LIMITED_LIVE
→ broader production
```

Risk limits should expand gradually based on evidence.

Do not jump from SHADOW directly to maximum production risk.

---

# 183. AUTOMATIC ROLLBACK

Where safe, support automatic rollback to a previously approved model/strategy version when a new deployment fails technical health gates.

For trading-performance deterioration, prefer quarantine/review rather than blindly restoring an old strategy whose edge may also have decayed.

---

# 184. SOFTWARE RELEASE CANARY

Separate:

```text
software canary
```

from:

```text
trading-strategy canary
```

A code release can be technically correct while a strategy remains unproven.

Track both.

---

# 185. DEPLOYMENT HEALTH GATE

After deployment verify:

```text
database
Redis
providers
worker heartbeats
scheduler
Telegram
web API
frontend
model loading
broker sandbox/demo connection
```

before declaring the deployment healthy.

---

# 186. STARTUP SELF-TEST

Each service should perform safe startup validation.

Examples:

```text
schema compatibility
required configuration
Redis connectivity where required
model artifact compatibility
provider configuration
```

Fail closed where running would be unsafe.

Avoid blocking harmless services because an unrelated optional provider is unavailable.

---

# 187. READINESS VS LIVENESS

Separate:

```text
liveness
readiness
```

A process can be alive but not ready to trade.

Readiness should incorporate critical dependencies for that role.

---

# 188. WORKER HEARTBEATS

Track:

```text
last heartbeat
current job
last successful job
error count
queue lag
```

Alert when critical workers stall.

---

# 189. SCHEDULER DRIFT

Detect scheduled jobs running:

```text
late
twice
not at all
```

Use distributed coordination.

Expose scheduler health.

---

# 190. DATA LAG MONITORING

Track lag between:

```text
market timestamp
ingestion
feature generation
signal
delivery
execution
```

Signal quality and execution should account for excessive delay.

---

# 191. SLO / SLI DEFINITIONS

Define measurable service objectives for important paths.

Examples:

```text
market-data freshness
signal processing latency
broker reconciliation lag
critical worker availability
notification delivery
API latency
```

Do not use one blanket uptime number.

---

# 192. ALERT PRIORITY

Classify alerts:

```text
INFO
WARNING
HIGH
CRITICAL
```

Prevent alert spam.

Deduplicate repeated failures.

Escalate persistent critical failures.

---

# 193. OWNER INCIDENT CENTER

Provide an operational view answering:

```text
What is broken?
When did it start?
Who/what is affected?
Are trades at risk?
Are new entries blocked?
What automatic protection fired?
```

---

# 194. INCIDENT TIMELINE

For serious incidents preserve:

```text
first detected
automated action
owner action
recovery
resolution
```

Useful for postmortems.

---

# 195. POSTMORTEM SUPPORT

After serious execution/system incidents generate structured evidence for:

```text
root cause
impact
timeline
safety systems activated
missed safeguards
corrective actions
```

Do not automatically invent a root cause.

---

# 196. CHAOS / FAILURE TESTING

Test controlled failures in staging:

```text
Redis unavailable
Postgres restart
market-data outage
AI outage
broker timeout
Telegram failure
worker crash
scheduler restart
network latency
duplicate message
out-of-order message
```

Verify safe recovery.

Do not run destructive chaos testing against production.

---

# 197. DISASTER RECOVERY

Document and verify:

```text
backup frequency
backup encryption
retention
restore procedure
restore test
RPO
RTO
```

A backup that has never been restored is not considered verified.

---

# 198. DATABASE RESTORE TEST

Perform a staging restore drill using real backup procedures.

Verify:

```text
schema
data integrity
critical records
migration compatibility
service startup
```

Production restore must be rehearsed before being claimed ready.

---

# 199. REDIS LOSS RECOVERY

Classify Redis data into:

```text
reconstructable cache
critical ephemeral state
locks
queues
```

Ensure a Redis restart cannot permanently lose essential financial truth.

PostgreSQL or another durable system should remain canonical for critical state where appropriate.

---

# 200. LOG SECURITY

Do not log:

```text
broker passwords
API keys
tokens
session secrets
full payment data
```

Mask sensitive account identifiers where appropriate.

---

# 201. SECRET ROTATION

Ensure secrets can be rotated without rebuilding major parts of the system.

Support orderly:

```text
broker credential replacement
provider-key rotation
webhook secret rotation
JWT/session secret procedures
```

where architecture permits.

---

# 202. SESSION SECURITY

For web users implement appropriate:

```text
secure cookies
CSRF protection where relevant
session expiry
revocation
refresh-token safety
device/session visibility
```

High-risk account actions may require reauthentication where appropriate.

---

# 203. STEP-UP AUTH FOR DANGEROUS ACTIONS

Consider step-up verification for actions such as:

```text
enable AUTO
change broker credentials
increase major risk limits
emergency close all
```

Use existing authentication architecture rather than inventing insecure alternatives.

---

# 204. RBAC / ABAC AUDIT

Review all permissions.

Ensure:

```text
customer
support
admin
owner
research
operations
```

only see/use appropriate capabilities.

Where needed include account ownership and environment in authorization decisions.

---

# 205. TENANT ISOLATION

Ensure one user's:

```text
signals
broker accounts
orders
positions
settings
performance
```

cannot leak to another user.

Add tests specifically for cross-user authorization.

---

# 206. WEBHOOK SECURITY

Verify:

```text
signature
timestamp/replay protection
idempotency
source validation
```

for supported webhooks.

Reject invalid callbacks.

---

# 207. DEPENDENCY SECURITY

Audit:

```text
Python
Node
container
GitHub actions
```

dependencies.

Resolve known high/critical vulnerabilities where safely possible.

Pin versions appropriately.

Do not blindly upgrade trading-critical libraries without regression testing.

---

# 208. SUPPLY-CHAIN SAFETY

Protect:

```text
CI secrets
artifact provenance
dependency lockfiles
container images
```

Use reproducible builds where practical.

---

# 209. STATIC & DYNAMIC ANALYSIS

Integrate appropriate:

```text
linting
typing
security scanning
secret scanning
dependency scanning
```

Fix findings rather than disabling scanners to get green CI.

If tooling times out, fix the scan scope/performance rather than silently ignoring it.

---

# 210. TYPE SAFETY

Reduce `Any` and ambiguous data dictionaries in trading-critical code.

Prefer typed models for:

```text
signals
orders
fills
positions
risk decisions
strategy evidence
```

Validate boundaries.

---

# 211. MONEY / PRECISION SAFETY

Avoid unsafe binary floating-point assumptions for broker-facing financial quantities where decimal precision matters.

Respect:

```text
tick size
lot step
currency precision
minimum notional
```

Perform rounding intentionally.

---

# 212. CURRENCY CONVERSION

Portfolio/risk aggregation across different account currencies must use appropriately timestamped conversion rates.

Store conversion source/time.

Do not sum:

```text
USD + EUR + NGN
```

directly.

---

# 213. PNL ACCOUNTING

Clearly define:

```text
gross P/L
fees
funding
commission
swap
slippage
net P/L
```

Use net P/L for meaningful performance reporting.

---

# 214. REALIZED VS UNREALIZED

Never mix realized and unrealized P/L ambiguously.

Customer dashboard should label each clearly.

---

# 215. PERFORMANCE ATTRIBUTION

Where feasible explain whether performance came from:

```text
strategy selection
position sizing
execution quality
manual user intervention
market regime
```

Avoid overstating strategy quality when execution or sizing drove results.

---

# 216. BENCHMARKS

Allow appropriate strategy research benchmarks.

Examples:

```text
buy-and-hold
cash
relevant index
simple baseline strategy
```

Use only where meaningful.

---

# 217. STRATEGY CAPACITY

Estimate whether a strategy's simulated performance remains plausible as user capital grows.

Avoid suggesting identical fill quality for unlimited capital.

---

# 218. STRATEGY CROWDING

Where enough internal data exists, monitor whether many users/strategies are attempting highly similar trades.

Do not claim market-wide crowding without external evidence.

Internal concentration can still inform execution/risk.

---

# 219. FAIR USER EXECUTION

If many users receive the same automatic trade:

design order submission so the system does not unfairly or accidentally create pathological sequential delays.

Consider batching/scheduling while respecting:

```text
broker
account
risk
price movement
```

Never share one user's credentials or orders with another.

---

# 220. PRICE-DEVIATION REVALIDATION

Between:

```text
signal generation
and
execution
```

revalidate important assumptions if price materially moves.

Potential checks:

```text
entry range
RR
stop distance
spread
volatility
regime
```

Do not execute a stale opportunity merely because it once passed.

---

# 221. SIGNAL REVALIDATION

For slower execution paths such as AUTO_CONFIRM, revalidate the signal at confirmation time.

If the setup is no longer valid:

```text
confirmation expired / setup invalidated
```

Do not execute.

---

# 222. ORDER INTENT MODEL

Before sending a broker order create a durable:

```text
OrderIntent
```

containing:

```text
signal
user
broker account
requested side
requested size
risk decision
price constraints
idempotency key
timestamp
policy versions
```

Then execution attempts operate against that intent.

This improves auditability and retry safety.

---

# 223. EXECUTION RECEIPTS

Persist broker-confirmed:

```text
broker order ID
broker deal/fill ID
requested size
filled size
fill price
fees
timestamp
```

Do not rely only on logs.

---

# 224. BROKER ACTION AUDIT

Every:

```text
submit
modify
cancel
close
```

broker action should have:

```text
request
response
result
latency
retry count
```

with secrets removed.

---

# 225. MANUAL VS AUTOMATED ORIGIN

Every order/position should indicate origin:

```text
SIGNALRANK_AUTO
SIGNALRANK_AUTO_CONFIRM
SIGNALRANK_MANUAL_ACTION
BROKER_EXTERNAL_MANUAL
UNKNOWN
```

This prevents incorrect performance attribution and management.

---

# 226. USER OVERRIDE PRECEDENCE

Define exactly what happens if a user manually changes a SignalRank-managed trade.

User intent must be respected.

Do not repeatedly overwrite manual changes.

---

# 227. POSITION OWNERSHIP

SignalRank must never automatically manage an unrelated broker position unless the user explicitly imports/adopts it and policy permits.

---

# 228. SAFE DISCONNECT

When a user disconnects a broker:

explain what happens to currently open SignalRank-managed positions.

Offer explicit choices where supported:

```text
leave positions untouched
disable automated management
close eligible positions first
```

Do not surprise the user.

---

# 229. SUBSCRIPTION DOWNGRADE SAFETY

If a user's plan changes while automated positions are open:

do not abandon positions.

Separate:

```text
permission to open new trades
```

from:

```text
safe management of existing positions
```

Define a safe downgrade policy.

---

# 230. PAYMENT FAILURE SAFETY

A failed subscription payment must not abruptly cause dangerous position abandonment.

Block new premium actions if required, but safely manage already-open positions according to policy.

---

# 231. ACCOUNT DELETION SAFETY

Before account deletion:

detect connected brokers and open managed positions.

Require explicit handling.

Do not delete records required for legal/audit/reconciliation obligations prematurely.

---

# 232. DATA RETENTION

Define retention for:

```text
market data
signals
orders
broker events
research
logs
AI inputs/outputs
user audit history
```

Apply legal/product requirements appropriately.

---

# 233. PRIVACY MINIMIZATION

Store only data needed for product operation, safety, legal obligations and research.

Avoid unnecessary sensitive data.

Separate internal identifiers from public/support references where practical.

---

# 234. EXPORTABILITY

Allow users to export suitable:

```text
signals
trade history
performance
account activity
```

without exposing proprietary strategy internals.

---

# 235. USER DATA DELETION WORKFLOW

Where deletion is allowed, ensure it does not break financial/audit integrity.

Use policy-aware retention/anonymization where required.

---

# 236. INTERNATIONALIZATION READINESS

Avoid embedding:

```text
currency
timezone
number/date formats
```

into components in ways that prevent future localization.

SignalRank can initially use chosen supported locales but architecture should be ready.

---

# 237. TIMEZONE UX

Store UTC internally.

Display relevant customer timezone clearly.

Market sessions should remain based on their actual market timezone, not user local time.

---

# 238. NOTIFICATION DEDUPLICATION

Do not send:

```text
Telegram
email
web
```

duplicates caused by worker retry.

Use notification idempotency.

---

# 239. ESCALATION POLICY

High-severity events such as:

```text
auto-execution disabled unexpectedly
broker reconciliation failure
critical risk breach
```

should trigger appropriate owner/user alerts.

Do not treat routine signal rejection as critical.

---

# 240. CUSTOMER STATUS PAGE

Where useful, expose customer-friendly operational status:

```text
Signal generation
Broker connectivity
Notifications
```

without revealing infrastructure secrets.

---

# 241. SUPPORT OPERABILITY

Support/admin tooling should help diagnose a user's problem without requiring direct database manipulation.

Support actions must be permissioned and audited.

---

# 242. NO DIRECT DATABASE "FIXES" AS PRODUCT WORKFLOW

Do not design normal administrative operations that require manually editing PostgreSQL.

Build proper:

```text
API
admin action
workflow
```

for recurring operational tasks.

---

# 243. SAFE ADMIN OVERRIDES

Where owner/admin overrides are necessary:

require:

```text
reason
actor
timestamp
previous value
new value
```

High-risk overrides may require additional confirmation.

---

# 244. CONFIGURATION DIFFS

When production/staging configuration differs materially, provide a sanitized diff.

Detect missing/extra variables.

Do not reveal secrets.

---

# 245. STAGING / PRODUCTION ISOLATION

Guarantee isolation of:

```text
database
Redis
broker/demo/live credentials
webhooks
queues
storage
```

between staging and production.

Application startup should detect obvious cross-environment misconfiguration.

---

# 246. DEMO BROKER SAFETY

Staging should default to:

```text
demo
paper
sandbox
```

connections.

Prevent accidentally using production live broker credentials in staging unless a deliberate secure process exists.

---

# 247. ENVIRONMENT BANNERS

Owner/admin interfaces should visibly show:

```text
STAGING
PRODUCTION
```

to reduce operational mistakes.

---

# 248. PRODUCTION MUTATION CONFIRMATION

High-risk owner actions in production should clearly say they affect production.

Do not require the same friction for harmless read-only operations.

---

# 249. MIGRATION GATES

Prevent application startup when required migrations are missing.

Do not automatically run unsafe destructive migrations without the project's approved release process.

---

# 250. MIGRATION SAFETY TESTS

For significant schema changes test:

```text
existing production-like data
upgrade
service compatibility
rollback/recovery
```

Avoid only testing fresh empty databases.

---

# 251. DATA BACKFILL JOBS

Large backfills should be:

```text
resumable
idempotent
observable
rate-limited
```

Do not block application startup for massive backfills.

---

# 252. PERFORMANCE / LOAD TESTING

Run realistic staging load tests for:

```text
simultaneous users
signal bursts
broker account scale
websocket connections
Telegram delivery
research jobs
```

Record bottlenecks.

Do not claim scale beyond tested evidence.

---

# 253. DATABASE QUERY AUDIT

Find:

```text
N+1 queries
missing indexes
slow hot-path queries
unbounded result sets
```

especially on:

```text
signals
positions
broker events
analytics
```

Fix material issues.

---

# 254. CACHE CORRECTNESS

Caching must never serve stale dangerous state for:

```text
kill switch
risk limit
broker connection
subscription entitlement
```

Use appropriate invalidation/TTL or bypass caching.

---

# 255. PAGINATION

Large histories must use server-side pagination/cursors.

Do not fetch thousands of trades into the browser.

---

# 256. ARCHIVAL

Archive old heavy analytical data where appropriate without breaking auditability.

Keep hot operational tables performant.

---

# 257. FRONTEND DATA CONSISTENCY

Avoid multiple pages independently interpreting raw API state differently.

Use canonical typed frontend models and shared status-formatting helpers.

---

# 258. OPTIMISTIC UI SAFETY

Do not optimistically show:

```text
trade executed
auto enabled
broker disconnected
```

until the backend confirms the action.

Optimistic UI is acceptable only for low-risk reversible presentation interactions.

---

# 259. STALE PAGE PROTECTION

Before dangerous actions, refresh/revalidate server state.

A browser tab open for hours must not submit using stale:

```text
risk
signal
price
subscription
broker
```

assumptions.

---

# 260. DOUBLE-CONFIRMATION ONLY WHERE WARRANTED

Avoid confirmation fatigue.

Use stronger confirmation only for genuinely dangerous actions such as:

```text
enable live AUTO
increase risk significantly
emergency close
disconnect while managed positions exist
```

Routine safe actions should remain easy.

---

# 261. UX TELEMETRY

Track privacy-conscious aggregate product events such as:

```text
broker connection failures
abandoned onboarding step
auto activation failures
settings validation errors
```

Use them to find confusing flows.

Do not turn telemetry into invasive tracking.

---

# 262. CUSTOMER ERROR RECOVERY

Every major failure screen should provide a sensible next action.

Example:

```text
Broker login expired.

[Reconnect]
[Switch to Signals Only]
```

Do not create dead ends.

---

# 263. DATA REFRESH INDICATOR

For important financial data show:

```text
Updated 8 seconds ago
```

where useful.

If stale beyond acceptable limits, visibly flag it.

---

# 264. CUSTOMER RISK SUMMARY

Create a concise persistent summary:

```text
Auto trading: ON
Account: Main MT5
Risk profile: Conservative
Risk/trade: 0.5%
Daily remaining risk: 1.2%
Open positions: 2/4
```

This should be quickly accessible.

---

# 265. ACCOUNT HEALTH CHECK

Before AUTO operation continuously verify:

```text
broker connected
market-data healthy
account tradable
margin valid
permissions valid
execution route healthy
risk system healthy
```

If a critical check fails, pause new auto entries.

---

# 266. SAFE AUTO-RESUME

After a critical failure, do not always automatically resume execution immediately.

For serious uncertainty:

```text
PAUSED_REQUIRES_REVIEW
```

may be safer.

Define which failures:

```text
auto-resume
require confirmation
require owner intervention
```

---

# 267. MAINTENANCE MODE

Implement safe operational maintenance mode.

Separate:

```text
website maintenance
signal-generation maintenance
execution maintenance
```

Existing positions must continue to be safely managed according to policy where possible.

---

# 268. DEPLOYMENT DRAIN

Before stopping execution workers, safely drain/hand off work.

Avoid terminating processes halfway through broker actions.

---

# 269. GRACEFUL SHUTDOWN

Critical workers should:

```text
stop accepting new work
finish/secure critical transaction
release/expire locks
persist state
```

on shutdown where possible.

---

# 270. CRASH RECOVERY

On restart reconcile:

```text
in-flight orders
positions
queued executions
locks
scheduled jobs
```

before resuming normal automatic trading.

---

# 271. EXACTLY-ONCE EFFECT, NOT ASSUMPTION

Distributed systems generally cannot assume perfect exactly-once message delivery.

Design for:

```text
at-least-once delivery
+
idempotent effects
```

where appropriate.

---

# 272. UNKNOWN STATE IS A FIRST-CLASS STATE

If SignalRank cannot know whether an external broker action completed:

do not guess.

Use:

```text
UNKNOWN
RECONCILING
```

and block unsafe follow-up actions.

---

# 273. HUMAN-IN-THE-LOOP ESCALATION

For ambiguous high-risk situations allow:

```text
OWNER_REVIEW_REQUIRED
USER_CONFIRMATION_REQUIRED
```

rather than forcing an automated decision.

---

# 274. SAFETY PRECEDENCE

When rules conflict, define precedence.

Recommended general ordering:

```text
global emergency controls
↓
regulatory/platform hard constraints
↓
broker/account constraints
↓
portfolio risk
↓
user hard limits
↓
strategy rules
↓
user preferences
↓
UI defaults
```

Document the final implemented precedence.

---

# 275. CONFIGURATION INVARIANTS

Validate impossible or contradictory settings.

Examples:

```text
AUTO enabled
but no executable broker

max positions = 0
but AUTO active

daily loss limit below risk/trade

asset allowed
but broker does not support it
```

Explain conflicts to users.

---

# 276. SIGNAL EXPLAINABILITY CONTRACT

Every delivered signal should have an explanation generated from stored deterministic evidence.

AI may improve wording but must not invent reasons that were not part of the actual decision.

---

# 277. REASON CODE TAXONOMY

Create canonical machine-readable codes for:

```text
generation
rejection
eligibility
risk
execution
broker
health
```

Map them to customer-friendly text.

This avoids inconsistent messages across web/Telegram.

---

# 278. AUDIT LOG TAMPER RESISTANCE

For important administrative/trading audit events consider append-only storage or integrity hashes where appropriate.

Normal admins should not be able to silently rewrite history.

---

# 279. PRIVILEGED ACTION ALERTING

Alert owner/security for appropriate events such as:

```text
global risk limit changed
kill switch disabled
live AUTO enabled globally
broker credentials changed
admin role changed
```

Avoid unnecessary noise.

---

# 280. EXTERNAL DEPENDENCY INVENTORY

Maintain an inventory of:

```text
market data
brokers
AI
news
email
Telegram
payment
hosting
database
cache
```

For each capture:

```text
purpose
criticality
fallback
failure behavior
```

---

# 281. SINGLE-POINT-OF-FAILURE REVIEW

Identify any external/internal component whose failure can stop:

```text
position management
critical risk control
signal delivery
```

Where practical, add fallback or safe degradation.

---

# 282. FAILURE BEHAVIOR MUST BE EXPLICIT

Every external dependency must define:

```text
FAIL_OPEN
FAIL_CLOSED
DEGRADE
```

according to the risk of that function.

Do not accidentally fail open on safety controls.

---

# 283. STRATEGY DEPENDENCY DECLARATION

Each strategy should declare which inputs are mandatory.

Example:

```text
requires_orderbook=true
requires_news=false
```

If required data is unavailable:

do not fabricate substitutes.

---

# 284. QUALITY-AWARE SCORING

Market-data quality should affect or block signals.

A high strategy score based on questionable data should not remain high-confidence.

---

# 285. EXECUTION-AWARE SIGNAL SCORE

Separate:

```text
market opportunity quality
```

from:

```text
execution quality
```

A good setup with:

```text
huge spread
low liquidity
bad latency
```

may remain a valid analytical signal but be unsuitable for automation.

---

# 286. USER SUITABILITY WITHOUT HIDDEN DISCRIMINATION

Personalization should use explicit product/risk preferences and account state.

Do not infer sensitive personal traits to determine trading access.

---

# 287. RETRAINING GOVERNANCE

Scheduled/retriggered ML retraining must:

```text
produce challenger
validate
shadow test
```

before promotion.

Never automatically overwrite the production model simply because a training job completed.

---

# 288. MODEL ROLLBACK HISTORY

Preserve:

```text
what was active
when
why promoted
why retired
```

for every production model.

---

# 289. TRAINING DATA QUALITY GATE

Do not train models on datasets that fail:

```text
coverage
label integrity
feature completeness
point-in-time correctness
```

---

# 290. OUTCOME COMPLETENESS

Do not evaluate models/strategies using heavily incomplete outcome sets without clearly accounting for missingness.

Track outcome coverage.

---

# 291. CENSORING

Recognize trades/signals whose full outcome is not yet known.

Do not automatically classify open/expired-window observations incorrectly.

---

# 292. LABEL VERSIONING

Outcome/target definitions must be versioned.

Changing:

```text
what counts as win
```

must not silently reinterpret historical metrics.

---

# 293. PAPER/LIVE PARITY

Paper execution should share as much production logic as safely possible:

```text
eligibility
risk
order intent
position lifecycle
```

with execution adapter swapped.

This reduces divergence.

---

# 294. SHADOW/LIVE PARITY

Shadow candidates should receive the same market/context inputs as live decisions where possible.

Do not create an artificially easier shadow environment.

---

# 295. BACKTEST/LIVE SEMANTIC PARITY

Where concepts differ between backtest and live execution, explicitly document them.

Do not use the same field name with different meanings.

---

# 296. GOLDEN TEST SCENARIOS

Create deterministic end-to-end fixtures representing:

```text
normal winning trade
normal losing trade
partial fill
same-bar TP/SL
price gap
broker rejection
broker timeout
manual intervention
daily-risk block
portfolio-correlation block
signal expiry
stale market data
news block
provider outage
```

Run them in CI where practical.

---

# 297. CONTRACT TESTS AGAINST BROKER ADAPTERS

For every broker adapter verify a shared contract.

A new broker must pass the same behavior suite before being considered supported.

---

# 298. SIMULATED BROKER

Maintain a deterministic simulator specifically for:

```text
CI
failure testing
execution lifecycle
```

This is different from customer paper trading.

It must support forced:

```text
reject
timeout
partial fill
disconnect
```

scenarios.

---

# 299. END-TO-END TEST ENVIRONMENT

Create a reproducible test/staging path that exercises:

```text
signal
eligibility
execution intent
broker simulator/demo
position
outcome
UI
Telegram
```

not only isolated unit tests.

---

# 300. AUTOMATED UI E2E

Add browser-level tests for critical journeys:

```text
login
onboarding
connect broker flow
change mode
AUTO activation
signal viewing
AUTO_CONFIRM
risk settings
emergency stop
```

Test mobile viewport(s) as part of CI where practical.

---

# 301. VISUAL REGRESSION

For critical screens consider screenshot/visual regression testing.

Catch:

```text
overflow
broken themes
missing buttons
layout regressions
```

especially on mobile.

---

# 302. ACCESSIBILITY AUTOMATION

Add automated accessibility checks to complement manual WCAG testing.

Do not treat automated checks as sufficient by themselves.

---

# 303. BROWSER CONSOLE CLEANLINESS

Critical journeys should not produce unexpected:

```text
console errors
uncaught promise rejections
React hydration warnings
```

Fix them.

---

# 304. NETWORK ERROR TESTS

Test frontend when:

```text
API times out
request fails
response is malformed
authentication expires
```

Ensure recovery UX works.

---

# 305. OFFLINE/RECONNECT BEHAVIOR

If browser connectivity is lost:

do not present stale trading state as current.

Clearly indicate:

```text
Connection lost
```

and re-sync on reconnect.

---

# 306. SECURITY HEADERS

Audit:

```text
CSP
HSTS
frame protection
content-type protection
referrer policy
```

and related production security settings.

---

# 307. CORS

Restrict CORS properly.

Do not use unrestricted origins with credentials.

---

# 308. API ABUSE PROTECTION

Protect sensitive endpoints with appropriate:

```text
rate limits
authorization
request-size limits
```

without preventing legitimate trading operations.

---

# 309. BOT / AUTOMATION ABUSE

Protect public endpoints from obvious automated abuse.

Do not interfere with expected Telegram/webhook provider traffic.

---

# 310. QUERY / FILTER LIMITS

Prevent expensive customer/admin queries from unintentionally exhausting database resources.

---

# 311. REPORT GENERATION JOBS

Heavy exports/analytics should run safely without blocking live operations.

---

# 312. CUSTOMER EXPORT ACCURACY

Performance exports must include clear:

```text
timezone
currency
gross/net
paper/live
```

labels.

---

# 313. AUDIT EXPORT

Owner/admin should be able to export relevant evidence for investigation without direct database access.

---

# 314. COST OBSERVABILITY

Track infrastructure/provider cost drivers where feasible:

```text
AI
market data
database
Redis
notifications
broker requests
```

Do not allow research/AI workloads to unexpectedly consume unlimited resources.

---

# 315. COST SAFETY LIMITS

Use quotas/limits for non-critical expensive workloads.

Trading safety must not be disabled just to save cost.

---

# 316. STORAGE GROWTH

Monitor:

```text
database size
market-data growth
logs
research artifacts
```

Alert before storage exhaustion.

---

# 317. RETENTION JOB HEALTH

Retention jobs must be observable and safe.

Never delete currently-needed audit/trading records due to a faulty cleanup job.

---

# 318. CLOCKED CLEANUP

Large cleanup should be batched, not lock critical tables.

---

# 319. VERSIONED DOCUMENTATION

Keep operational documentation aligned with the current release.

Do not leave old deployment guides as if they were current.

Clearly mark deprecated documents.

---

# 320. REPOSITORY MAP

Maintain an updated repository architecture map showing:

```text
services
workers
core modules
data flow
execution flow
research flow
frontend
```

This must reflect actual code.

---

# 321. DEAD CODE REMOVAL

After consolidation, identify clearly unused duplicate implementations.

Remove only after proving they are not referenced.

Do not leave multiple competing sources of truth.

---

# 322. DEPRECATION POLICY

Where old APIs/configs remain temporarily:

```text
mark deprecated
log usage
provide migration
remove when safe
```

Do not maintain silent compatibility forever.

---

# 323. NO SILENT FALLBACK TO WRONG BEHAVIOR

Fallbacks must preserve semantics.

Example:

If order-book data is unavailable:

do not silently replace it with candle volume and label it order flow.

If live broker execution fails:

do not silently treat a paper trade as live.

---

# 324. FAILING TESTS ARE NOT ACCEPTABLE COMPLETION

At completion:

```text
unit
integration
contract
migration
security
frontend
critical E2E
```

tests must pass for the changed implementation unless a test requires a documented unavailable external system.

Do not simply disable failing tests.

Do not weaken assertions just to make CI green.

---

# 325. WARNINGS MUST BE REVIEWED

Review:

```text
compiler
type checker
lint
runtime deprecation
build
```

warnings.

Fix material warnings.

Do not ignore warnings affecting trading correctness/security.

---

# 326. CI MUST TEST THE ACTUAL CANDIDATE

All hosted CI evidence must correspond to the exact candidate commit intended for deployment.

Do not report tests from an older SHA.

---

# 327. DEPLOY SAME ARTIFACT

Where architecture allows, deploy the same built candidate/artifact across staging roles.

Avoid rebuilding subtly different artifacts independently.

---

# 328. RELEASE FINGERPRINT

Every release must have an immutable fingerprint including:

```text
Git SHA
build ID
schema version
artifact hashes
model versions
```

Owner diagnostics should expose it.

---

# 329. STAGING CERTIFICATION

Before production eligibility verify in staging:

```text
API
web
Telegram
market data
worker
scheduler
paper
demo broker
risk
kill switches
retries
crash recovery
Redis failures
database recovery
```

---

# 330. MARKET-SESSION CERTIFICATION

Asset classes whose behavior depends on market hours must be validated during genuine open sessions.

A weekend test does not certify FX/equity live-market operation.

---

# 331. DEMO EXECUTION CERTIFICATION

Before real-money AUTO eligibility verify actual broker demo behavior:

```text
order submit
fill
partial fill where supported
stop
take profit
partial exit
break-even
manual intervention
reconciliation
broker restart/reconnect
```

---

# 332. REAL-MONEY CANARY REQUIREMENT

Even after demo success, real-money execution should begin with controlled canary limits.

Do not enable unrestricted automation system-wide immediately.

---

# 333. PRODUCTION EXPANSION GATE

Increase live scope only after predefined evidence thresholds.

Possible dimensions:

```text
users
capital
strategies
brokers
asset classes
```

---

# 334. AUDIT BEFORE EXPANSION

Perform adversarial review before each major expansion stage.

Do not rely solely on absence of alerts.

---

# 335. DEFINITION OF DONE

A requirement is **IMPLEMENTED** only when all applicable items are true:

```text
code exists
backend connected
database connected
frontend connected if customer/admin-facing
authorization enforced
validation implemented
error states handled
observability exists
tests exist
tests pass
deployment configuration exists
documentation is current
```

A requirement is **VERIFIED** only when the relevant behavior was actually exercised.

Do not equate:

```text
file exists
```

with:

```text
implemented
```

Do not equate:

```text
implemented
```

with:

```text
verified
```

---

# 336. FORBIDDEN COMPLETION LANGUAGE

Do not say:

```text
done
complete
fully implemented
production ready
verified
```

unless evidence supports the statement.

Instead report exact status.

---

# 337. COMPLETION LEDGER

For every requirement across all SignalRank prompts/specifications maintain:

```text
requirement_id
description
status
implementation
tests
evidence
remaining blocker
```

Allowed statuses:

```text
IMPLEMENTED
VERIFIED
BLOCKED_EXTERNAL
NOT_APPLICABLE
```

At final completion, avoid `DEFERRED` for requirements that are technically implementable now.

If `DEFERRED` remains, justify why it cannot reasonably be completed now.

---

# 338. NO PARTIAL CUSTOMER FEATURES

Do not leave situations such as:

```text
button exists but API absent
API exists but page absent
setting saves but is ignored
backend calculates value but frontend shows hardcoded value
frontend claims live data while using demo data
Telegram performs action differently from web
```

Every feature must be wired end-to-end.

---

# 339. NO ORPHAN BACKEND

If a backend capability is intentionally internal:

document its consumer.

Otherwise connect it or remove it.

---

# 340. NO ORPHAN DATABASE TABLES

New tables must have actual production code paths or clear research/operational consumers.

Do not create schema merely to satisfy the prompt.

---

# 341. NO DUPLICATE SOURCES OF TRUTH

For each domain establish a canonical source:

```text
asset registry
user identity
entitlements
risk limits
signal status
execution status
broker account
strategy version
model version
```

Remove/reconcile conflicting copies.

---

# 342. NO HARDCODED BUSINESS RULES WHEN CONFIGURABLE POLICY IS REQUIRED

Examples:

```text
subscription names
broker limits
strategy limits
risk thresholds
```

should come from their canonical policy/configuration system where appropriate.

---

# 343. CONFIGURATION VALIDATION AT STARTUP

Detect missing/invalid required configuration.

Provide clear diagnostics.

Do not continue into unsafe operation.

---

# 344. USER-MIGRATION SAFETY

If new defaults/settings are introduced for existing users:

create explicit migration/backfill logic.

Do not assume all existing rows contain new values.

---

# 345. API BACKWARD COMPATIBILITY

Where deployed frontend/backend may briefly run different versions:

handle compatibility safely.

Avoid deployment windows where the application becomes unusable.

---

# 346. ZERO-DOWNTIME WHERE PRACTICAL

Use expand/migrate/contract approaches for schema/API changes that could otherwise break active users.

---

# 347. FRONTEND CACHE INVALIDATION

Ensure deployments do not serve mismatched old JS against incompatible APIs.

Use appropriate cache/version behavior.

---

# 348. CUSTOMER-FACING RELEASE SAFETY

When major behavior changes:

surface appropriate release information without overwhelming customers.

Do not silently alter material risk behavior.

---

# 349. CHANGE AUDIT

Important policy/risk changes should record:

```text
old
new
actor/system
reason
timestamp
```

---

# 350. FINAL AUTONOMOUS AUDIT

When all implementation is believed complete, run another repository-wide adversarial audit.

Ask at minimum:

```text
Is anything mocked?

Is anything disconnected?

Is anything only documented but not implemented?

Is anything implemented but unused?

Can a user see a feature they cannot actually use?

Can an API return success without confirmed effect?

Can retries duplicate an order?

Can stale state cause an unsafe execution?

Can a broker timeout cause duplicate execution?

Can a manual user action be overwritten?

Can one user access another user's account data?

Can a subscription change abandon a position?

Can an AI/provider outage silently bypass a gate?

Can a market-data outage produce fake confidence?

Can a research result leak future information?

Can a strategy reset its multiple-testing history?

Can a new strategy reach live too quickly?

Can risk budgets race?

Can a broken worker go unnoticed?

Can staging touch production resources?

Can a bad migration partially deploy?

Can a Redis restart lose financial truth?

Can an admin override leave no audit record?

Can the frontend display stale AUTO status?

Can PAPER be confused with LIVE?

Can the system claim a trade filled before broker confirmation?

Can a feature be marked VERIFIED without being exercised?
```

Fix every material issue that is technically resolvable.

Then repeat the audit once more.

Stop only when the second audit reveals no new material code-level gaps that can presently be fixed.

---

# 351. FINAL CODE SEARCH

Before declaring completion perform searches for:

```text
TODO
FIXME
HACK
pass
NotImplemented
placeholder
mock
dummy
temporary
coming soon
```

and inspect every relevant result.

There must be no unresolved production-path placeholder related to the requested system.

Test fixtures and intentionally unsupported adapters are acceptable only when clearly isolated and documented.

---

# 352. FINAL UI AUDIT

Inspect every customer/admin page at representative:

```text
mobile
tablet
desktop
```

and in:

```text
light
dark
```

modes.

Verify:

```text
content
spacing
alignment
overflow
navigation
loading
empty
error
success
disabled
permissions
real data
live state
```

Do not consider the frontend complete merely because the build passes.

---

# 353. FINAL END-TO-END AUDIT

Exercise complete flows:

```text
registration
authentication
subscription
signal delivery
paper trading
broker connect
AUTO_CONFIRM
AUTO
execution block
execution success
position management
manual intervention
broker outage
reconciliation
risk breach
emergency stop
strategy quarantine
subscription downgrade
logout/relogin
mobile use
```

Use staging/demo/simulator where real-money execution is inappropriate.

---

# 354. FINAL DEPLOYMENT AUDIT

Confirm:

```text
candidate SHA
database migration head
environment isolation
Redis isolation
secrets present
providers configured
health endpoints
readiness
worker heartbeat
scheduler
frontend/API compatibility
```

Do not change production data merely for demonstration.

---

# 355. FINAL SECURITY AUDIT

Run available:

```text
dependency
static
secret
container
authorization
session
API
```

security checks.

Fix material findings.

Do not suppress them simply to finish.

---

# 356. FINAL PERFORMANCE AUDIT

Check critical latency and load paths.

Ensure research/analytics cannot starve:

```text
execution
position management
risk
```

---

# 357. FINAL DATABASE AUDIT

Verify:

```text
constraints
indexes
migrations
foreign keys
retention
backup
restore
```

for newly affected areas.

---

# 358. FINAL DOCUMENTATION

Update:

```text
README
deployment docs
environment examples
architecture
runbooks
broker setup
research lifecycle
risk controls
admin operations
```

only to reflect actual implemented behavior.

Do not document aspirational features as existing.

---

# 359. FINAL OUTPUT FORMAT

At the end provide:

## Candidate

```text
Repository:
Branch:
Commit SHA:
PR:
Migration head:
```

## Implementation

For every major subsystem:

```text
IMPLEMENTED
VERIFIED
BLOCKED_EXTERNAL
NOT_APPLICABLE
```

## Tests

Report:

```text
suite
result
count
failures
```

## External verification still required

Only include items genuinely requiring:

```text
live market hours
real broker/demo availability
real fills
extended soak
external account credentials
legal/regulatory review
```

## Deployment instructions

Exact steps.

## Environment variables

Every required variable, without secrets.

## Migrations

Exact command/order.

## Remaining material gaps

If any remain, state them plainly.

---

# 360. STRICT COMPLETION RULE

Do not intentionally leave technically implementable work incomplete.

Do not stop because:

```text
the task is large
the feature is complex
another subsystem requires modification
the original prompt did not explicitly mention a discovered dependency
```

If the feature is required for correctness, safety, usability, or production integrity:

implement it.

The only acceptable unfinished categories are those requiring something unavailable inside the repository/session, such as:

```text
external credentials
live-market elapsed time
real broker fills
extended staging soak
external approval
legal/regulatory review
third-party outage
```

Code necessary to support those external checks must still be completed beforehand.

---

# 361. DO NOT FABRICATE EXTERNAL COMPLETION

This strict completion rule does NOT permit pretending that external evidence exists.

For example:

```text
24–72 hour soak
real-market session certification
real broker fill
production restore exercise
```

cannot be marked VERIFIED unless they actually happened.

Implement all supporting code and tooling, then mark the evidence:

```text
BLOCKED_EXTERNAL
```

until the real test is performed.

---

# 362. SIGNALRANK FINAL PRODUCT MODEL

The completed platform should behave conceptually as:

```text
                 SIGNALRANK RESEARCH SYSTEM
                           ↓
                 Validated strategy set
                           ↓
                    MARKET ANALYSIS
                           ↓
                    Candidate signal
                           ↓
                  Validation / scoring
                           ↓
                 Canonical valid signal
                           ↓
              Per-user eligibility engine
                           ↓
             ┌─────────────┴─────────────┐
             ↓                           ↓
        Not eligible                  Eligible
                                         ↓
                                  Deliver signal
                                         ↓
                              Execution eligibility
                                         ↓
                 ┌───────────────────────┼──────────────────────┐
                 ↓                       ↓                      ↓
           SIGNALS_ONLY               PAPER                AUTO_CONFIRM
                                                                  ↓
                                                            user confirms
                                                                  ↓
                                                               EXECUTE
                                         ↓
                                       AUTO
                                         ↓
                               broker order intent
                                         ↓
                                  risk reservation
                                         ↓
                                      broker
                                         ↓
                                  reconciliation
                                         ↓
                                  position manager
                                         ↓
                                      outcome
                                         ↓
                           analytics / learning feedback
                                         ↓
                        research / strategy health system
```

All paths share canonical:

```text
identity
assets
signals
risk
entitlements
strategy versions
reason codes
audit history
```

---

# 363. FINAL PRINCIPLE

SignalRankAI must never choose between:

```text
good trading logic
good risk management
good engineering
good security
good UX
```

as though only one matters.

The finished system must combine them.

Customers should experience something simple:

```text
SignalRank finds opportunities.
I choose how I want to participate.
I understand my risk.
I can connect my broker.
I can trade manually.
I can approve each trade.
I can use paper trading.
I can enable automation.
I can stop automation instantly.
I can always understand what happened.
```

Underneath that simple experience, the platform should maintain:

```text
point-in-time data
statistically honest research
versioned models
robust strategies
portfolio-aware risk
broker reconciliation
idempotent execution
continuous health monitoring
security
auditability
failure recovery
```

Do not sacrifice internal rigor for UI simplicity.

Do not sacrifice UI simplicity for internal sophistication.

The final product should provide both.