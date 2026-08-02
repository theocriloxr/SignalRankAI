# SignalRankAI v1.3.6.5 Source Certification Report

Date: 2026-08-02
Fingerprint: `v1.3.6.5-production-integrity-hardening-20260802`

## Certification result

**SOURCE CERTIFICATION: PASS**
**STAGING DEPLOYMENT: ELIGIBLE**
**UNRESTRICTED LIVE/COPY/PUBLIC CLAIM ACTIVATION: BLOCKED PENDING RUNTIME EVIDENCE**

## Verified source contracts

| Contract | Result |
|---|---|
| Migration graph | PASS — 34 revisions, one head: `0034_production_integrity` |
| Signal thesis deduplication | PASS |
| Per-user asset cooldown/race protection | PASS |
| Purpose-specific freshness | PASS |
| Provider discovery/provenance gate | PASS |
| Aggregate profile-demand scanning | PASS |
| Per-user delivery/paper/live/copy policy | PASS |
| Signal geometry and quality gate | PASS |
| Out-of-sample calibration evidence path | PASS |
| Public probability fail-closed behavior | PASS |
| Paper duplicate/freshness/exposure controls | PASS |
| Paper daily-loss and aggregate-risk breakers | PASS |
| Monotonic outcome ordering | PASS |
| Candle-extrema outcome recovery contract | PASS |
| Worker outcome projection reconciliation | PASS |
| Worker performance-ledger reconciliation | PASS |
| Public performance fail-closed behavior | PASS |
| Independent-thesis public-claim statistics | PASS |
| Shadow and Engine Pulse certification gates | PASS |
| Live financial dependency graph | PASS |
| Copy-trading separate certification gate | PASS |
| Generated governance artifacts | PASS |

## Validation evidence

### Production-focused matrix

```text
144 passed
```

Modules covered production integrity, profile routing, v1.3.6.4 regression compatibility, signal deduplication, paper exits, monitoring reliability, outcome delivery, provider/asset registry hardening, live financial activation, Railway decomposition, staged contracts, runtime hardening and canonical broker entrypoints.

### Broad dependency-independent matrix

```text
405 passed, 1 skipped
```

This matrix covered 105 modules that do not require importing the unavailable Telegram/APScheduler dependencies in the validation container.

### Integrity verifier

```text
overall=PASS release=v1.3.6.5 live_activation=BLOCKED_UNTIL_RUNTIME_CERTIFIED
```

### Schema audit

```text
ok=true
heads=[0034_production_integrity]
revisions=34
live_financial_contract.ok=true
outcome_projection_contract.ok=true
signal_runtime_contract.ok=true
```

### Compilation

```text
818 Python files compiled
0 errors
```

## Environment limitation

The validation container does not have `python-telegram-bot` or APScheduler and its package index could not provide them. Therefore the complete 195-module repository collection was not executed in this environment. The production-focused source-contract tests passed, but the full suite must also be run in the project’s `.audit-venv` and after Railway deployment where declared runtime dependencies are installed.

## Required runtime certification

Source certification does not create these IDs. They must be generated from real evidence and must never be invented:

- production integrity;
- live runtime;
- calibrated ML artifact;
- provider discovery;
- freshness;
- profile routing;
- paper trading;
- delivery and Telegram lifecycle;
- outcome tracking;
- performance truth;
- public performance claim;
- shadow tracking;
- Engine Pulse integrity;
- OHLC pipeline;
- tests and secret scan;
- demo trading;
- copy trading, when requested.

## Profitability and claim boundary

No source test can prove a future win rate. The system may only display calibrated probabilities when held-out calibration passes, and may only make a public 60% claim when the independent-thesis sample, terminal coverage, observed rate and Wilson lower-confidence-bound gates all pass.

## Final determination

The code is suitable for controlled staging, paper simulation, provider discovery validation, profile-routing validation and broker demo certification. It remains intentionally blocked from unrestricted live money, public paid launch, copy trading and performance marketing until the deployment guide’s runtime gates pass.
