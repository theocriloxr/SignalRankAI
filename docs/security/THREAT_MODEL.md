# THREAT_MODEL — SignalRankAI

Last updated: 2026-09-26  
Scope: public web/PWA and Telegram frontdoor, account identity and sessions,
payments, signal generation, delivery/outcomes, market-data providers, broker
connections, execution admission, account ledgers, analytics/ML, Redis/Postgres,
Railway runtime roles, and operator/admin tooling.

This document models the system that actually exists at Alembic head
`0045_mt5_credential_retirement`. It does **not** treat disabled roadmap
features or unverified provider sandboxes as deployed security controls.

## 1. Security objectives

SignalRankAI must preserve five properties:

1. **Account isolation.** A user can never read, configure, freeze, reconcile,
   execute through, or inspect ledger evidence for another user's broker
   connection.
2. **Execution safety.** A connected broker account is not execution
   permission. Real execution must pass global activation, account ownership,
   connection health, immutable/versioned policy, risk, reconciliation,
   provider-freshness, and idempotency gates.
3. **Credential confidentiality and binding.** Broker credentials must not be
   stored or returned as plaintext and must not be replayable against a
   different user, connection, provider, connector, or credential revision.
4. **Financial truth.** Broker/account evidence and financial corrections must
   be traceable, account-scoped, idempotent, and append-only where required.
5. **Recoverable operation.** Provider, database, Redis, Telegram, AI, or broker
   failures must degrade safely rather than silently enabling riskier behavior.

## 2. Protected assets

High-value assets include:

- broker/API credentials and provider tokens;
- Telegram bot and webhook credentials;
- Paystack secrets and payment-event integrity;
- account identity, sessions, MFA secrets, recovery codes, and device state;
- canonical trading-account policy and PROP certification state;
- broker reconciliation state and execution permission;
- financial/account ledger evidence, execution decisions, outcomes and P/L;
- model artifacts, strategy versions and decision provenance;
- owner/admin authority and audit trails;
- service availability and database/Redis capacity.

## 3. Trust boundaries

### TB-01 — Internet → frontdoor

The public HTTP/Telegram service is untrusted ingress. The staging decomposed
frontdoor owns HTTP, Telegram and scheduler responsibilities, but does not own
the signal engine or delivery worker. Runtime ownership is enforced by
`runtime/roles.py`; staging evidence proves `engine=false` and `worker=false`
for the frontdoor.

### TB-02 — User session → canonical identity

Web/mobile operations resolve a canonical `users.id`. Password and magic-link
authentication can require TOTP MFA. TOTP codes use replay prevention,
recovery codes are one-time and hash-stored, refresh tokens rotate, and reuse
of a rotated refresh token revokes the session family and records a critical
security event.

### TB-03 — Canonical user → broker connection

All normal broker-account object access is scoped by both canonical
`users.id` and immutable `broker_connections.connection_id`. Object-level
authorization is tested across policy, safety freeze, execution toggle,
execution evidence, account ledger, and Telegram account selection.

Telegram execution selection uses a short-lived opaque server-bound token
rather than trusting a raw broker account ID in callback data. Consumption
revalidates owner, signal, connection and policy version.

### TB-04 — Application → broker credential material

New broker credential writes use a versioned context-bound envelope. The
credential cryptographic context binds user ID, connection ID, provider,
connector and credential revision. The keyring supports key rotation: old keys
may remain readable while new writes use the configured active key. Missing
key material fails closed.

Migration `0044_broker_credential_envelope` adds credential format/version,
key ID, revision and rotation metadata without decrypting legacy ciphertext.
Migration `0045_mt5_credential_retirement` retires duplicate MT5 password
ciphertext once an equivalent canonical envelope exists and makes the
compatibility password column nullable. Legacy Fernet values remain
compatibility/read-only migration material; new connection writes reject raw
legacy ciphertext until it is explicitly rotated. Public connection responses
never return ciphertext or credential key IDs. The certified staging inventory
after 0045 reports zero canonical legacy rows and zero MT5 legacy, duplicate or
unmigrated secret rows.

