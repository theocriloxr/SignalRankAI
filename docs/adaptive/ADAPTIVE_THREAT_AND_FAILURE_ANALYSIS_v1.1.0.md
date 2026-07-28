# Adaptive Strategy Threat and Failure Analysis v1.1.0

| Threat or failure | Control |
|---|---|
| Look-ahead leakage | Chronological sorting, purged train boundary, later-only validation, future-row regression test. |
| Overfitting | Bounded weights, minimum samples, multi-fold WFO, complexity kept deterministic, no auto-promotion. |
| Candidate explosion | Stable content fingerprints and duplicate suppression. |
| Unsafe negative transfer | Per-asset profiles override broader assumptions; no automatic global-to-asset live promotion. |
| Fabricated order flow | Genuine bid/ask/delta requirement; unavailable evidence otherwise. |
| Gemini hallucination | Adaptive components generate deterministic evidence; Gemini cannot create price facts or profiles. |
| DB starvation | Queue-based candle persistence, analytics admission priority, advisory lock, bounded batches. |
| Duplicate workers | PostgreSQL advisory transaction lock and idempotent profile fingerprints/events. |
| Stale approved Redis profile | Immediate cache invalidation on suspension; republish after rollback. |
| Missing calibration | Promotion gate fails closed. |
| Live degradation | Confirmed-delivery-only drift monitor, automatic suspension and rollback. |
| Provider outage mislabelled as strategy loss | Data quality/provider context remains separate from strategy outcome. |
| Unapproved strategy affects live scoring | SHADOW/RESEARCH weights are neutral; only current runtime states are published. |
| Direct jump to live | Enforced transition map SHADOW → FORWARD_TEST → CANARY → LIMITED_LIVE. |
| User command abuse | Commands limited to configured owner/admin IDs, audited through existing handler wrapper. |
| Real-money expansion by adaptive flag | Execution, payments, copy trading and payouts remain independent gates. |
