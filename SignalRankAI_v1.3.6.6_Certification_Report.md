# SignalRankAI v1.3.6.6 Source Certification Report

Date: 2026-08-02
Fingerprint: `v1.3.6.6-runtime-certification-hotfix-20260802`

## Result

- Source hotfix verification: **PASS**
- Staging redeployment eligibility: **PASS**
- Runtime production certification: **PENDING REDEPLOYMENT EVIDENCE**
- Live/copy/public claim activation: **BLOCKED**

## Verified fixes

- PostgreSQL reconciliation query compiles without `DISTINCT ON`.
- Delivery proof is grouped into one candidate per signal.
- Missing outcome rows are prioritized and batch-limited.
- Logged weak model metrics (accuracy `0.50`, AUC `0.575`) fail deployed promotion thresholds.
- Deployed promotion requires validated calibration by default.
- Outcome notification budget begins after the DB snapshot.
- Remote notification price fetching is disabled by default.
- Broker master-switch ordering and real-account integrity are preserved.

## Validation

- Runtime-hotfix tests: `5 passed`.
- Production-focused matrix: `147 passed`.
- Broker entrypoint subset: `16 passed`.
- Source integrity verifier: `PASS`.
- v1.3.6.5 production-integrity verifier updated for v1.3.6.6: `PASS`.
- Schema audit: `PASS`, 34 revisions, head `0034_production_integrity`.
- Governance generation/check: `PASS`.
- Python compilation: `PASS`.

The validation container still lacks APScheduler, so tests importing the complete Railway/Telegram runtime must be run in the user's `.audit-venv` and Railway deployment.

## Remaining runtime evidence

This source report does not certify outcome coverage, performance truth, provider-backed all-class discovery, ML calibration, demo execution, live execution, copy trading, payments or a public win-rate claim. Those require real post-deployment evidence and must remain fail-closed.