### TB-05 — Frontdoor/payment provider → financial entitlement

Paystack webhook signatures are verified against the raw request body.
Financial effects use idempotency/durable receipt patterns so retries cannot
silently create duplicate entitlement effects. Payment/public-transfer
capabilities remain separately feature-gated.

### TB-06 — Engine → market data / AI

External market/news/provider input is untrusted evidence. Market data carries
provider provenance and freshness requirements. Execution quotes cannot be
silently substituted with stale candle data.

OpenAI/Gemini may review, explain or enrich a signal, but LLM output is not a
risk authority and cannot bypass deterministic execution/risk gates or invent
privileged order permission.

### TB-07 — Engine/frontdoor/worker/analytics → Postgres/Redis

Runtime roles use explicit ownership and bounded database admission. Queues,
delivery/outcome work and background persistence use bounded concurrency,
backoff and/or requeue semantics. The frontdoor does not own engine/worker
loops; the engine does not own outcome reconciliation; analytics owns its
learning/discovery jobs.

### TB-08 — Trading account → execution / financial ledger

Every execution decision is account-scoped and stores policy/version,
allow/block reasons and provenance. Broker-authoritative account evidence is
stored in `trading_account_ledger_entries`, with provider-event idempotency
and a PostgreSQL trigger blocking UPDATE/DELETE. Corrections reference the
original account-owned entry rather than mutating history.

## 4. Mandatory security invariants

The following are release-blocking invariants:

- `GLOBAL_EXECUTION_KILL_SWITCH` can disable execution regardless of AI or
  strategy output.
- A normal account cannot execute unless its exact account policy and
  connection permit it.
- A PROP policy cannot self-certify; certification is owner/admin-authorized,
  version-bound and audited.
- Material account-policy edits invalidate prior certification and disable
  execution.
- Reconciliation states such as DEGRADED/FROZEN/AUTH_EXPIRED/DISCONNECTED
  disable execution for that account.
- Broker credentials cannot be returned in public connection payloads.
- Missing credential key material fails closed.
- Unknown PROP hard-rule types fail closed rather than being ignored.
- Money/quantity/P&L persistence uses decimal/numeric representations at
  financial boundaries.
- Append-only ledger rows cannot be updated or deleted through normal SQL.
- Webhook replay/idempotency controls remain enabled for financial effects.
- Real-money activation and payout switches are independent of ordinary
  feature availability.
- Staging keeps real execution, copy trading, broker live-account execution,
  Hyperliquid mainnet, real payouts and Paystack transfers disabled during
  certification.

## 5. Threat catalogue

