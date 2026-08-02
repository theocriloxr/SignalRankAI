# SignalRankAI v1.3.6.6 Runtime Certification Hotfix

Date: 2026-08-02
Fingerprint: `v1.3.6.6-runtime-certification-hotfix-20260802`
Base: v1.3.6.5

## Why this hotfix exists

Railway staging proved that migration `0034_production_integrity` was installed, but three runtime defects still blocked certification:

1. Outcome reconciliation generated invalid PostgreSQL `DISTINCT ON` ordering and never completed.
2. A weak ML candidate with 50% accuracy and 0.575 AUC was promoted despite drift and missing calibration evidence.
3. Outcome notifications spent their bounded budget before reaching recipients, repeatedly deferring the same terminal outcome.

A fourth compatibility issue was also corrected: broker master switches now fail before expensive profile/broker loading, while real accounts retain the complete live-integrity contract.

## Fixes

### Outcome and performance reconciliation

- Replaced invalid `DISTINCT ON` SQL with one-row-per-signal delivery-proof aggregation.
- Selects missing outcome projections first, avoiding long-term batch starvation.
- Preserves chronological proof ordering and the configured batch limit.
- Allows worker-owned performance reconciliation to execute after outcome projection.

### ML promotion safety

- Deployed-runtime default minimum AUC: `0.60`.
- Deployed-runtime default minimum accuracy: `0.55`.
- Models below either threshold are rejected and the active primary model is preserved.
- Deployed promotion requires validated held-out calibration by default.
- Uncalibrated candidates may be saved separately but cannot replace the primary model.

### Outcome notification progress

- The notification work budget starts after the prerequisite database snapshot.
- Tracker/outcome evidence is used as the notification price source.
- Remote OHLC price fetching is disabled by default and available only as a bounded opt-in fallback.
- Prevents the same terminal outcome from being indefinitely deferred before its first recipient.

### Broker gate ordering

- AUTO/COPY master-switch failures are returned before profile and broker calls.
- Demo execution remains available for controlled broker certification.
- Real accounts still require production activation, allowlists, calibrated signal integrity, reconciliation, risk controls and kill-switch clearance.

## Safety boundary

This release fixes runtime certification blockers. It does not certify profitability, create certification IDs, guarantee a 60% win rate, or enable live/copy/public marketing switches. Those remain fail-closed until post-deployment evidence passes.
