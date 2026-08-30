# Adaptive Strategy Operations Runbook v1.1.0

## Railway deployment

1. Deploy the v1.1.0 source package.
2. Apply migration `0025_adaptive_strategy`.
3. Set `APP_VERSION=1.1.0`.
4. Apply `SignalRankAI_v1.1.0_Railway_Adaptive_Enabled.env.example`.
5. Keep `ADAPTIVE_SHADOW_CANDIDATES_IN_SIGNAL_PIPELINE_ENABLED=0`.
6. Keep `ADAPTIVE_AUTO_PROMOTION_ENABLED=0` and `ADAPTIVE_REQUIRE_HUMAN_APPROVAL=1`.
7. Do not treat adaptive enablement as permission to enable unrestricted execution, public payments, payouts or copy trading.

## Expected startup evidence

```text
[boot] SignalRankAI v1.1.0
[worker] AdaptiveStrategyLearning started
[worker] AdaptiveCandleCapture started
[adaptive] asset=... mode=shadow_observation profile=baseline:...
```

The first analytics run is intentionally delayed to avoid startup DB pressure.

## Owner commands

- `/adaptive_status [ASSET]` — profile, dataset, WFO and learning status.
- `/adaptive_pause` — pause candidate generation and optimisation. Existing approved runtime profile behaviour is unchanged.
- `/adaptive_resume` — resume analytics.
- `/adaptive_promote <profile_id> <FORWARD_TEST|CANARY|LIMITED_LIVE>` — execute the next evidence-gated transition.
- `/adaptive_suspend <profile_id> [reason]` — immediately suspend and invalidate the runtime cache.
- `/adaptive_rollback <ASSET>` — restore the recorded previous runtime profile.

Commands are silent for users who are not in `OWNER_IDS` or `ADMIN_IDS`.

## Certification sequence

1. Confirm canonical candle writes in `market_candles`.
2. Confirm signal rows have `adaptive_signal_evidence` and `adaptive_signal_sequences` records.
3. Confirm dataset and feature versions are created.
4. Confirm WFO fold timestamps are strictly chronological.
5. Confirm new profiles begin in `SHADOW` with `is_current=FALSE`.
6. Run shadow and forward tests across multiple regimes.
7. Add confidence-calibration evidence.
8. Use owner command to move one lifecycle step only.
9. Confirm CANARY application is bounded and existing risk rejections remain effective.
10. Confirm drift suspension and rollback in staging before limited live use.

## Emergency response

- Pause learning: `/adaptive_pause`.
- Suspend a degraded profile: `/adaptive_suspend <profile_id> incident_reference`.
- Roll back: `/adaptive_rollback <ASSET>`.
- Use the existing platform kill switch for broader execution risk.

## Diagnostics

Investigate:

- `[adaptive] ... evaluation failed` — component or malformed market context.
- `[adaptive_candles] ...` — capture queue or DB admission pressure.
- `[adaptive_learning] iteration failed` — analytics DB, migration or data issue.
- `distributed_lock_busy` — another worker owns the current run; this is safe.
- `duplicates_skipped` — unchanged candidate fingerprint was correctly suppressed.
- `drift.suspended_assets` — current profile was automatically removed.

## Rollback

Code rollback can return to v1.0.8. Database downgrade is available but should only be run after confirming no v1.1.0 process remains. Adaptive tables are additive and do not alter existing signal/outcome tables.