| ID | Threat | Likelihood | Impact | Controls / evidence | Residual status |
|---|---|---:|---:|---|---|
| TM-01 | Secret/API-key disclosure through logs or API responses | M | H | secret redaction, public broker response strips ciphertext/key ID, startup redaction tests | Mitigated; continue log scanning |
| TM-02 | Account takeover | M | H | password/magic-link flows, TOTP MFA, one-time hashed recovery codes, device/session revocation | Mitigated; phishing remains external risk |
| TM-03 | Session-token replay | M | H | rotating refresh tokens, session-family revocation on reuse, security event on reuse | Mitigated |
| TM-04 | MFA code replay | L | H | TOTP last-used-step replay prevention; one-time recovery codes | Mitigated |
| TM-05 | BOLA/IDOR across broker accounts | M | H | canonical user + connection ID queries; dedicated BOLA tests; opaque Telegram selection token | Mitigated |
| TM-06 | Broker credential ciphertext replay onto another account | M | H | context-bound envelope includes user/connection/provider/connector/revision; binding mismatch rejected | Mitigated |
| TM-07 | Broker credential key rotation breaks access or silently downgrades security | M | H | active key ID + keyring; old-key read/new-key write; missing keys fail closed; legacy writes rejected | Mitigated with operational rotation discipline |
| TM-08 | Legacy ciphertext remains indefinitely | M | M | `legacy_fernet` explicitly labelled by 0044; new writes require envelope; 0045 retires duplicate MT5 password storage; counts-only staging inventory proves zero legacy/unmigrated rows | Mitigated in certified staging; repeat inventory before each live-money promotion |
| TM-09 | Forged Paystack webhook | M | H | raw-body signature verification; durable/idempotent receipt processing | Mitigated |
| TM-10 | Duplicate/replayed financial event | M | H | idempotency keys, durable inbox/receipt semantics, unique constraints | Mitigated |
| TM-11 | Ledger tampering / history rewrite | L | H | account-scoped append-only ledger + DB mutation trigger + compensating correction reference | Mitigated |
| TM-12 | Wrong-account execution | M | H | explicit connection selection, account-owned execution claims/evidence, policy version binding, reconciliation | Mitigated |
| TM-13 | PROP-firm rule bypass | M | H | certified immutable policy version, owner/admin-only certification, generic deterministic hard-rule engine, exact rule IDs | Mitigated for configured rules; external firm-rule correctness still requires verification |
| TM-14 | Stale/spread-deviant broker quote | M | H | provider timestamp freshness, spread/slippage caps, fail-closed quote admission | Mitigated |
| TM-15 | Market-data poisoning or provider degradation | M | H | provenance/freshness, typed failures, provider fallback/circuit breakers, session calendars | Partial; correlated upstream failures remain possible |
| TM-16 | Prompt injection / malicious news content influences execution | M | H | LLM is advisory/enrichment only; deterministic risk/execution boundaries remain authoritative | Mitigated at execution boundary |
| TM-17 | Model/strategy promotes itself after short profitable run | M | H | champion/challenger and promotion-governance foundations; live-money activation separate | Partial; lifecycle evidence still requires ongoing governance |
| TM-18 | Redis/database outage causes unsafe fallback | M | H | fail-closed execution/account gates, bounded DB admission, durable Postgres evidence, idempotency | Mitigated; availability impact remains |
| TM-19 | Queue poisoning or retry storm | M | M | per-item isolation, bounded queues, DLQ/requeue/backoff, role ownership | Mitigated |
| TM-20 | Resource exhaustion / connection-pool starvation | M | H | decomposed roles, foreground reserve, bounded analytics/background lanes, locked runtime pool limits | Mitigated at certified staging scale; 100k-user certification still external |
| TM-21 | Compromised dependency/supply chain | L | H | `requirements.lock`, locked `--no-deps` install + `pip check`, deterministic CycloneDX SBOM, release-provenance hashes bound to exact commit/branch/Alembic head, build + clean-room verification | Mitigated for deterministic provenance; external artifact signing/key custody remains separate |
| TM-22 | Operator/admin abuse | L/M | H | live owner/admin allowlists, privileged certification boundary, audit events, execution/payout master switches | Partial; human/key compromise remains |
| TM-23 | Cross-role duplicate work after deployment | M | M/H | explicit decomposed runtime ownership + role-specific rollout paths; live staging role evidence | Mitigated |
| TM-24 | Cross-environment contamination | M | H | isolated staging/production environments and schema gates; production untouched during 0044 staging certification | Mitigated; never share operational DB state between environments |
| TM-25 | Copy-trading/marketplace abuse or fraudulent publisher | M | H | feature remains disabled; no production certification claim | Blocked/disabled until separate trust/suitability controls exist |
| TM-26 | Real-money loss from unverified broker behavior | M | H | staging kill switch + real-execution flags off; per-account policy/reconciliation/ledger | Blocked until demo/canary/live-provider certification |
| TM-27 | Availability attack on public ingress | M | M/H | bounded webhook queue, fast ACK, rate/resource controls and decomposed frontdoor | Partial; external DDoS/WAF capacity depends on platform controls |

## 6. Broker credential lifecycle

1. A broker connection receives an immutable `connection_id`.
2. New credential material is encrypted with the active broker credential key
   and bound to that account context.
3. The database stores ciphertext plus non-secret envelope metadata; it does not
   store raw broker credentials.
4. Public connection serializers expose only safe state such as
   `credential_encrypted`, format/version/revision and rotation time; they do
   not expose ciphertext or key ID.
5. Key rotation can keep old key material temporarily available for reads while
   new envelopes use the active key.
