# Current SignalRankAI Release

```text
Version: 1.5.1
Patch level: master-blueprint-release-candidate-20261001
Fingerprint: signalrank-blueprint-0048-runtime-schema-bridge-20261002
Repository Alembic head: 0048_runtime_schema_bridge
Release-candidate branch: implementation-of-master-blueprint
Release-candidate status: NOT YET LIVE-CERTIFIED
Previously certified staging baseline: 0045_mt5_credential_retirement (historical only)
Production runtime baseline: 8f8583933a853a54ba1b3585610ee466903c08fc
Production live-money posture during certification: keep disabled / fail-closed
```

This file is the current source for release provenance. Historical staging,
production and clean-room reports remain evidence for the exact older SHAs they
name; they do **not** certify the current release candidate.

## Current release-candidate changes

The repository schema now extends the previously certified credential-retirement
chain with:

- `0046_decision_log`: unified decision/rejection evidence;
- `0047_event_outbox`: durable PostgreSQL fallback for critical events when the Redis transport is unavailable;
- `0048_runtime_schema_bridge`: canonical Alembic bridge for runtime-critical columns that previously existed only in the retired parallel migration tree or startup auto-repair.

The current release candidate also includes:

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
