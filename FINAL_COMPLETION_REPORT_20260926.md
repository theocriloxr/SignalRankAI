# SignalRankAI — Current Completion Report

Date: 2026-09-26  
Release line: 1.5.1 + 2026-09-25/26 blueprint hardening  
Repository Alembic head: `0045_mt5_credential_retirement`

## Completion statement

The repository-side implementation requested by the 2026-09-25 SignalRank
blueprint has been hardened through the current staging-certified architecture.
Items that require real third-party credentials, representative 100k-scale
infrastructure, legal approval, elapsed soak time, or owner-authorized
live-money activity remain separate external gates and are not represented as
complete.

## Current staging architecture

The shared staging PostgreSQL database is at
`0045_mt5_credential_retirement`.

The long-lived staging topology is decomposed and role-owned:

- frontdoor: HTTP + Telegram + frontdoor scheduler; engine=false, worker=false;
- engine: market discovery, strategy/signal generation and candidate decision;
- delivery: delivery/outcome/reconciliation work;
- analytics: model learning, discovery and analytics-owned background work.

All four roles enforce release-source and database-schema admission before
business work.

Current post-0045 staging role deployments are aligned on the same certified
provider-opt-in hardening commit `b2249fe64b8ae05b178ccec5e0879590c56f7130`:

- analytics: deployment `c1d51cca-be56-43ed-b87c-446e651793bc`;
- engine: deployment `f550a99e-0669-4bf8-a794-a41e90330b30`;
- delivery: deployment `52ab68b7-a301-49e3-ada8-b74f2af49f2c`;
- frontdoor: deployment `7b06848a-11dd-4fb0-bcc7-bd0ae3595f39`.

All four passed release-source and `0045_mt5_credential_retirement` schema
admission. Frontdoor explicitly skips engine/worker ownership, while the other
three roles start only their declared dedicated runtime lanes. Role-specific
Railway watch paths plus the controlled common staging-rollout path prevent
unrelated production promotion.

## Multi-user / multi-account execution

Implemented and tested:

- multiple broker connections per canonical user;
- immutable `connection_id` account identity;
- PAPER / DEMO / LIVE_PERSONAL / PROP classification;
- separately versioned account risk/execution policy;
- explicit Telegram account choice through opaque short-lived server tokens;
- BOLA/IDOR ownership checks;
- per-account risk ceilings, trading windows, spread/slippage and strategy rules;
- configuration-driven PROP hard rules;
- owner/admin-only immutable PROP policy certification;
- reconciliation safety freezes;
- account-scoped execution decisions and evidence;
- append-only per-account broker ledger;
- per-account performance composition on web.

## Execution lifecycle

A single monotonic execution state machine now owns broker execution state.
Terminal states are absorbing, same-state observations are idempotent,
ambiguous/reconciliation states are explicit, and every execution state maps to
one canonical position-state projection.

MT5 and Bybit routers/reconcilers use this canonical transition writer.

Real-money execution remains disabled in staging.

## Provider certification

The enabled staging market-data provider set is now independently certified in
the exact staging environment.

Evidence:

- provider-cert commit: `12e2427e1faa4a7b72d3484953a7d3736d19eb81`;
- provider-cert deployment: `65c8d1a6-0358-49ee-91b2-aa8b60718fda`;
- matching clean-room deployment:
  `115f4d92-b78f-4063-99e1-3908fdd3137f`;
- certification exit: `0`;
- clean-room result: Alembic 0045/schema/provenance PASS and 396 targeted tests
  PASS.

Every enabled market-data provider reported explicit live/public endpoint
evidence. FMP, Alpha Vantage, OANDA and FRED are implemented but deliberately
disabled behind explicit operator gates until their missing plan/credential
requirements are independently certified. See
`docs/evidence/STAGING_PROVIDER_CERTIFICATION_20260926.md`.

This completes `SR-PROVIDER-007` for the enabled provider set while preserving
the optional-provider external boundary under `SR-PROVIDER-008`.

## Broker credential security

Migrations `0044_broker_credential_envelope` and
`0045_mt5_credential_retirement` provide:

- context-bound broker credential envelopes;
- user/connection/provider/connector/revision binding;
- active-key/keyring rotation;
- fail-closed missing-key behavior;
- execution disablement on credential rotation;
- non-secret audit provenance;
- retirement of duplicate MT5 password persistence;
- counts-only credential inventory.

Certified staging inventory reports zero legacy, duplicate or unmigrated broker
secret rows at the recorded certification point.

## ML/model governance

Implemented and tested:

- calibrated probability governance;
- durable primary/candidate artifacts;
- champion/challenger non-inferiority comparison;
- shadow candidate inference and persistence;
- candidate-only behavior when promotion gates fail;
- rollback to the previous champion when promoted serving validation fails;
- deterministic dataset version/hash;
- training-run ID;
- parent-model/current-champion hash lineage;
- fail-closed lineage mismatch;
- WFO/dataset leakage contracts;
- live-risk authority remains separate from model promotion.

## Market coverage

The engine supports and discovers:

- crypto;
- FX;
- equities/stocks;
- indices;
- commodities.

Market/session calendars are applied after discovery. A class may correctly have
zero assets in the open scan queue when that market is closed; that is not
treated as missing provider support.

## Delivery and notification reliability

Implemented and tested:

- durable delivery reservation before send;
- per-user/per-asset serialization;
- idempotency keys;
- monotonic delivery state;
- Telegram acknowledgement proof;
- ambiguous-send no-blind-retry behavior;
- receipt stash/reconciliation;
- bounded/retry-aware fan-out and outbox recovery;
- frontdoor does not own worker outcome reconciliation.

## Database/runtime safety

Implemented and staged:

- one schema head;
- migration-owner discipline;
- release-source admission;
- schema admission;
- decomposed role ownership;
- bounded DB priority/admission;
- foreground reserve;
- analytics/background shedding;
- locked dependency graph;
- `pip install --no-deps` + `pip check`;
- deterministic clean-room verification;
- staging role-specific rollout isolation.

## Supply-chain provenance

The release now has deterministic repository tooling to generate:

- CycloneDX 1.5 SBOM from `requirements.lock`;
- exact release commit and branch binding;
- current Alembic head binding;
- SHA-256 hashes for the dependency lock, Dockerfile, release contract and SBOM;
- self-verifying release provenance bundle.

External signing with an organization-controlled key remains a separate release
operation.

## Security

The current threat model covers:

- account takeover/session/MFA replay;
- broker-account BOLA/IDOR;
- credential replay/rotation;
- payment webhook forgery/replay;
- ledger tampering;
- wrong-account execution;
- PROP-rule bypass;
- quote freshness/provider degradation;
- LLM/prompt-injection execution boundaries;
- database/Redis outages;
- queue/resource exhaustion;
- supply chain;
- operator abuse;
- cross-role duplication;
- cross-environment contamination;
- disabled copy-trading/marketplace risk;
- unverified live-broker risk.

See `docs/security/THREAT_MODEL.md`.

## Verification

The current release path has:

- deterministic clean-room compile + Alembic release-chain + schema-audit gates;
- targeted account/security/ML/execution/delivery tests;
- locked Railway image build gate with 275 tests plus readiness checks on the
  current staging runtime line;
- live staging `0045` schema admission for all four long-lived roles;
- frontdoor `/healthz` success and active Telegram webhook with pending=0;
- production left as a separate controlled gate.

## Deliberately incomplete external claims

The following are not claimed complete by this report:

- every declared venue live/sandbox certified;
- 100,000-user infrastructure load certification;
- 24-hour+ final production-candidate soak and disaster-recovery exercise;
- real payment settlement/email/OAuth/mobile-store external-provider proof;
- external artifact signature/attestation;
- copy-trading/marketplace legal/trust certification;
- a specific funded/PROP account certification;
- owner-authorized live-money canary;
- any guaranteed trading win rate.

See `BLOCKED_EXTERNAL_REQUIREMENTS_20260926.md`.

## Production boundary

Staging certification is not production approval. Production promotion must use
its own backup, migration, release-source, schema, provider, legal, demo/canary
and owner-authorization gates. Live-money switches must not be inferred from
ordinary application health.