6. Legacy Fernet rows are explicitly marked `legacy_fernet` and cannot be
   imported as new raw ciphertext. They must be rotated into the canonical
   envelope before relying on them for live-money certification.
7. Removing a required key before dependent envelopes are rotated is a
   fail-closed operational error, not permission to fall back to plaintext.

## 7. Authentication and session lifecycle

Implemented controls include:

- email verification and password reset;
- magic-link authentication;
- TOTP MFA;
- TOTP replay prevention using the last accepted time step;
- one-time recovery codes stored as hashes;
- short-lived access token + rotating refresh-token sessions;
- session-family revocation when refresh-token reuse is detected;
- per-device/session revocation and logout-all support;
- security-event persistence for high-risk session anomalies.

MFA reduces account-takeover risk but does not protect a compromised endpoint,
mailbox, authenticator device, browser session, or administrator account by
itself.

## 8. Execution-specific abuse cases

Execution safety is intentionally layered. An attacker or bug must not obtain a
trade merely by toggling one account flag. A broker submission must survive the
relevant chain of:

- canonical user/account ownership;
- account classification;
- trade-only broker permissions;
- connection health;
- account execution enablement;
- global financial activation / kill-switch state;
- exact account-policy version;
- PROP certification when applicable;
- loss/drawdown/leverage/position/spread/slippage/confidence/R:R rules;
- strategy/instrument/time-window/news/weekend rules;
- fresh broker quote and reconciliation state;
- idempotent execution claim;
- provider acknowledgement;
- immutable/account-scoped evidence.

LLM output is never part of the authorization chain.

## 9. Deployment and environment threats

Staging certification uses a decomposed frontdoor, engine, delivery and
analytics topology. Every long-lived role must prove release identity and the
current Alembic schema before business work begins.

For the 2026-09-26 staging certification:

- database head is `0045_mt5_credential_retirement`;
- migration/schema/runtime proof passed before role rollout;
- counts-only broker credential inventory reports zero legacy, duplicate and
  unmigrated broker secret rows;
- each role passed the locked Docker build gate;
- role-specific rollout paths prevented unrelated role restarts;
- real execution and payout switches remained off;
- production services/database were not migrated or activated.

See `docs/evidence/STAGING_0045_CREDENTIAL_RETIREMENT_20260926.md`.

## 10. Residual risks and blocked certification

The following remain deliberately open rather than being described as
complete:

- provider-specific live/sandbox certification for every declared venue;
- re-running the counts-only credential inventory immediately before any
  live-money promotion and rotating any legacy row if one ever reappears;
- 100k-user infrastructure load certification;
- external cryptographic signing/attestation of the deterministic SBOM/provenance digest using organization-controlled signing keys;
- external prop-firm rule validation for each funded-account product;
- end-to-end Telegram/provider/broker tests that require external sandbox
  credentials;
- copy-trading marketplace/publisher trust and suitability controls;
- demo/canary broker certification before any owner-authorized live-money
  activation.

## 11. Verification sources

Key deterministic evidence includes:

- `tests/test_broker_account_bola_idor.py`
- `tests/test_broker_credential_envelope.py`
- `tests/test_multi_account_prop_policy.py`
- `tests/test_trading_account_ledger.py`
- `tests/test_auth_fail_closed_boundaries.py`
- `tests/test_quiescent_role_certification.py`
- `tests/test_final_cross_channel_parity_20260925.py`
- `services/platform/identity.py`
- `services/broker_credentials.py`
- `services/broker_connections.py`
- `services/account_policies.py`
- `scripts/assert_database_schema.py`
- `scripts/verify_0044_release_chain.py`
- `scripts/verify_0045_release_chain.py`
- `scripts/broker_credential_inventory.py`
- `docs/evidence/STAGING_0045_CREDENTIAL_RETIREMENT_20260926.md`
- `scripts/schema_audit.py`
- `scripts/generate_release_provenance.py`
- `tests/test_release_provenance.py`

A threat marked “mitigated” means the documented control exists and has the
listed deterministic evidence. It does not mean the threat is impossible or
that external provider/infrastructure certification has occurred.
