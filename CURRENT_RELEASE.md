# Current SignalRankAI Release

The authoritative recovery/handoff contract is now
[`docs/release/MASTER_EXECUTION_CONTRACT.md`](docs/release/MASTER_EXECUTION_CONTRACT.md),
with exact source revisions in [`baseline.json`](docs/release/baseline.json).
Stage 1 acceptance and current evidence are recorded there. Production baseline
values below are historical observations, not a fresh deployment certification.

```text
Version: 1.5.1
Patch level: master-blueprint-release-candidate-20261001
Fingerprint: signalrank-blueprint-0048-runtime-schema-bridge-20261002
Repository Alembic head: 0057_expectancy_shadow_index
Release-candidate branch: fix/stage1-canonical-reconciliation-20261014
Release-candidate status: NOT YET LIVE-CERTIFIED
Previously certified staging baseline: 0045_mt5_credential_retirement (historical only)
Production runtime baseline: 9865a3d1bcee632bfd9347e50d5de34d355225d9 (schema 0053_research_market_inputs)
Production live-money posture during certification: keep disabled / fail-closed
```

This file summarizes release provenance. Historical staging,
production and clean-room reports remain evidence for the exact older SHAs they
name; they do **not** certify the current release candidate.

## Current release-candidate changes

The repository schema now extends the previously certified credential-retirement
chain with:

- `0046_decision_log`: unified decision/rejection evidence;
- `0047_event_outbox`: durable PostgreSQL fallback for critical events when the Redis transport is unavailable;
- `0048_runtime_schema_bridge`: canonical Alembic bridge for runtime-critical columns that previously existed only in the retired parallel migration tree or startup auto-repair;
- `0049_research_trial_ledger`: append-only hypothesis versions, trial definitions, terminal results and enforced lineage. Research evidence does not activate trading.
- `0050_profile_health_index`: validated concurrent profile/signal lookup index for bounded strategy-health surveillance. Index availability does not certify trading.
- `0051_strategy_health_baselines`: immutable, owner-approved delivery baselines and predefined decay limits, forward-evidence comparisons and append-only health receipts. Unverified baselines cannot receive runtime cache approvals.

- `0052_research_dataset_snapshots`: append-only canonical outcome dataset snapshots. Adaptive research replays persisted rows after source corrections.
- `0053_research_market_inputs`: bounded immutable normalized component inputs, deduplicated across signals from one capture. Source publication vintages, historical universe membership and calendar qualification remain unverified.

- `0054_shadow_pending_index`: concurrent validated partial index for pending ML-shadow observations; no account or execution state changes.

- `0055_user_renewal_default`: opt-in renewal default for future users; existing preferences and subscription records are untouched.

- `0056_ai_usage_ledger`: append-only AI usage/cost ledger and budget alerts (new tables only; no change to existing data).

- `0057_expectancy_shadow_index`: concurrent, validated partial index for expectancy-shadow decision rows; no data change.

The current release candidate also includes:

- complete financial-switch admission and startup clamping, including prop, legacy MT5, unsupported mainnet and automatic-payout switches; paper-release approval and monitoring reject these switches without their required safety posture;
- transactional ML promotion bound to the reviewed candidate and champion row identities, with stale reviews rejected;
- strictly typed ML qualification, finite metrics/tolerances and required champion comparisons; market-class certification requires the canonical calendar session to be open;
- cycle-bound background delivery and lock cleanup, shared final-opportunity prefiltering, and freshness-first resend selection ([incident details](docs/CONTINUATION_DELIVERY_20261011.md));
- bounded prospective engine-universe observations bound to immutable component inputs, with historical membership still unverified;
- immediate removal of ineligible assets from pending and refill scanner queues;
- exact-branch CI/release-manifest gating;
- web fan-out ORM materialization before SQLAlchemy session expiry;
- bounded adaptive-candle database transaction wall time;
- separate Telegram queue-delay and handler-duration SLOs;
- Redis-first event publication with durable PostgreSQL fallback and replay;
- process-only liveness plus dependency readiness;
- explicit build/version provenance;
- a real Next.js SignalRankAI public/application shell instead of the default
  Create Next App page.

## Certification boundary

This release candidate is **not** production/live-money certified until all
required gates in `certification/release_manifest.yaml` pass for one immutable
SHA. Required external/runtime evidence includes:

1. clean-room compile/schema/targeted regression pass;
2. GitHub/static security and frontend/mobile build gates or equivalent
   independent evidence;
3. isolated Railway staging using separate PostgreSQL and Redis state;
4. current-head migration and restore drill;
5. provider freshness certification for each enabled asset class;
6. demo broker lifecycle and reconciliation certification;
7. database storage headroom and session-hold SLOs;
8. Telegram/web delivery and outcome reconciliation SLOs;
9. 24–72 hour immutable-SHA staging soak;
10. explicit human approval for any controlled live-money pilot.

No successful build or deployment by itself changes this boundary.

The [3 October master audit](docs/MASTER_AUDIT_20261003.md) records P0
corrections, local PostgreSQL evidence, the GitHub billing blocker, active
branch governance and remaining dependency/runtime certification gaps.
No local result grants exact-SHA staging or live-money certification.

## Historical evidence retained

The following remain useful historical references but apply only to the older
release they document:

- `FINAL_COMPLETION_REPORT_20260926.md`
- `BLOCKED_EXTERNAL_REQUIREMENTS_20260926.md`
- `docs/security/THREAT_MODEL.md`
- `docs/architecture/REQUIREMENTS_TRACEABILITY_MATRIX.md`
- `docs/evidence/STAGING_0045_CREDENTIAL_RETIREMENT_20260926.md`
- `docs/evidence/STAGING_PROVIDER_CERTIFICATION_20260926.md`

Production promotion remains a separate controlled operation. Real execution,
automatic execution, copy trading, prop execution and real payouts must remain
disabled until the exact release candidate is certified and the user explicitly
authorizes a controlled pilot.
