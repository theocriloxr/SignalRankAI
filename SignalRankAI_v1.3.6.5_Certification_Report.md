# SignalRankAI v1.3.6.5 Source Certification Report

Date: 2026-08-02  
Release: `1.3.6.5`  
Fingerprint: `v1.3.6.5-production-integrity-hardening-20260802`

## Certification result

**Source certification: PASS for staging deployment and runtime certification.**

**Live-production certification: NOT YET EARNED.**

This distinction is intentional. Source tests prove the controls are implemented; only Railway staging/canary, real providers and broker reconciliation can prove that the deployed system operates safely.

## Implemented controls

- canonical cross-timeframe signal-thesis fingerprint;
- transaction-serialized thesis persistence;
- transaction-serialized per-user asset delivery reservation;
- four-hour user asset cooldown with production fail-closed behavior;
- delivered signal geometry immutability;
- online multi-provider asset discovery and provenance;
- profile-demand scan planning and per-user eligibility/ranking;
- execution-time freshness checks;
- paper duplicate-asset and portfolio exposure controls;
- paper close-all recovery;
- monotonic outcome stages and durable notification claims;
- proof-backed delivery projection reconciliation;
- independent-thesis performance statistics;
- terminal-coverage and Wilson-confidence public claim gate;
- held-out calibration evidence requirements;
- live/copy execution evidence gates;
- provider-coverage and production-integrity readiness checks;
- Alembic migration `0034_production_integrity`.

## Automated evidence

| Check | Result |
|---|---|
| Integrated relevant test suite | 114 passed, 1 deselected |
| Focused final UTC-clean suite | 41 passed |
| Python compilation | PASS |
| Alembic heads | `0034_production_integrity (head)` |
| v1.3.6.5 integrity verifier | PASS |
| Railway decomposition verifier | PASS |
| Production cutover verifier | PASS |
| Static asset fallback default | OFF |
| Real execution default | OFF |
| Copy trading default | OFF |
| Global execution kill switch default | ON |

## Evidence still required before live launch

- the exact approved Git commit deployed to all three roles;
- successful migration and readiness from Railway;
- provider-discovery certification across enabled asset classes;
- freshness and profile-routing canaries;
- paper-trading admission and recovery canaries;
- outcome projection coverage meeting the configured threshold;
- stable command/callback and scheduler SLOs;
- held-out calibration artifact meeting row/Brier/ECE thresholds;
- broker demo execution and reconciliation;
- owner-only live canary with bounded exposure;
- separately certified copy-trading fan-out and reconciliation;
- performance truth with independent theses and at least 95% terminal coverage;
- a statistical report before any public 60% claim.

## Public-claim determination

The release prevents a 60% claim solely because a point estimate reaches 60%. The claim is allowed only when the sample, unique-thesis count, terminal coverage and 95% Wilson lower confidence bound all meet the configured threshold.

Therefore, v1.3.6.5 is capable of supporting a truthful future claim, but it does not itself establish that the strategy has achieved 60% reliability.

## Final source verdict

The code is suitable for deployment to staging and controlled certification. It is not honest or safe to enable unrestricted live auto-trading, copy trading, paid public launch or a 60% marketing claim until the external evidence gates above have genuinely passed.
