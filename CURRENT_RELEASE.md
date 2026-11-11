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
Repository Alembic head: 0063_user_trade_ideas
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
- `0058_exclude_no_trade_outcomes`: data-only. Missed-entry/expired outcomes that carry an R get an audited correction (R cleared, original kept in `correction_reason`) and are excluded from performance; outcomes with |R| > 10 (degenerate stops) are excluded with a reason. Nothing is deleted; no schema change.
- `0059_close_pending_terminal`: data-only. Closed outcomes stored with `canonical_outcome` `pending` or empty (the 4 Nov ZECUSDT stop) get the canonical result `upsert_outcome` now derives, as an audited correction (previous value named in `correction_reason`). Status, R, percent and inclusion are unchanged; nothing is deleted; no schema change.
- `0060_notification_channels`: new table `notification_channel_deliveries` (one row per notification and external channel, email or push) so each is sent at most once. No existing data changes.
- `0061_tracked_shadow_index`: partial index `ix_decision_log_tracked_id` on `decision_log(id)` for rows with a tracked outcome, built concurrently (no write blocking). The strategy scorecard reads only those rows. No data changes.
- `0062_candidate_shadow_index`: partial index `ix_ml_rejected_candidate_shadow` on `ml_rejected_signals` (artifact hash, created_at) for challenger forward-proof rows, built concurrently. `/ml_candidate` and the training lease read only those rows. No data changes.
- `0063_user_trade_ideas`: new table `user_trade_ideas` for trades users submit for analysis (Telegram `/check_trade`, website/app Analyse page, API); the idea tracker labels each one from candles after its entry is touched, the owner of the idea is notified, and resolved ideas join training as low-weight fit-only rows. Additive table and indexes only.

The current release candidate also includes:

- complete financial-switch admission and startup clamping, including prop, legacy MT5, unsupported mainnet and automatic-payout switches; paper-release approval and monitoring reject these switches without their required safety posture;
- transactional ML promotion bound to the reviewed candidate and champion row identities, with stale reviews rejected;
- strictly typed ML qualification, finite metrics/tolerances and required champion comparisons; market-class certification requires the canonical calendar session to be open;
- cycle-bound background delivery and lock cleanup, shared final-opportunity prefiltering, and freshness-first resend selection ([incident details](docs/CONTINUATION_DELIVERY_20261011.md));
- bounded prospective engine-universe observations bound to immutable component inputs, with historical membership still unverified;
- immediate removal of ineligible assets from pending and refill scanner queues;
- exact-branch CI/release-manifest gating;
- setup-evidence snapshot refreshed one hour per short session with retries (a single 30 s session timed out and the fail-closed filter blocked every candidate for 19 h, 10-11 Nov 2026), named in the drought alert; Coinbase 4h built from complete UTC hours; scorer rejections named in place of "Score 0.0"; background trade-idea, rank-alert and teaser reads at analytics DB priority; each ML training run also kept in `runtime_state`;
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
