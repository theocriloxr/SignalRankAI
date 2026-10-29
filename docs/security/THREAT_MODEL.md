# THREAT_MODEL — SignalRankAI

Last updated: 2026-10-29 (section 12 extends the model to `0057`; sections 1–11 are the 2026-09-26 baseline)  
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

## 12. Revision 2026-10-29 — surfaces added since `0045`

Sections 1–11 describe the system at `0045_mt5_credential_retirement` and are
kept unchanged. This section extends the model to the code on
`feat/frontend-rebuild-and-stage1-hardening` at schema head
`0057_expectancy_shadow_index`. Production still runs `9865a3d1` at `0053`,
so nothing below is a statement about the deployed system. Every control was
read in the code during this revision and has the cited tests. "Fixed" means
it was changed in this revision.

### 12.1 New or changed surfaces

| Surface | Entry point | Owner of authority |
|---|---|---|
| Rebuilt web frontend (Next.js 16) and its API proxy | browser → `frontend/src/proxy.ts`, `frontend/src/lib/platform-proxy.ts` | backend platform API |
| Developer API keys and outbound webhooks | `/api/v1/platform/api-keys`, `/webhooks`; `services/platform/webhooks.py` | account owner (plan feature) |
| Privacy export and deletion request | `/account/export`, `/account/deletion-request` | account owner; support review |
| Telegram ↔ web account merges | link flow; `/operator/account-merges`; `services/platform/account_merge.py` | owner (apply), owner/admin (preview) |
| Owner web controls | `/operator/kill-switch/scoped`, `/operator/ai-spend`; `frontend/src/components/OwnerControls.tsx` | owner |
| AI usage and cost ledger | `services/ai_cost_ledger.py`, migration `0056` | system (budgets), owner (view) |
| Telegram `/watchlist`, `/journal` and other account commands | bot command wrapper `_audit_handler`; `signalrank_telegram/workspace_commands.py` | account owner |
| Engine liveness and owner alerts | `engine/stall_watchdog.py`, `observability/owner_alerts.py` | system |

### 12.2 New trust boundaries

- **TB-09 — Browser → web proxy → platform API.** The proxy forwards only `/api/v1/platform/*` to one configured backend origin. It refuses encoded path separators and does not follow redirects. Responses are marked `no-store`. Pages carry a nonce-based Content-Security-Policy with `frame-ancestors 'none'`. Session cookies are `HttpOnly` and `SameSite=Lax`, and cookie-authenticated writes need the double-submit CSRF token (`web/app.py` `platform_csrf_middleware`).
- **TB-10 — Platform → customer webhook endpoints.** Customers choose the destination URL, so every delivery is a server-side request to an address an outsider controls.
- **TB-11 — Telegram chat context.** A command's reply goes to the chat it came from. Groups and channels are shared spaces, unlike a private chat.
- **TB-12 — Owner web controls.** Changes need owner authority, explicit confirmation and a recent sign-in. Kill-switch changes are audited, and a merge applies in one transaction.
- **TB-13 — One identity across channels.** Web and Telegram read and write the same canonical rows (watchlists, journal, paper, preferences). A reviewed merge moves rows from an archived account to the kept one.

### 12.3 Threat catalogue additions

