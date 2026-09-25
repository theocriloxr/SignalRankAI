# Multi-Account Execution Safety Architecture — 2026-09-25

This document is the implementation companion to
`docs/specs/2026-09-25/04-multi-user-account-addendum.txt`.

## Non-negotiable boundaries

SignalRank intelligence may be shared across users and accounts, but account
identity, credentials, permission, risk policy, reconciliation state,
execution claims, execution evidence, ledger entries and performance are
account-scoped.

A broker connection is never execution permission. A trading-account policy is
never global execution permission. A PROP certification is never permission to
bypass SignalRank's global execution gate. Every layer must independently pass.

Normal account operations use the tuple:

`canonical users.id + immutable broker_connections.connection_id`

Telegram execution account selection uses a short-lived opaque server-side
token bound to the Telegram identity, canonical user, signal, connection,
provider and policy version. Raw broker account IDs are not trusted from
callback data.

## Account policy

Every new broker connection receives a conservative policy immediately.
Material policy edits increment `policy_version`, clear prior PROP
certification and disable broker execution.

The policy may constrain:

- account mode: PAPER, DEMO, LIVE_PERSONAL or PROP;
- permission: read-only, signals-only, paper-only, manual, assisted or auto;
- risk per trade;
- daily, weekly and total drawdown;
- open positions and leverage;
- spread and expected slippage;
- minimum confidence and reward:risk;
- instruments, asset classes and strategies;
- account-local trading windows;
- high-impact-news and weekend holding;
- external PROP limits and a safety buffer.

### Configuration-driven PROP hard rules

Firm-specific hard rules live in the versioned `external_rules.hard_rules`
configuration. Supported rule types are validated by the deterministic account
policy engine. Unknown rule types fail closed and cannot enter a certifiable
policy.

Current generic rule types include trailing drawdown, max order size with an
explicit unit, max notional/equity, forbidden execution modes, restricted
instruments/asset classes and max open positions.

Every rejection contains the stable rule ID, for example:

`prop_rule:lot-cap:max_order_size`

PROP certification is a separate owner/admin operation. Authority is resolved
server-side from current operator configuration; a user cannot self-certify by
supplying a role string. Certification binds an immutable policy version and
stores certifier provenance plus an audit event.

## Canonical account ledger

`trading_account_ledger_entries` is the persistent broker-account evidence
ledger. It is scoped to `user_id + connection_id`, is idempotent on
`connection_id + provider + source_event_id`, and PostgreSQL blocks UPDATE or
DELETE through an immutability trigger.

Supported evidence includes deposits, withdrawals, balance/equity/margin
snapshots, realized/unrealized P/L, commissions, funding, swap, fees, orders,
fills, position snapshots, adjustments and reconciliation corrections.

Only provider-proven values are recorded. Missing deposits, withdrawals,
funding, swaps or fees are not inferred. Ledger metadata is scrubbed for
passwords, API keys, tokens and other credential-like fields before
persistence.

Current provider wiring:

- MT4/MT5: account snapshots and broker-acknowledged order evidence.
- Bybit: account snapshots, broker-acknowledged orders, open-position
  snapshots, closed realized P/L and provider-reported entry/exit fees.
- MT4/MT5 closed-deal/P&L ingestion remains pending an authoritative provider
  history/deal adapter; no synthetic closure evidence is created.

## Reconciliation and freezes

Reconciliation state is stored per account. A transient RECONCILING state
blocks the current execution decision. DEGRADED, FROZEN, AUTH_EXPIRED and
DISCONNECTED states disable account execution and create durable safety audit
events. System/reconciliation freezes cannot be cleared through the normal
user-unfreeze path.

## Performance composition

Broker performance is composed per connection. DEMO, LIVE_PERSONAL and PROP
accounts are not combined into the web headline. Mixed provider/user
aggregates may exist only as explicitly labelled diagnostics accompanied by
single-account composition.

Paper performance remains in the paper ledger and is not mixed with broker
account performance.

## Decision provenance

Every account execution decision records:

- user and immutable connection;
- signal and execution mode;
- account mode and policy version;
- allow/block status and exact reason codes;
- release SHA and execution-engine version;
- model/strategy versions when supplied;
- market/risk/request snapshots;
- trace ID.

This provenance contains no broker credentials.

## Runtime and release posture

Migration `0043_account_execution_policy` is the schema head for this branch.
Runtime schema admission and staging proof require the account policy,
reconciliation, account ledger, decision-provenance tables and account-scoped
MT5/provider execution columns.

Real-money execution remains fail-closed until the separate release,
schema/runtime, provider, reconciliation and owner-activation gates are
certified. Implementing this architecture does not itself activate live
trading.

## Verification state

The branch has deterministic tests for account-policy rules, PROP rule
evaluation, object-level authorization, opaque Telegram account selection,
schema admission, account-ledger validation/redaction, web parity and
per-account performance composition.

An isolated zero-secret Railway clean-room service is used for compile/targeted
test verification. Staging database migration/runtime evidence and live broker
provider certification are separate gates and are not claimed by this document.
