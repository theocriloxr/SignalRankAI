# SignalRankAI — Remaining External Completion Gates

Date: 2026-09-26  
Current certified staging schema: `0045_mt5_credential_retirement`

This file lists only work that cannot be truthfully completed by repository
changes alone. Source-code, deterministic tests, staging schema migration,
credential-retirement proof, and decomposed role admission are already covered
by the current release evidence.

## 2026-09-27 executable preflight refresh

Staging deployment `3a95addd-510d-47d2-acd8-f2257f529ea4` executed
`scripts/external_blocker_preflight.py` against the current external activation
contract. No credential values were printed and every check reported
`activation_performed=false`.

- FMP: BLOCKED on entitlement, live-market-data certification and
  redistribution-rights evidence.
- Alpha Vantage: BLOCKED on entitlement, request-budget, live-market-data
  certification and redistribution-rights evidence.
- OANDA: BLOCKED on missing provider secret, missing `OANDA_ACCOUNT_ID`, and
  missing intended-environment / market-data / regional certification.
- FRED: BLOCKED on missing provider secret and missing attribution, live-macro
  and point-in-time/vintage certification.
- 100k / 20k-concurrent scale claim: BLOCKED; no valid `large_scale` PASS,
  claim permission or required concurrency evidence exists.
- Public copy marketplace: BLOCKED; external publisher/trust/legal/commercial
  evidence and runtime copy-safety certification remain incomplete.

See `docs/evidence/EXTERNAL_BLOCKER_PREFLIGHT_20260927.md`.

## 1. Optional provider and venue certification

The **enabled staging market-data provider set is now integration-verified**.
See `docs/evidence/STAGING_PROVIDER_CERTIFICATION_20260926.md`: the exact
staging run exited successfully and every enabled provider reported explicit
live/public endpoint evidence.

The remaining external boundary applies only to optional or trading-specific
providers that remain disabled until their own evidence exists. In particular:

- Financial Modeling Prep remains disabled behind `FMP_ENABLED=0` until the
  configured plan includes the required candle endpoints and recertification
  passes;
- Alpha Vantage remains disabled behind `ALPHAVANTAGE_ENABLED=0` until the
  intended endpoint/timeframe plan is entitled and recertified;
- OANDA remains disabled behind `OANDA_ENABLED=0` until the intended
  practice/live credentials, account identity and broker behavior are
  certified;
- FRED remains disabled behind `FRED_ENABLED=0` until a valid credential and
  exact-environment macro-provider certification pass;
- other dormant venues/providers remain disabled by catalogue policy until
  their credentials, licence/redistribution terms, regional availability and
  capability-specific evidence are supplied.

For a disabled provider/venue to be enabled, required external evidence may
include:

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

This boundary is tracked as `SR-PROVIDER-008`. It does not downgrade the
integration-verified enabled provider set under `SR-PROVIDER-007`.

## 2. Broker demo/canary/live-money certification

2026-09-27 current read-only staging preflight evidence: deployment
`9757cac0-7f68-466a-a9a0-8e458f1390cd` on marker
`3656eabaf56a7468a49667e078289d4bf00028af` ran against Alembic
`0045_mt5_credential_retirement` after secure Broker Hub frontdoor deployment
`68219e01-9b4a-48a8-8abb-9e4372f634f9` at `c4d1e6d6ec5e...`. The frontdoor
keeps broker secrets out of Telegram chat, hands authenticated users to Broker
Hub, and retains the provider-proven **Prepare DEMO certification** action that
re-verifies read-only broker state, requires HEALTHY reconciliation, applies a
bounded `DEMO/MANUAL` policy and keeps execution disabled. The refreshed
preflight still found **zero canonical broker connections** and therefore
correctly returned BLOCKED with `demo_account_not_connected`,
`demo_account_not_read_only_verified`,
`demo_account_credentials_not_ready`, `demo_reconciliation_not_healthy`
and `demo_execution_permission_not_configured`. It performed no activation,
placed zero orders and returned no secrets. Environment-level broker credential
variables are not treated as account ownership and are not silently adopted
into a user's canonical broker connection.

See `docs/evidence/STAGING_DEMO_ACCOUNT_PREFLIGHT_20260927.md`.

The latest frontdoor-only safety rollout, deployment
`68219e01-9b4a-48a8-8abb-9e4372f634f9` at
`c4d1e6d6ec5e...`, adds the secure Broker Hub handoff and preserves the same
fail-closed verification/preparation boundary. Telegram does not collect broker
passwords; users are directed through the authenticated Broker Hub and
`/verifybroker`, and DEMO accounts must still pass **Prepare DEMO
certification** before any execution enablement. The rollout passed 469
clean-room targeted tests, 356 frontdoor image-build tests plus all 12
readiness checks, Alembic 0045/schema admission, frontdoor-only ownership,
healthy webhook startup and /healthz=200. It did not create a broker connection,
enable execution, place an order or change the external demo-account blocker.

Before owner-authorized live execution:

1. connect one explicitly identified DEMO account;
2. run the canonical safe DEMO-preparation action, then separately accept terms
   and explicitly enable only that DEMO account;
3. prove account policy, broker identity, quote freshness and reconciliation;
4. execute bounded demo orders through the canonical router;
5. prove broker acknowledgement, canonical execution lifecycle, account ledger,
   realized P/L/fees, restart reconciliation and idempotency;
6. complete a documented demo certification report;
7. use a tightly capped canary account before any wider live rollout;
8. for PROP/funded accounts, independently validate the exact firm/product rule
   set and certify the immutable policy version;
9. keep LLMs advisory: no model may bypass deterministic risk limits.

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

Repository harness:

- `scripts/load_certification.py plan` builds deterministic per-shard plans
  from `requirements/scale_profiles.yaml`;
- `run` requires `--acknowledge-authorized-target` and emits one shard's
  machine-readable HTTP evidence;
- `merge` rejects missing or duplicate shard sets;
- `certify` refuses a PASS unless every declared profile SLO is supplied and
  passes, including duplicate-delivery/order and projection-coverage metrics.

No 100k capacity claim is permitted until the distributed test is run against
representative infrastructure and the merged runtime metrics pass certification.

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

As of 2026-09-27:

- staging database is certified at Alembic `0045_mt5_credential_retirement`;
- staging frontdoor, engine, delivery and analytics roles pass release/schema
  admission on the decomposed topology;
- broker legacy-secret inventory is clean in certified staging;
- canonical demo broker connections currently present in staging: **0**; demo certification remains blocked until an explicitly owned demo account is linked through the canonical flow;
- real execution, copy execution, live broker-account execution, mainnet
  Hyperliquid, real payouts and Paystack transfers remain disabled;
- production remains a separate controlled rollout and was not promoted merely
  by staging certification.