| ID | Threat | L | I | Controls / evidence | Status |
|---|---|---:|---:|---|---|
| TM-28 | Server-side request forgery through webhook destinations, including DNS rebinding between validation and connection | M | H | HTTPS only, no credentials in URLs, port allowlist, optional host allowlist, no redirects, non-global addresses refused, and delivery connects to the validated address with TLS verified against the real hostname; no connection reuse across customers. `tests/test_webhook_ssrf_pinning_20261029.py`, `tests/test_unified_platform_webhooks.py` | **Fixed** (pinning, `is_global`, no keep-alive); mitigated |
| TM-29 | Password guessing that sidesteps IP-keyed limits | M | H | scrypt hashes; per-account failure limit (10 per 15 min, counted for unknown emails too); TOTP challenges limited to 5 attempts each. `tests/test_login_account_throttle_20261029.py` | **Fixed** (per-account limit); mitigated |
| TM-30 | Inbox flooding through unauthenticated sign-in-link and reset requests | M | M | per-account cap of 5 emails per hour per purpose, with the same reply for accepted, capped and unknown addresses. `tests/test_account_email_budget_20261029.py` | **Fixed**; mitigated |
| TM-31 | Account or operations data shown in a Telegram group | M | M/H | the command wrapper refuses all but eight public-information commands outside private chats; `/watchlist` and `/journal` repeat the check. `tests/test_telegram_private_chat_scope_20261029.py`, `tests/test_telegram_workspace_commands_20261029.py` | **Fixed**; mitigated |
| TM-32 | Cross-site request forgery against cookie sessions | M | H | double-submit CSRF token on every cookie-authenticated write; `SameSite=Lax`; a fixed-origin proxy | Mitigated |
| TM-33 | Proxy misuse (open proxy, path traversal, header injection) | L | H | fixed destination, path prefix check, encoded-separator rejection, header allowlist, hop-by-hop headers stripped, 30 s timeout. `frontend/scripts/platform-proxy.test.mjs` | Mitigated |
| TM-34 | Script injection in the web app | L | H | nonce-based CSP with `strict-dynamic`; React escaping; no `dangerouslySetInnerHTML` on user content | Mitigated |
| TM-35 | One account reading or changing another's watchlists, journal or export | M | H | every query is scoped by canonical user id in shared services; short journal ids match only the caller's entries. `tests/test_multi_user_isolation_postgres_20261024.py`, `tests/test_privacy_requests_20261024.py`, `tests/test_telegram_workspace_commands_20261029.py` | Mitigated |
| TM-36 | Wrong or partial account merge (data loss, or data moved to the wrong person) | L | H | owner-only apply, repeat-the-id confirmation, recent sign-in, one transaction, rows that would collide stay on the archived account, credentials and sessions never move. `tests/test_account_merge_postgres_20261027.py` | Mitigated; production data not exercised |
| TM-37 | Kill-switch tampering or an unreadable switch store enabling execution | L | H | owner-only, confirmed and audited changes; an unreadable store blocks execution; switches only add blocks. `tests/test_scoped_kill_switch_20261027.py` | Mitigated |
| TM-38 | Runaway AI spend (denial of wallet) or prompt-injected AI text | M | M | append-only ledger, budgets that refuse calls once exhausted, deduplicated alerts; AI output stays advisory (TM-16). `tests/test_ai_cost_ledger_budgets_20261028.py` | Mitigated once the owner sets budgets |
| TM-39 | Silent engine stall (no signals, no alarm) | M | H | bounded database calls in the loop, a stall watchdog that exits a dedicated engine, owner alerts for stalled or silent engines and old queue items. `tests/test_engine_db_call_timeouts_20261029.py`, `tests/test_engine_stall_watchdog_20261028.py`, `tests/test_owner_alerts_20261029.py` | Mitigated; not deployed |
| TM-40 | Secrets exposed in the public repository | L | H | no secret patterns found in tracked files on 29 Oct (false positives only); secrets live in Railway variables; logs and owner alerts carry no credentials | Mitigated; keep scanning before every push |
| TM-41 | Known-vulnerable dependencies | M | M/H | 29 Oct: `pip-audit` on `requirements.lock` found 0 known vulnerabilities in 135 packages; `npm audit --omit=dev` found 0 | Mitigated at that date; repeat before each promotion |

### 12.4 Open items (not fixed in this revision)

- **Forwarded-address trust.** *Resolved later on 29 Oct; see 12.6.*
- **Webhook response text.** Delivery stores up to 500 characters of the receiver's reply. It is not exposed to users today; keep it that way, or redact it before exposing.
- **Owner Telegram menu.** *Fixed later on 29 Oct:* the owner menu keeps every operator command (98 of 100). This was usability, not access control.
- **Everything in section 10**, plus: no staging environment, no exercised provider/broker/payment sandboxes, and GitHub Actions currently unavailable, so all evidence in this section is local.

### 12.5 How this revision was verified

- Local only: Windows 11, Python 3.13.7, an owned PostgreSQL 17 test cluster migrated to `0057`. Not CI, staging or production.
- New tests: 17 across the four fixes, 5 of them on real PostgreSQL. 598 related tests pass.
- The TLS claim in TM-28 was checked directly: a certificate valid only for `127.0.0.1` is refused when a pinned request names another host.

### 12.6 Follow-up, 29 October 2026 — client address trust

| ID | Threat | L | I | Controls / evidence | Status |
|---|---|---:|---:|---|---|
| TM-42 | A client chooses the address used for rate limits, security events or the Paystack IP allowlist | M | M | `core/client_ip.py` trusts, in order: an address signed by our web proxy (HMAC with a shared secret, 5-minute window), then `X-Real-IP` on Railway (`TRUSTED_CLIENT_IP_HEADER` to override), then the socket peer; the first `X-Forwarded-For` value is never used. The web proxy no longer forwards browser-supplied forwarding headers. `tests/test_client_ip_trust_20261029.py`, `frontend/scripts/client-address.test.mjs` | **Fixed**; mitigated |

- **Evidence for the trusted header.** Railway's public networking specification says its edge sets `X-Real-IP` to the client's remote address and does not mention setting `X-Forwarded-For`. The production domain resolves directly to Railway's edge, with no CDN in front. That the edge *replaces* a client-supplied `X-Real-IP` comes from the documentation; it was not observed, because production cannot be inspected without a deployment.
- **Post-deployment check.** Signed in as the owner, open `/api/v1/platform/operator/request-identity`. `client_ip` must be your public address, with source `x-real-ip` (direct) or `signed_proxy` (through the web app). Repeat with a forged `X-Forwarded-For` or `X-Real-IP` request header: the result must not change.
- **Web proxy hop.** If the web app reaches the API through the public edge rather than Railway's private network, set the same `SIGNALRANK_CLIENT_IP_SECRET` (32 or more random characters) on both services. Without it, every web user would share the web server's address for rate limiting.

