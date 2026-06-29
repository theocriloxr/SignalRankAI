# Shadow Intelligence Governance

Last updated: 2026-06-29
Owner: Quant/Engineering

Shadow Intelligence is a first-class subsystem. It evaluates production decisions
and alternative decisions, but it must not automatically change live production
logic without evidence and promotion controls.

## Required Capabilities

- Evaluate every production decision.
- Record alternative decisions and model probabilities.
- Compare production outcomes against shadow outcomes.
- Measure precision, recall, calibration, false positives, and false negatives.
- Detect strategy, model, and confidence drift.
- Recommend improvements backed by historical evidence.

## Promotion Gate

No shadow recommendation may change live production behavior until it passes:

1. Historical replay.
2. Backtesting.
3. Forward testing.
4. Statistical significance checks.
5. Acceptance thresholds.
6. Human review or explicitly documented automated promotion criteria.

## Current Implementation Evidence

- `db.models.MLShadowPrediction` stores shadow model predictions.
- `engine/shadow_outcome_worker.py` exists for outcome comparison work.
- `services/decision_intelligence.py` includes `shadow_agreement`.
- `ml/ml.py` records shadow prediction metadata where configured.

## Open Governance Work

| ID | Gap | Required Work | Status |
| --- | --- | --- | --- |
| SHADOW-001 | Full production decision coverage | Ensure every accepted/rejected/skipped signal gets a production and shadow record. | Open |
| SHADOW-002 | Counterfactual outcomes | Track what rejected/shadow trades would have done. | Open |
| SHADOW-003 | Promotion thresholds | Define minimum sample size, win-rate lift, calibration, and drawdown criteria. | Open |
| SHADOW-004 | Review workflow | Add admin report for recommendations and approval trail. | Open |
