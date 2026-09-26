# SignalRankAI — Remaining External Completion Gates

Date: 2026-09-26  
Current certified staging schema: `0045_mt5_credential_retirement`

This file lists only work that cannot be truthfully completed by repository
changes alone. Source-code, deterministic tests, staging schema migration,
credential-retirement proof, and decomposed role admission are already covered
by the current release evidence.

## 1. Provider and venue certification

Declared providers/venues are not considered live-certified merely because an
adapter or capability manifest exists.

Required external evidence, as applicable:

- provider/sandbox/testnet credentials supplied through staging secrets;
- required paid plan, exchange entitlement, redistribution permission and
  regional availability;
- live request/response smoke with provider timestamps and freshness;
- rate-limit/circuit-breaker behavior;
- symbol/instrument mapping proof;
- authoritative bid/ask or execution acknowledgement where the venue is used
  for trading;
- reconciliation proof after restart/disconnect;
- no credential values in evidence artifacts.

Repository tooling:

- `scripts/certify_providers.py`
- `scripts/deployment_diagnostics.py`
- `docs/providers/PROVIDER_CAPABILITY_MATRIX.md`
- `docs/PROVIDER_ENVIRONMENT_CONTRACT.md`

Provider flags remain disabled or uncertified until their own evidence passes.

## 2. Broker demo/canary/live-money certification

Before owner-authorized live execution:

1. connect one explicitly identified DEMO account;
2. prove account policy, broker identity, quote freshness and reconciliation;
3. execute bounded demo orders through the canonical router;
4. prove broker acknowledgement, canonical execution lifecycle, account ledger,
   realized P/L/fees, restart reconciliation and idempotency;
5. complete a documented demo certification report;
6. use a tightly capped canary account before any wider live rollout;
7. for PROP/funded accounts, independently validate the exact firm/product rule
   set and certify the immutable policy version;
8. keep LLMs advisory: no model may bypass deterministic risk limits.

Current staging certification does not activate real execution.

## 3. 100,000-user infrastructure certification

Source code can provide bounded queues, decomposed roles, backpressure and scale
profiles, but a 100k-user claim requires representative infrastructure.

Required evidence:

- staged load profiles up to the target concurrency/arrival rate;
- p50/p95/p99 latency and error rate by HTTP, Telegram, DB and queue class;
- Postgres connection/admission behavior;
- Redis stream/queue backlog and reclaim behavior;
- engine scan cadence under load;
- delivery throughput and RetryAfter behavior;
- analytics shedding while foreground work remains healthy;
- memory/CPU/network saturation boundaries;
- restart/failover recovery and duplicate-event checks;
- cost estimate for the certified topology.

No 100k capacity claim is permitted until that test is run against
representative infrastructure.

## 4. Soak, failover, backup and restore

Before production promotion:

- at least 24 hours of clean staging soak on the intended release;
- database backup/snapshot evidence;
- restore drill to an isolated target;
- Redis loss/restart exercise;
- provider disconnect/reconnect exercise;
- Telegram/webhook recovery exercise;
- one application-role restart at a time with ownership preserved;
- incident/rollback rehearsal and retained evidence.

## 5. Payments, email and identity providers

Where these product paths are enabled:

- Paystack test/live keys owned by the business;
- verified Paystack webhook and real test-mode checkout/webhook/reconciliation;
- SMTP/transactional-email credentials plus SPF/DKIM/DMARC;
- Google/Apple OAuth credentials where offered;
- institutional SSO metadata where offered.

Transfers, payouts and public payment activation remain independent release
gates.

## 6. Copy trading / marketplace / publisher trust

The roadmap may contain copy trading, strategy marketplace, strategy bots and
smart-terminal concepts, but production activation requires more than code:

- publisher identity and ownership;
- explicit follower consent and revocation;
- suitability/risk disclosures;
- per-follower risk ceilings independent of publisher settings;
- immutable publisher/follower execution provenance;
- reconciliation and partial-failure behavior;
- conflict/abuse/fraud controls;
- transparent performance methodology;
- jurisdiction/legal approval.

These features remain disabled until the separate trust, legal and runtime
certification programme is complete.

## 7. Supply-chain signing

The repository now generates and self-verifies a deterministic CycloneDX SBOM
and release-provenance manifest via
`scripts/generate_release_provenance.py`.

Still external:

- organization-controlled signing identity/key;
- signing in the trusted build/release environment;
- retention/verification policy for the signed digest or attestation.

No signing key is generated, embedded or guessed by source code.

## 8. Mobile/store distribution

Public mobile release still requires:

- Expo/EAS ownership;
- APNs/FCM credentials;
- Apple/Google developer accounts;
- signing certificates/profiles;
- privacy declarations and store metadata;
- review/submission/publication.

## 9. Legal/compliance/business approval

External review is required for the intended jurisdictions covering:

- financial promotions and signal marketing;
- subscriptions/refunds/tax terms;
- copy trading and automated execution;
- broker linking and portfolio functionality;
- privacy, retention, deletion, cookies and marketing consent;
- provider/exchange terms and redistribution;
- public performance claims.

## 10. Performance evidence

A source tree cannot prove a fixed win rate.

Any public or live-money performance claim must use:

- point-in-time leakage-free data;
- purged/walk-forward evaluation;
- realistic spread, commission, funding, slippage and latency;
- immutable signal/delivery/outcome/execution lineage;
- adequate sample size and regime coverage;
- shadow/paper/demo evidence;
- coverage alongside win rate, expectancy, drawdown and uncertainty.

SignalRankAI therefore makes no guaranteed 60%, 70%, 75% or other fixed win-rate
claim.

## Current safe boundary

As of 2026-09-26:

- staging database is certified at Alembic `0045_mt5_credential_retirement`;
- staging frontdoor, engine, delivery and analytics roles pass release/schema
  admission on the decomposed topology;
- broker legacy-secret inventory is clean in certified staging;
- real execution, copy execution, live broker-account execution, mainnet
  Hyperliquid, real payouts and Paystack transfers remain disabled;
- production remains a separate controlled rollout and was not promoted merely
  by staging certification.
